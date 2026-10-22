"""
Visual endpoints for retrieving metadata, streaming assets, and requesting revisions.
Strict user-level isolation and authentication enforced on all endpoints.
"""

import logging
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.user import User
from backend.app.models.visual import VisualAsset
from backend.app.schemas.visual import VisualResponse, VisualRegenerateRequest
from backend.app.security.auth import get_current_user
from backend.app.services.visual.visual_service import visual_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/visuals", tags=["Visuals"])


@router.get("/{visual_id}", response_model=VisualResponse)
def get_visual_metadata(
    visual_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve metadata for a visual asset.
    Strictly verifies user ownership.
    """
    asset = visual_service.get_visual_meta(db, visual_id, current_user.id)
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Visual asset not found or access denied.",
        )

    asset_url = f"/api/visuals/{asset.id}/asset" if asset.status == "completed" else None
    return VisualResponse(
        id=asset.id,
        user_id=asset.user_id,
        chat_id=asset.chat_id,
        message_id=asset.message_id,
        visual_type=asset.visual_type,
        title=asset.title,
        caption=asset.caption,
        step_id=asset.step_id,
        status=asset.status,
        error_message=asset.error_message,
        mime_type=asset.mime_type,
        asset_url=asset_url,
        is_generative=asset.is_generative,
        created_at=asset.created_at,
    )


@router.get("/{visual_id}/asset")
def get_visual_asset_file(
    visual_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Stream visual asset (SVG / PNG) with strict ownership validation.
    Prevents cross-user data leakage.
    """
    file_info = visual_service.get_visual_asset_file(db, visual_id, current_user.id)
    if not file_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Visual asset not found, unavailable, or access denied.",
        )

    file_path = file_info["file_path"]
    mime_type = file_info["mime_type"]

    return FileResponse(
        path=file_path,
        media_type=mime_type,
        filename=Path(file_path).name,
        headers={
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/{visual_id}/regenerate", response_model=VisualResponse)
def regenerate_visual(
    visual_id: str,
    body: VisualRegenerateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Request revision or regeneration of a visual (e.g. 'make it simpler', 'add FI-CA').
    """
    new_asset = visual_service.revise_visual(
        db=db,
        visual_id=visual_id,
        user_id=current_user.id,
        instruction=body.instruction,
    )

    if not new_asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Original visual not found or cannot be revised.",
        )

    # Queue background rendering for the new revised asset
    background_tasks.add_task(
        visual_service.render_visual_async,
        visual_id=new_asset.id,
        user_id=current_user.id,
    )

    return VisualResponse(
        id=new_asset.id,
        user_id=new_asset.user_id,
        chat_id=new_asset.chat_id,
        message_id=new_asset.message_id,
        visual_type=new_asset.visual_type,
        title=new_asset.title,
        caption=new_asset.caption,
        step_id=new_asset.step_id,
        status="pending",
        error_message=None,
        mime_type=new_asset.mime_type,
        asset_url=None,
        is_generative=new_asset.is_generative,
        created_at=new_asset.created_at,
    )
