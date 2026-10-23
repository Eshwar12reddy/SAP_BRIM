from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class VisualItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    chat_id: str
    message_id: Optional[str] = None
    visual_type: str
    title: str
    caption: Optional[str] = None
    step_id: Optional[str] = None
    status: str = "pending"
    asset_url: Optional[str] = None
    mime_type: str = "image/svg+xml"
    is_generative: bool = False
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None


class VisualResponse(VisualItem):
    pass


class VisualRegenerateRequest(BaseModel):
    instruction: Optional[str] = Field(None, description="Optional revision instruction, e.g. 'make it simpler', 'add FI-CA'")
