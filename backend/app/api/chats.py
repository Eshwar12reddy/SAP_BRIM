from typing import List, Optional
from datetime import datetime, timezone
import json
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response, UploadFile, File
from fastapi.responses import FileResponse
import pymupdf
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.app.database import get_db
from backend.app.models.user import User
from backend.app.models.chat import Chat
from backend.app.models.message import Message
from backend.app.models.attachment import ChatAttachment
from backend.app.schemas.chat import ChatCreate, ChatUpdate, ChatResponse, ChatListItem
from backend.app.security.auth import get_current_user
from backend.app.services.vision_service import vision_service, strip_exif_metadata
from backend.app.config import BASE_DIR, settings

router = APIRouter(prefix="/chats", tags=["Chats"])

@router.post("", response_model=ChatResponse, status_code=status.HTTP_201_CREATED)
def create_chat(
    chat_in: ChatCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    chat = Chat(
        user_id=current_user.id,
        title=chat_in.title or "New SAP Chat",
        is_temporary=bool(chat_in.is_temporary),
    )
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return ChatResponse.model_validate(chat)

@router.get("", response_model=List[ChatListItem])
def list_chats(
    search: Optional[str] = Query(None, description="Search chats by title"),
    include_archived: bool = Query(False, description="Include archived chats"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = (
        db.query(
            Chat.id,
            Chat.user_id,
            Chat.title,
            Chat.is_pinned,
            Chat.is_archived,
            Chat.is_temporary,
            Chat.created_at,
            Chat.updated_at,
            func.count(Message.id).label("message_count")
        )
        .outerjoin(Message, Message.chat_id == Chat.id)
        .filter(Chat.user_id == current_user.id)
        .filter(Chat.is_temporary == False)
    )

    if not include_archived:
        query = query.filter(Chat.is_archived == False)

    if search:
        query = query.filter(Chat.title.ilike(f"%{search}%"))

    results = (
        query.group_by(Chat.id)
        .order_by(Chat.updated_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [
        ChatListItem(
            id=r.id,
            user_id=r.user_id,
            title=r.title,
            is_pinned=r.is_pinned,
            is_archived=r.is_archived,
            is_temporary=r.is_temporary,
            created_at=r.created_at,
            updated_at=r.updated_at,
            message_count=r.message_count
        )
        for r in results
    ]

@router.get("/{chat_id}", response_model=ChatResponse)
def get_chat(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Strictly query by both chat_id and authenticated user_id to prevent enumeration or cross-user leaks
    chat = db.query(Chat).filter(
        Chat.id == chat_id,
        Chat.user_id == current_user.id
    ).first()

    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found"
        )

    msgs = []
    for msg in chat.messages:
        c_list = [
            {
                "id": c.id,
                "document": c.document_name,
                "page": c.page_number,
                "section": c.section,
                "score": c.similarity_score,
                "snippet": c.citation_text,
            }
            for c in getattr(msg, "citations", [])
        ]
        w_list = [
            {
                "id": w.id,
                "title": w.title,
                "url": w.url,
                "domain": w.domain,
                "snippet": w.snippet,
            }
            for w in getattr(msg, "web_sources", [])
        ]
        a_list = [a.to_dict() for a in getattr(msg, "attachments", [])]
        msgs.append({
            "id": msg.id,
            "chat_id": msg.chat_id,
            "role": msg.role,
            "content": msg.content,
            "source_type": msg.source_type,
            "grounding_score": msg.grounding_score,
            "created_at": msg.created_at,
            "citations": c_list,
            "web_sources": w_list,
            "attachments": a_list,
            "feedback": msg.feedback,
            "feedback_comment": msg.feedback_comment,
        })

    return ChatResponse(
        id=chat.id,
        user_id=chat.user_id,
        title=chat.title,
        is_pinned=chat.is_pinned,
        is_archived=chat.is_archived,
        is_temporary=chat.is_temporary,
        created_at=chat.created_at,
        updated_at=chat.updated_at,
        messages=msgs,
    )

@router.patch("/{chat_id}", response_model=ChatResponse)
def update_chat(
    chat_id: str,
    chat_in: ChatUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    chat = db.query(Chat).filter(
        Chat.id == chat_id,
        Chat.user_id == current_user.id
    ).first()

    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found"
        )

    if chat_in.title is not None:
        chat.title = chat_in.title.strip()
    if chat_in.is_pinned is not None:
        chat.is_pinned = chat_in.is_pinned
    if chat_in.is_archived is not None:
        chat.is_archived = chat_in.is_archived
    chat.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(chat)
    return ChatResponse.model_validate(chat)

@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    chat = db.query(Chat).filter(
        Chat.id == chat_id,
        Chat.user_id == current_user.id
    ).first()

    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found"
        )

    db.delete(chat)
    db.commit()
    return None


@router.get("/{chat_id}/export")
def export_chat(
    chat_id: str,
    format: str = Query("markdown", description="Export format: 'markdown', 'json', or 'txt'"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Secure, permission-controlled conversation export.
    Supports markdown (.md), JSON (.json), and plain text (.txt) exports.
    """
    chat = db.query(Chat).filter(
        Chat.id == chat_id,
        Chat.user_id == current_user.id
    ).first()

    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found"
        )

    messages = (
        db.query(Message)
        .filter(Message.chat_id == chat.id)
        .order_by(Message.created_at.asc())
        .all()
    )

    clean_title = "".join(c for c in chat.title if c.isalnum() or c in (" ", "_", "-")).rstrip()[:40] or "chat"
    file_base = clean_title.replace(" ", "_")

    if format.lower() == "json":
        import json
        data = {
            "chat_id": chat.id,
            "title": chat.title,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "message_count": len(messages),
            "messages": [
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "source_type": m.source_type,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in messages
            ]
        }
        content = json.dumps(data, indent=2, ensure_ascii=False)
        filename = f"{file_base}_{chat.id[:8]}.json"
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    elif format.lower() == "txt":
        lines = [
            f"CLYPTUS.AI CONVERSATION EXPORT",
            f"Title: {chat.title}",
            f"Exported: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"Messages: {len(messages)}",
            "=" * 60,
            ""
        ]
        for m in messages:
            speaker = "User" if m.role == "user" else "Clyptus.AI Assistant"
            lines.append(f"[{speaker}]")
            lines.append(m.content.strip())
            lines.append("-" * 40)
            lines.append("")
        content = "\n".join(lines)
        filename = f"{file_base}_{chat.id[:8]}.txt"
        return Response(
            content=content,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    else:
        # Default: Markdown
        lines = [
            f"# {chat.title}",
            f"*Exported on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} from Clyptus.AI*",
            "",
            "---",
            ""
        ]
        for m in messages:
            if m.role == "user":
                lines.append(f"### 👤 User:\n{m.content.strip()}\n")
            else:
                source_label = f" *({m.source_type})*" if m.source_type else ""
                lines.append(f"### 🤖 Clyptus.AI Assistant{source_label}:\n{m.content.strip()}\n")
            lines.append("---\n")
        content = "\n".join(lines)
        filename = f"{file_base}_{chat.id[:8]}.md"
        return Response(
            content=content,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )


async def _process_and_save_attachment(
    chat_id: str,
    file: UploadFile,
    current_user: User,
    db: Session
) -> dict:
    filename = file.filename or "attachment.png"
    ext = Path(filename).suffix.lower()

    image_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".svg", ".gif"}
    doc_exts = {".pdf", ".txt", ".md", ".log", ".json", ".csv", ".xml", ".abap", ".sql"}
    allowed_exts = image_exts | doc_exts

    if ext not in allowed_exts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Allowed types: {', '.join(sorted(allowed_exts))}"
        )

    contents = await file.read()
    file_type = "image" if ext in image_exts else "document"

    if file_type == "image":
        max_image_mb = getattr(settings, "MAX_IMAGE_MB", 5)
        max_size = max_image_mb * 1024 * 1024
        if len(contents) > max_size:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File size exceeds maximum allowed limit of {max_image_mb} MB."
            )
        # Strip EXIF metadata from screenshot
        contents = strip_exif_metadata(contents)
    else:
        max_size = 10 * 1024 * 1024  # 10 MB limit for text/docs
        if len(contents) > max_size:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File size exceeds maximum allowed limit of 10 MB."
            )

    # User-isolated secure storage directory
    upload_dir = BASE_DIR / "media" / "attachments" / str(current_user.id) / str(chat_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    unique_file_id = str(uuid.uuid4())
    safe_disk_filename = f"{unique_file_id}_{Path(filename).name}"
    saved_path = upload_dir / safe_disk_filename

    with open(saved_path, "wb") as f:
        f.write(contents)

    mime_type = file.content_type or ("image/png" if file_type == "image" else "application/octet-stream")

    extracted_text = ""
    vision_metadata = {}

    if file_type == "image":
        vision_res = vision_service.parse_sap_screenshot_structured(
            image_bytes=contents,
            mime_type=mime_type,
            user_query="",
            conversation_context="",
        )
        extracted_text = vision_res.get("text", "")
        vision_metadata = {
            "is_sap": vision_res.get("is_sap", True),
            "screen_or_app": vision_res.get("screen_or_app"),
            "transaction_code": vision_res.get("transaction_code"),
            "module": vision_res.get("module"),
            "message_class_and_number": vision_res.get("message_class_and_number"),
            "error_text": vision_res.get("error_text"),
            "visible_fields_and_values": vision_res.get("visible_fields_and_values", {}),
            "readable": vision_res.get("readable", True),
            "confidence": vision_res.get("confidence", 1.0),
            "screen_type": vision_res.get("screen_type"),
            "detected_error": vision_res.get("detected_error"),
            "is_unclear": vision_res.get("is_unclear", False),
            "has_credentials": vision_res.get("has_credentials", False),
            "mermaid_code": vision_res.get("mermaid_code"),
        }
    elif ext == ".pdf":
        try:
            doc = pymupdf.open(stream=contents, filetype="pdf")
            pages_text = []
            for page_idx in range(min(len(doc), 50)):
                page = doc[page_idx]
                t = page.get_text("text") or ""
                if t.strip():
                    pages_text.append(f"--- Page {page_idx + 1} ---\n{t.strip()}")
            doc.close()
            extracted_text = "\n\n".join(pages_text)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Could not parse PDF content: {str(e)}"
            )
    else:
        try:
            extracted_text = contents.decode("utf-8", errors="replace")
        except Exception:
            extracted_text = contents.decode("latin-1", errors="replace")

    cleaned = "\n".join(line for line in extracted_text.splitlines() if line.strip())

    attachment = ChatAttachment(
        id=unique_file_id,
        chat_id=chat_id,
        user_id=current_user.id,
        filename=filename,
        file_type=file_type,
        mime_type=mime_type,
        file_path=str(saved_path),
        size_bytes=len(contents),
        extracted_text=cleaned,
        vision_metadata=json.dumps(vision_metadata),
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)

    preview_url = f"/api/chats/{chat_id}/attachments/{attachment.id}"

    return {
        "id": attachment.id,
        "attachment_id": attachment.id,
        "filename": filename,
        "file_type": file_type,
        "mime_type": mime_type,
        "preview_url": preview_url,
        "size_bytes": len(contents),
        "char_count": len(cleaned),
        "extracted_text": cleaned[:12000],
        "snippet": cleaned[:300].strip(),
        "vision_metadata": vision_metadata,
    }


@router.post("/{chat_id}/attachment")
async def upload_chat_attachment(
    chat_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Accepts an uploaded SAP screenshot or document.
    Stores file securely under user-isolated directory, strips EXIF,
    runs OCR/vision inspection, and returns structured attachment metadata.
    """
    chat = db.query(Chat).filter(
        Chat.id == chat_id,
        Chat.user_id == current_user.id
    ).first()

    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found"
        )

    return await _process_and_save_attachment(chat_id, file, current_user, db)


@router.post("/{chat_id}/attachments")
async def upload_chat_attachments(
    chat_id: str,
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Accepts up to 3 uploaded SAP screenshots or documents (batch).
    Validates count, size, and extensions, strips EXIF, runs vision analysis,
    and returns a list of created attachment objects.
    """
    chat = db.query(Chat).filter(
        Chat.id == chat_id,
        Chat.user_id == current_user.id
    ).first()

    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found"
        )

    max_count = getattr(settings, "MAX_IMAGES_PER_MESSAGE", 3)
    if len(files) > max_count:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {max_count} images allowed per message."
        )

    results = []
    for f in files:
        res = await _process_and_save_attachment(chat_id, f, current_user, db)
        results.append(res)
    return results


@router.get("/{chat_id}/attachments/{attachment_id}")
def get_chat_attachment(
    chat_id: str,
    attachment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Secure, user-isolated endpoint to retrieve or preview an uploaded chat attachment.
    Enforces strict ownership checks: never serves an attachment to unauthorized users.
    """
    # 1. Verify chat ownership
    chat = db.query(Chat).filter(
        Chat.id == chat_id,
        Chat.user_id == current_user.id
    ).first()

    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found"
        )

    # 2. Verify attachment ownership
    attachment = db.query(ChatAttachment).filter(
        ChatAttachment.id == attachment_id,
        ChatAttachment.chat_id == chat_id,
        ChatAttachment.user_id == current_user.id
    ).first()

    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found"
        )

    file_path = Path(attachment.file_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment file missing from disk"
        )

    return FileResponse(
        path=str(file_path),
        media_type=attachment.mime_type,
        filename=attachment.filename
    )

