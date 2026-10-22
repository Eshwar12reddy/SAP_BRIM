import json
import logging
import uuid
import time
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from backend.app.database import get_db, SessionLocal
from backend.app.models.user import User
from backend.app.models.chat import Chat
from backend.app.models.message import Message
from backend.app.models.citation import Citation
from backend.app.models.web_source import WebSource
from backend.app.models.attachment import ChatAttachment
from backend.app.schemas.message import MessageCreate, MessageResponse, MessageFeedbackRequest, MessageFeedbackResponse
from backend.app.security.auth import get_current_user
from backend.app.services.rag_service import rag_service
from backend.app.services.llm_service import llm_service
from backend.app.services.retrieval_service import retrieval_service
from backend.app.services.reranking_service import reranking_service
from backend.app.services.grounding_service import grounding_service
from backend.app.services.web_search_service import web_search_service
from backend.app.services.sap_classifier import sap_classifier
from backend.app.services.memory_service import memory_service
from backend.app.services.visual import visual_service
from backend.app.config import settings

router = APIRouter(prefix="/chats/{chat_id}/messages", tags=["Messages"])

def verify_chat_ownership(chat_id: str, user_id: str, db: Session) -> Chat:
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == user_id).first()
    if not chat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    return chat

@router.get("", response_model=List[MessageResponse])
def get_messages(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    verify_chat_ownership(chat_id, current_user.id, db)
    messages = (
        db.query(Message)
        .filter(Message.chat_id == chat_id)
        .order_by(Message.created_at.asc())
        .all()
    )

    result = []
    for msg in messages:
        c_list = [
            {
                "id": c.id,
                "document": c.document_name,
                "page": c.page_number,
                "section": c.section,
                "score": c.similarity_score,
                "snippet": c.citation_text
            }
            for c in msg.citations
        ]
        w_list = [
            {
                "id": w.id,
                "title": w.title,
                "url": w.url,
                "domain": w.domain,
                "snippet": w.snippet
            }
            for w in msg.web_sources
        ]
        v_list = [
            {
                "id": v.id,
                "visual_type": v.visual_type,
                "title": v.title,
                "caption": v.caption,
                "step_id": v.step_id,
                "status": v.status,
                "error_message": v.error_message,
                "mime_type": v.mime_type,
                "asset_url": f"/api/visuals/{v.id}/asset" if v.status == "completed" else None,
                "is_generative": v.is_generative,
            }
            for v in getattr(msg, "visuals", [])
        ]
        a_list = [
            {
                "id": a.id,
                "filename": a.filename,
                "file_type": a.file_type,
                "mime_type": a.mime_type,
                "preview_url": f"/api/chats/{chat_id}/attachments/{a.id}",
                "size_bytes": a.size_bytes,
                "extracted_text": a.extracted_text,
                "vision_metadata": json.loads(a.vision_metadata) if a.vision_metadata else {},
            }
            for a in getattr(msg, "attachments", [])
        ]
        result.append(
            MessageResponse(
                id=msg.id,
                chat_id=msg.chat_id,
                role=msg.role,
                content=msg.content,
                source_type=msg.source_type,
                grounding_score=msg.grounding_score,
                grounding_status="evaluated" if msg.grounding_score is not None else "not_evaluated",
                verification_status="evaluated" if msg.grounding_score is not None else None,
                created_at=msg.created_at,
                citations=c_list,
                web_sources=w_list,
                visuals=v_list,
                attachments=a_list,
                feedback=msg.feedback,
                feedback_comment=msg.feedback_comment
            )
        )
    return result

def run_background_memory_extraction(user_id: str, chat_id: str, user_message: str, assistant_message: str):
    bg_db = SessionLocal()
    try:
        memory_service.extract_and_persist(
            db=bg_db,
            user_id=user_id,
            chat_id=chat_id,
            user_message=user_message,
            assistant_message=assistant_message
        )
    except Exception as e:
        logger.warning(f"Background memory extraction failed: {e}")
    finally:
        bg_db.close()

@router.post("")
def send_message(
    chat_id: str,
    msg_in: MessageCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    stream: bool = Query(False, description="Enable Server-Sent Events (SSE) streaming"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        request_id = str(uuid.UUID(request.headers.get("X-Request-ID", "")))
    except (ValueError, AttributeError):
        request_id = str(uuid.uuid4())
    request_started_at = time.perf_counter()
    chat = verify_chat_ownership(chat_id, current_user.id, db)

    # Validate image attachment count
    if msg_in.attachment_ids and len(msg_in.attachment_ids) > settings.MAX_IMAGES_PER_MESSAGE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {settings.MAX_IMAGES_PER_MESSAGE} images allowed per message."
        )

    # Validate non-empty message (content or attachments required)
    trimmed_content = msg_in.content.strip() if msg_in.content else ""
    if not trimmed_content and not msg_in.attachment_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message must include text content or at least one attachment."
        )

    # 1. Save user message
    user_msg = Message(
        chat_id=chat_id,
        role="user",
        content=trimmed_content
    )
    db.add(user_msg)
    
    # Link any attachments provided by user
    attached_items = []
    attachment_context = ""
    attachments_data = []
    if msg_in.attachment_ids:
        attached_items = (
            db.query(ChatAttachment)
            .filter(
                ChatAttachment.id.in_(msg_in.attachment_ids),
                ChatAttachment.chat_id == chat_id,
                ChatAttachment.user_id == current_user.id
            )
            .all()
        )
        for att in attached_items:
            att.message_id = user_msg.id
            meta = {}
            if att.vision_metadata:
                try:
                    meta = json.loads(att.vision_metadata) if isinstance(att.vision_metadata, str) else att.vision_metadata
                except Exception:
                    meta = {}
            attachments_data.append({
                "id": att.id,
                "filename": att.filename,
                "file_type": att.file_type,
                "mime_type": att.mime_type,
                "extracted_text": att.extracted_text,
                "vision_metadata": meta,
            })
            if att.file_type == "image":
                attachment_context += f"\n[Attached SAP Screenshot: {att.filename}]\n{att.extracted_text}\n"
            else:
                attachment_context += f"\n[Attached Document: {att.filename}]\n{att.extracted_text}\n"

    # Auto-generate chat title from first question or screenshot filename if default
    if chat.title == "New SAP Chat" or not chat.title:
        words = trimmed_content.split()
        if words:
            chat.title = " ".join(words[:6]) + ("..." if len(words) > 6 else "")
        elif attached_items:
            chat.title = f"Screenshot: {attached_items[0].filename[:20]}"

    chat.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user_msg)

    # Fetch recent conversation history (excluding the new user_msg)
    prev_messages = (
        db.query(Message)
        .filter(Message.chat_id == chat_id)
        .filter(Message.id != user_msg.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    chat_history = [
        {"role": m.role, "content": m.content, "source_type": m.source_type}
        for m in prev_messages
    ]

    # 2. Check SSE streaming flow
    if stream:
        return handle_streaming_response(
            chat_id, trimmed_content,
            chat_history=chat_history, current_user=current_user,
            request_id=request_id, request_started_at=request_started_at,
            has_attachment=bool(attached_items), attachment_context=attachment_context,
            attachments_data=attachments_data
        )

    # 3. Synchronous RAG flow with enterprise security
    rag_result = rag_service.process_query(
        db, trimmed_content,
        chat_history=chat_history, user=current_user,
        has_attachment=bool(attached_items), attachment_context=attachment_context,
        attachments_data=attachments_data
    )

    # 4. Save assistant message
    assistant_msg = Message(
        chat_id=chat_id,
        role="assistant",
        content=rag_result["answer"],
        source_type=rag_result["source_type"],
        grounding_score=rag_result.get("grounding_score")
    )
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)

    # 5. Persist citations or web sources
    if rag_result["citations"]:
        for c in rag_result["citations"]:
            cit = Citation(
                message_id=assistant_msg.id,
                source_type="knowledge_base",
                document_id="doc-" + c["document"],
                document_name=c["document"],
                chunk_id="chunk-ref",
                page_number=c["page"],
                section=c["section"],
                similarity_score=c["score"],
                citation_text=c["snippet"]
            )
            db.add(cit)
        db.commit()

    if rag_result["web_sources"]:
        for w in rag_result["web_sources"]:
            ws = WebSource(
                message_id=assistant_msg.id,
                url=w["url"],
                title=w["title"],
                domain=w["domain"],
                snippet=w["snippet"]
            )
            db.add(ws)
        db.commit()

    db.refresh(assistant_msg)

    # 6. Enqueue background memory extraction (non-blocking)
    background_tasks.add_task(
        run_background_memory_extraction,
        current_user.id,
        chat_id,
        msg_in.content.strip(),
        assistant_msg.content
    )

    # 7. Plan and enqueue visual placeholders (non-blocking delivery)
    visual_placeholders = []
    try:
        visual_placeholders = visual_service.plan_and_create_placeholders(
            db=db,
            user_id=str(current_user.id),
            chat_id=str(chat.id),
            message_id=str(assistant_msg.id),
            query=msg_in.content.strip(),
            answer_text=assistant_msg.content,
            evidence_text=rag_result.get("evidence_text", ""),
            chat_history_context="",
            memory_context=rag_result.get("memory_context", ""),
        )
        for vp in visual_placeholders:
            background_tasks.add_task(
                visual_service.render_visual_async,
                visual_id=vp["visual_id"],
                user_id=str(current_user.id),
                spec=vp.get("spec"),
            )
    except Exception as v_err:
        db.rollback()
        logger.warning(f"Visual planning failed: {v_err}")

    return MessageResponse(
        id=assistant_msg.id,
        chat_id=assistant_msg.chat_id,
        role=assistant_msg.role,
        content=assistant_msg.content,
        source_type=assistant_msg.source_type,
        selected_source=rag_result.get("selected_source", assistant_msg.source_type),
        grounding_score=assistant_msg.grounding_score,
        kb_relevance_score=rag_result.get("kb_relevance_score"),
        kb_threshold=rag_result.get("kb_threshold", 75),
        fallback_reason=rag_result.get("fallback_reason"),
        stage_timings_ms=rag_result.get("stage_timings_ms", {}),
        web_search_used=rag_result.get("web_search_used", False),
        grounding_status=rag_result.get("grounding_status"),
        is_in_rag_pipeline=rag_result.get("is_in_rag_pipeline"),
        kb_score=rag_result.get("kb_score"),
        web_score=rag_result.get("web_score"),
        winning_score=rag_result.get("winning_score"),
        verification_status=rag_result.get("verification_status"),
        grounding_method=rag_result.get("grounding_method"),
        grounding_summary=rag_result.get("grounding_summary"),
        grounding_claims=rag_result.get("grounding_claims", []),
        internal_evidence_confidence=rag_result.get("internal_evidence_confidence"),
        selected_evidence_quality=rag_result.get("selected_evidence_quality"),
        external_search_used=rag_result.get("external_search_used", False),
        created_at=assistant_msg.created_at,
        citations=[
            {
                "id": c.id,
                "document": c.document_name,
                "page": c.page_number,
                "section": c.section,
                "score": c.similarity_score,
                "snippet": c.citation_text
            }
            for c in assistant_msg.citations
        ],
        web_sources=[
            {
                "id": w.id,
                "title": w.title,
                "url": w.url,
                "domain": w.domain,
                "snippet": w.snippet
            }
            for w in assistant_msg.web_sources
        ],
        follow_up_questions=rag_result.get("follow_up_questions", []),
        used_memories=rag_result.get("used_memories", []),
        used_memory_ids=rag_result.get("used_memory_ids", []),
        previous_context_used=rag_result.get("previous_context_used", False),
        visuals=visual_placeholders,
        attachments=[
            {
                "id": a.id,
                "filename": a.filename,
                "file_type": a.file_type,
                "mime_type": a.mime_type,
                "preview_url": f"/api/chats/{chat_id}/attachments/{a.id}",
                "size_bytes": a.size_bytes,
                "extracted_text": a.extracted_text,
                "vision_metadata": json.loads(a.vision_metadata) if a.vision_metadata else {},
            }
            for a in attached_items
        ]
    )


@router.post("/stream")
def send_message_stream(
    chat_id: str,
    msg_in: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Direct POST /chats/{chat_id}/messages/stream endpoint for SSE streaming."""
    chat = verify_chat_ownership(chat_id, current_user.id, db)

    # Validate image attachment count
    if msg_in.attachment_ids and len(msg_in.attachment_ids) > settings.MAX_IMAGES_PER_MESSAGE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {settings.MAX_IMAGES_PER_MESSAGE} images allowed per message."
        )

    trimmed_content = msg_in.content.strip() if msg_in.content else ""
    if not trimmed_content and not msg_in.attachment_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message must include text content or at least one attachment."
        )

    # 1. Save user message
    user_msg = Message(
        chat_id=chat_id,
        role="user",
        content=trimmed_content
    )
    db.add(user_msg)

    # Link any attachments provided by user
    attached_items = []
    attachment_context = ""
    attachments_data = []
    if msg_in.attachment_ids:
        attached_items = (
            db.query(ChatAttachment)
            .filter(
                ChatAttachment.id.in_(msg_in.attachment_ids),
                ChatAttachment.chat_id == chat_id,
                ChatAttachment.user_id == current_user.id
            )
            .all()
        )
        for att in attached_items:
            att.message_id = user_msg.id
            meta = {}
            if att.vision_metadata:
                try:
                    meta = json.loads(att.vision_metadata) if isinstance(att.vision_metadata, str) else att.vision_metadata
                except Exception:
                    meta = {}
            attachments_data.append({
                "id": att.id,
                "filename": att.filename,
                "file_type": att.file_type,
                "mime_type": att.mime_type,
                "extracted_text": att.extracted_text,
                "vision_metadata": meta,
            })
            if att.file_type == "image":
                attachment_context += f"\n[Attached SAP Screenshot: {att.filename}]\n{att.extracted_text}\n"
            else:
                attachment_context += f"\n[Attached Document: {att.filename}]\n{att.extracted_text}\n"

    if chat.title == "New SAP Chat" or not chat.title:
        words = trimmed_content.split()
        if words:
            chat.title = " ".join(words[:6]) + ("..." if len(words) > 6 else "")
        elif attached_items:
            chat.title = f"Screenshot: {attached_items[0].filename[:20]}"

    chat.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user_msg)

    prev_messages = (
        db.query(Message)
        .filter(Message.chat_id == chat_id)
        .filter(Message.id != user_msg.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    chat_history = [
        {"role": m.role, "content": m.content, "source_type": m.source_type}
        for m in prev_messages
    ]

    return handle_streaming_response(
        chat_id, trimmed_content,
        chat_history=chat_history, current_user=current_user,
        has_attachment=bool(attached_items), attachment_context=attachment_context,
        attachments_data=attachments_data
    )


@router.post("/save-partial")
def save_partial_message(
    chat_id: str,
    msg_in: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Explicitly saves a partial assistant message when generation is stopped."""
    chat = verify_chat_ownership(chat_id, current_user.id, db)
    partial_msg = Message(
        chat_id=chat_id,
        role="assistant",
        content=msg_in.content.strip(),
        source_type="interrupted",
        grounding_score=None
    )
    db.add(partial_msg)
    chat.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(partial_msg)
    return {"status": "saved", "message_id": partial_msg.id}


def handle_streaming_response(
    chat_id: str,
    query: str,
    db: Session = None,
    chat_history: List[Dict[str, Any]] = None,
    current_user: User = None,
    request_id: str = None,
    request_started_at: float = None,
    has_attachment: bool = False,
    attachment_context: str = "",
    attachments_data: Optional[List[Dict[str, Any]]] = None,
):
    """
    Generates Server-Sent Events (SSE) stream using the complete verified RAG pipeline.
    Progressively yields structured status stages, LLM token stream, and done event with citations/grounding.
    Persists the completed assistant message in the database once generation concludes.
    """
    def event_stream():
        save_db = SessionLocal()
        accumulated_text = ""
        done_payload = None
        response_started_at = request_started_at or time.perf_counter()

        hist = chat_history
        if hist is None:
            prev_msgs = (
                save_db.query(Message)
                .filter(Message.chat_id == chat_id)
                .order_by(Message.created_at.asc())
                .all()
            )
            hist = []
            for m in prev_msgs:
                if m.role == "user" and m.content.strip() == query.strip():
                    continue
                hist.append({"role": m.role, "content": m.content, "source_type": m.source_type})

        try:
            for event in rag_service.stream_query(
                save_db, query, chat_history=hist, user=current_user,
                request_id=request_id, request_started_at=request_started_at,
                has_attachment=has_attachment, attachment_context=attachment_context,
                attachments_data=attachments_data
            ):
                event_type = event.get("type")

                if event_type == "token":
                    accumulated_text += event.get("content", "")

                elif event_type == "done":
                    done_payload = event
                    full_answer = (event.get("answer") or "").strip()
                    if not full_answer and accumulated_text.strip():
                        full_answer = accumulated_text.strip()
                    elif not full_answer:
                        full_answer = "No response generated."
                    event["answer"] = full_answer
                    source_type = event.get("source_type", "knowledge_base")
                    grounding = event.get("grounding_score")
                    citations = event.get("citations", [])
                    web_sources = event.get("web_sources", [])

                    # Persist single assistant message to DB
                    assistant_msg = Message(
                        chat_id=chat_id,
                        role="assistant",
                        content=full_answer,
                        source_type=source_type,
                        grounding_score=grounding
                    )
                    save_db.add(assistant_msg)
                    save_db.commit()
                    save_db.refresh(assistant_msg)
                    logger.info("Persisted completed assistant message id=%s length=%d chat_id=%s", assistant_msg.id, len(full_answer), chat_id)

                    if citations:
                        for c in citations:
                            save_db.add(Citation(
                                message_id=assistant_msg.id,
                                source_type="knowledge_base",
                                document_id="doc-" + str(c.get("document", "")),
                                document_name=c.get("document", ""),
                                chunk_id="chunk-ref",
                                page_number=c.get("page"),
                                section=c.get("section"),
                                similarity_score=c.get("score"),
                                citation_text=c.get("snippet")
                            ))
                        save_db.commit()

                    if web_sources:
                        for w in web_sources:
                            save_db.add(WebSource(
                                message_id=assistant_msg.id,
                                url=w.get("url"),
                                title=w.get("title"),
                                domain=w.get("domain"),
                                snippet=w.get("snippet")
                            ))
                        save_db.commit()

                    event["message_id"] = assistant_msg.id
                    event["used_memories"] = done_payload.get("used_memories", [])
                    event["used_memory_ids"] = done_payload.get("used_memory_ids", [])
                    event["previous_context_used"] = done_payload.get("previous_context_used", False)
                    event["attachments"] = attachments_data or []

                    # Persist cross-chat memory facts after answer completion
                    if current_user and getattr(current_user, "id", None):
                        try:
                            memory_service.extract_and_persist(
                                db=save_db,
                                user_id=current_user.id,
                                chat_id=chat_id,
                                user_message=query,
                                assistant_message=full_answer
                            )
                        except Exception as m_err:
                            logger.warning(f"Background memory extraction on stream done failed: {m_err}")

                        # Plan visuals for streaming response
                        try:
                            v_holders = visual_service.plan_and_create_placeholders(
                                db=save_db,
                                user_id=str(current_user.id),
                                chat_id=str(chat.id),
                                message_id=str(assistant_msg.id),
                                query=query,
                                answer_text=full_answer,
                                evidence_text="",
                                chat_history_context="",
                                memory_context="",
                            )
                            event["visuals"] = v_holders
                            # Trigger background rendering
                            for vp in v_holders:
                                import asyncio
                                asyncio.create_task(
                                    visual_service.render_visual_async(
                                        visual_id=vp["visual_id"],
                                        user_id=str(current_user.id),
                                        spec=vp.get("spec"),
                                    )
                                )
                        except Exception as v_err:
                            save_db.rollback()
                            logger.warning(f"Visual planning on stream done failed: {v_err}")

                # SSE Event Formats:
                # 1. Main JSON payload: data: {"type": ...}\n\n
                yield f"data: {json.dumps(event)}\n\n"

        except Exception as e:
            logger.error(f"Streaming generation error: {e}", exc_info=True)
            err_event = {
                "type": "error",
                "message": "Generation interrupted. Please try again."
            }
            yield f"data: {json.dumps(err_event)}\n\n"

        finally:
            # If aborted/interrupted before normal 'done' event, persist partial answer
            if not done_payload and accumulated_text.strip():
                try:
                    partial_msg = Message(
                        chat_id=chat_id,
                        role="assistant",
                        content=accumulated_text.strip(),
                        source_type="interrupted",
                        grounding_score=None
                    )
                    save_db.add(partial_msg)
                    save_db.commit()
                    logger.info(f"Persisted partially generated response ({len(accumulated_text)} chars) for chat {chat_id}")
                except Exception as save_err:
                    logger.error(f"Failed to persist partial interrupted message: {save_err}")
            save_db.close()
            logger.info(
                "chat_stream_complete request_id=%s total_backend_ms=%.2f completed=%s",
                request_id or "unavailable",
                (time.perf_counter() - response_started_at) * 1000,
                bool(done_payload)
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Request-ID": request_id or str(uuid.uuid4())
        }
    )


@router.post("/{message_id}/feedback", response_model=MessageFeedbackResponse)
def submit_message_feedback(
    chat_id: str,
    message_id: str,
    feedback_in: MessageFeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Save thumbs up or thumbs down feedback on an assistant message."""
    verify_chat_ownership(chat_id, current_user.id, db)
    msg = db.query(Message).filter(Message.id == message_id, Message.chat_id == chat_id).first()
    if not msg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    msg.feedback = feedback_in.rating
    if feedback_in.comment is not None:
        msg.feedback_comment = feedback_in.comment
    db.commit()

    return MessageFeedbackResponse(
        message_id=msg.id,
        feedback=msg.feedback,
        feedback_comment=msg.feedback_comment,
        status="success"
    )
