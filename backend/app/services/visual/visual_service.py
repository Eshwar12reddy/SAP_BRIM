"""
Visual Service Orchestrator.
Coordinates planning, background SVG / generative rendering, user-isolated storage, caching, and revisions.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.database import SessionLocal
from backend.app.models.visual import VisualAsset
from backend.app.services.visual.svg_renderer import render_svg
from backend.app.services.visual.provider_adapter import get_image_provider_adapter
from backend.app.services.visual.visual_planner import visual_planner
from backend.app.services.visual.visual_cache import (
    compute_cache_key,
    get_cached_visual,
    check_user_daily_quota,
)

logger = logging.getLogger(__name__)


class VisualService:
    """Manages visual assets creation, rendering, storage, and retrieval."""

    def plan_and_create_placeholders(
        self,
        db: Session,
        user_id: Any,
        chat_id: Any,
        message_id: Optional[Any] = None,
        query: str = "",
        answer_text: str = "",
        evidence_text: str = "",
        chat_history_context: str = "",
        memory_context: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Plans visuals for a message. If planned, stores pending VisualAsset records in DB
        and returns placeholder dicts for immediate delivery to the client.
        Strictly validates chat existence and user ownership before persistence.
        """
        if not settings.ENABLE_VISUAL_GENERATION:
            return []

        u_id = str(user_id)
        c_id = str(chat_id)
        m_id = str(message_id) if message_id else None

        # Check daily quota
        within_quota = check_user_daily_quota(db, u_id)
        if not within_quota:
            logger.warning(f"User {u_id} exceeded daily visual generation quota.")
            return []

        # Validate that chat exists and belongs to the authenticated user
        from backend.app.models.chat import Chat
        chat = db.query(Chat).filter(Chat.id == c_id, Chat.user_id == u_id).first()
        if not chat:
            logger.warning(f"Visual planning skipped: Chat {c_id} not found or does not belong to user {u_id}.")
            return []

        # Validate message if supplied
        if m_id:
            from backend.app.models.message import Message
            msg = db.query(Message).filter(Message.id == m_id, Message.chat_id == c_id).first()
            if not msg:
                logger.warning(f"Visual planning: Message {m_id} not found for chat {c_id}; clearing message_id.")
                m_id = None

        specs = visual_planner.plan_visual_specs(
            query=query,
            answer_text=answer_text,
            evidence_text=evidence_text,
            chat_history_context=chat_history_context,
            memory_context=memory_context,
        )

        if not specs:
            return []

        placeholders = []
        try:
            for spec in specs:
                cache_key = compute_cache_key(u_id, spec)
                is_generative = spec.get("is_generative", False)
                visual_type = spec.get("type", "flow_diagram")
                title = spec.get("title", "Visual Illustration")
                caption = spec.get("caption", "AI-generated illustration - not an SAP screenshot.")

                # Create VisualAsset record with status 'pending'
                asset = VisualAsset(
                    user_id=u_id,
                    chat_id=c_id,
                    message_id=m_id,
                    visual_type=visual_type,
                    title=title,
                    caption=caption,
                    step_id=spec.get("step_id"),
                    status="pending",
                    spec_json=json.dumps(spec),
                    cache_key=cache_key,
                    is_generative=is_generative,
                )
                db.add(asset)
                db.flush()  # populate asset.id

                placeholders.append({
                    "visual_id": asset.id,
                    "type": visual_type,
                    "title": title,
                    "caption": caption,
                    "step_id": asset.step_id,
                    "status": "pending",
                    "is_generative": is_generative,
                    "spec": spec,
                })

            db.commit()
            return placeholders
        except Exception as exc:
            db.rollback()
            logger.error(f"Failed to create visual placeholders in database: {exc}", exc_info=True)
            return []

    async def render_visual_async(
        self,
        visual_id: Any,
        user_id: Any,
        spec: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Background rendering task. Generates SVG or image file, writes to disk, and updates DB.
        Guarantees isolation: asset path is namespaced under media/visuals/{user_id}/.
        """
        v_id = str(visual_id)
        u_id = str(user_id)
        with SessionLocal() as db:
            try:
                asset = (
                    db.query(VisualAsset)
                    .filter(VisualAsset.id == v_id, VisualAsset.user_id == u_id)
                    .first()
                )

                if not asset:
                    logger.error(f"VisualAsset {v_id} for user {u_id} not found.")
                    return

                if asset.status == "completed":
                    return

                # Load spec from asset if not supplied
                if not spec and asset.spec_json:
                    spec = json.loads(asset.spec_json)
                elif not spec:
                    spec = {"type": "flow_diagram", "title": asset.title, "caption": asset.caption}

                # Ensure storage directory exists
                user_dir = settings.VISUAL_STORAGE_DIR / u_id
                user_dir.mkdir(parents=True, exist_ok=True)

                # Check if exact cache match already exists for this user
                if asset.cache_key:
                    cached = get_cached_visual(db, u_id, asset.cache_key)
                    if cached and cached.file_path and Path(cached.file_path).exists():
                        asset.file_path = cached.file_path
                        asset.mime_type = cached.mime_type
                        asset.status = "completed"
                        db.commit()
                        logger.info(f"Reused cached visual for user {u_id}, asset {v_id}")
                        return

                # Path B: Generative image (if requested and enabled)
                if asset.is_generative and settings.ENABLE_GENERATIVE_IMAGES:
                    adapter = get_image_provider_adapter()
                    prompt = spec.get("prompt") or spec.get("title", "")
                    img_bytes = await adapter.generate_image(prompt)
                    if img_bytes:
                        out_path = user_dir / f"{v_id}.png"
                        out_path.write_bytes(img_bytes)
                        asset.file_path = str(out_path)
                        asset.mime_type = "image/png"
                        asset.status = "completed"
                        db.commit()
                        return
                    else:
                        logger.warning(f"Path B generative failed for {v_id}; falling back to Path A.")

                # Path A: Structured SVG rendering
                svg_content = render_svg(spec)
                out_path = user_dir / f"{v_id}.svg"
                out_path.write_text(svg_content, encoding="utf-8")

                asset.file_path = str(out_path)
                asset.mime_type = "image/svg+xml"
                asset.status = "completed"
                db.commit()
                logger.info(f"Successfully rendered visual {v_id} as SVG for user {u_id}")

            except Exception as e:
                logger.error(f"Failed to render visual {v_id}: {e}", exc_info=True)
                try:
                    asset = (
                        db.query(VisualAsset)
                        .filter(VisualAsset.id == v_id, VisualAsset.user_id == u_id)
                        .first()
                    )
                    if asset:
                        asset.status = "failed"
                        asset.error_message = str(e)[:250]
                        db.commit()
                except Exception as inner_e:
                    logger.error(f"Failed to record failure status for visual {v_id}: {inner_e}")

    def get_visual_asset_file(
        self,
        db: Session,
        visual_id: Any,
        user_id: Any,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves visual file with strict ownership check.
        Returns dict with file_path and mime_type, or None if not found/unauthorized.
        """
        v_id = str(visual_id)
        u_id = str(user_id)
        asset = (
            db.query(VisualAsset)
            .filter(VisualAsset.id == v_id, VisualAsset.user_id == u_id)
            .first()
        )

        if not asset or asset.status != "completed" or not asset.file_path:
            return None

        p = Path(asset.file_path)
        if not p.exists():
            logger.error(f"File {asset.file_path} for visual {v_id} missing on disk.")
            return None

        return {
            "file_path": str(p),
            "mime_type": asset.mime_type or "image/svg+xml",
            "title": asset.title,
            "caption": asset.caption,
            "status": asset.status,
        }

    def get_visual_meta(
        self,
        db: Session,
        visual_id: Any,
        user_id: Any,
    ) -> Optional[VisualAsset]:
        """Fetches visual metadata with strict ownership check."""
        return (
            db.query(VisualAsset)
            .filter(VisualAsset.id == str(visual_id), VisualAsset.user_id == str(user_id))
            .first()
        )

    def revise_visual(
        self,
        db: Session,
        visual_id: Any,
        user_id: Any,
        instruction: str,
    ) -> Optional[VisualAsset]:
        """
        Creates a revised version of an existing visual asset.
        """
        v_id = str(visual_id)
        u_id = str(user_id)
        original = (
            db.query(VisualAsset)
            .filter(VisualAsset.id == v_id, VisualAsset.user_id == u_id)
            .first()
        )

        if not original or not original.spec_json:
            return None

        orig_spec = json.loads(original.spec_json)
        revised_spec = visual_planner._simplify_spec(orig_spec, instruction)

        cache_key = compute_cache_key(u_id, revised_spec)
        new_asset = VisualAsset(
            user_id=u_id,
            chat_id=original.chat_id,
            message_id=original.message_id,
            visual_type=revised_spec.get("type", original.visual_type),
            title=revised_spec.get("title", f"Revised: {original.title}"),
            caption=revised_spec.get("caption", original.caption),
            step_id=original.step_id,
            status="pending",
            spec_json=json.dumps(revised_spec),
            cache_key=cache_key,
            is_generative=False,
        )
        db.add(new_asset)
        db.commit()
        db.refresh(new_asset)
        return new_asset


visual_service = VisualService()
