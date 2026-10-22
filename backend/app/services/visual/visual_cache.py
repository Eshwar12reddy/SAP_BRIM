"""
User-scoped caching and quota verification for visual assets.
Never shares cache entries across users.
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Union
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.models.visual import VisualAsset
from backend.app.config import settings

logger = logging.getLogger(__name__)

RENDERER_VERSION = "svg-v1.0"


def compute_cache_key(
    user_id: Union[str, int],
    spec_or_prompt: Union[Dict[str, Any], str],
    version: str = RENDERER_VERSION,
) -> str:
    """
    Computes a deterministic SHA256 hash strictly scoped to user_id.
    Cache key = hash of (user_id, normalized spec/prompt, renderer/provider version).
    """
    if isinstance(spec_or_prompt, dict):
        normalized = json.dumps(spec_or_prompt, sort_keys=True, separators=(",", ":"))
    else:
        normalized = str(spec_or_prompt).strip().lower()

    payload = f"{str(user_id)}:{normalized}:{version}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def get_cached_visual(
    db: Session,
    user_id: Union[str, int],
    cache_key: str,
) -> Optional[VisualAsset]:
    """
    Lookup previously successfully rendered visual for the same user with exact cache_key match.
    Never returns visuals belonging to another user.
    """
    if not cache_key:
        return None

    return (
        db.query(VisualAsset)
        .filter(
            VisualAsset.user_id == str(user_id),
            VisualAsset.cache_key == cache_key,
            VisualAsset.status == "completed",
        )
        .order_by(VisualAsset.created_at.desc())
        .first()
    )


def check_user_daily_quota(
    db: Session,
    user_id: Union[str, int],
) -> bool:
    """
    Returns True if user is within their daily visual quota, False if exceeded.
    """
    since = datetime.now(timezone.utc) - timedelta(days=1)
    count = (
        db.query(func.count(VisualAsset.id))
        .filter(
            VisualAsset.user_id == str(user_id),
            VisualAsset.created_at >= since,
        )
        .scalar()
        or 0
    )
    return count < settings.VISUAL_DAILY_QUOTA_PER_USER
