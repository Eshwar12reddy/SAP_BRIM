from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict
from backend.app.schemas.message import MessageResponse

class ChatCreate(BaseModel):
    title: Optional[str] = Field(default="New SAP Chat", max_length=255)
    is_temporary: Optional[bool] = False

class ChatUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    is_pinned: Optional[bool] = None
    is_archived: Optional[bool] = None

class ChatResponse(BaseModel):
    id: str
    user_id: str
    title: str
    is_pinned: bool = False
    is_archived: bool = False
    is_temporary: bool = False
    created_at: datetime
    updated_at: datetime
    messages: List[MessageResponse] = []

    model_config = ConfigDict(from_attributes=True)

class ChatListItem(BaseModel):
    id: str
    user_id: str
    title: str
    is_pinned: bool = False
    is_archived: bool = False
    is_temporary: bool = False
    created_at: datetime
    updated_at: datetime
    message_count: int = 0

    model_config = ConfigDict(from_attributes=True)
