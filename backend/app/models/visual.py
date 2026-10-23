import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.database import Base


class VisualAsset(Base):
    __tablename__ = "visual_assets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    chat_id = Column(String(36), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = Column(String(36), ForeignKey("messages.id", ondelete="CASCADE"), nullable=True, index=True)

    visual_type = Column(String(50), nullable=False, default="flow_diagram")
    title = Column(String(255), nullable=False)
    caption = Column(Text, nullable=True)
    step_id = Column(String(50), nullable=True)  # e.g., "step-1", "step-2"
    status = Column(String(20), default="pending", nullable=False)  # pending, ready, failed
    error_message = Column(Text, nullable=True)

    mime_type = Column(String(50), default="image/svg+xml", nullable=False)
    file_path = Column(String(500), nullable=True)
    spec_json = Column(Text, nullable=True)
    cache_key = Column(String(64), index=True, nullable=True)
    is_generative = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="visual_assets")
    chat = relationship("Chat", back_populates="visual_assets")
    message = relationship("Message", back_populates="visual_assets")
