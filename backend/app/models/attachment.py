import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.database import Base


class ChatAttachment(Base):
    """
    Stores user-uploaded documents and screenshots tied securely to a conversation and user.
    Supports user isolation, OCR / vision extraction, and message linkage.
    """
    __tablename__ = "chat_attachments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id = Column(String(36), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = Column(String(36), ForeignKey("messages.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    filename = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False, default="document")  # "image" or "document"
    mime_type = Column(String(100), nullable=False)
    file_path = Column(String(500), nullable=False)
    size_bytes = Column(Integer, nullable=False, default=0)
    extracted_text = Column(Text, nullable=True)
    vision_metadata = Column(Text, nullable=True)  # JSON-encoded metadata (dimensions, screen_type, observations)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    chat = relationship("Chat", back_populates="attachments")
    message = relationship("Message", back_populates="attachments")
    user = relationship("User", back_populates="attachments")

    @property
    def preview_url(self) -> str:
        return f"/api/chats/{self.chat_id}/attachments/{self.id}"

    def to_dict(self):
        import json
        vm = {}
        if self.vision_metadata:
            try:
                vm = json.loads(self.vision_metadata)
            except Exception:
                vm = {}
        return {
            "id": self.id,
            "filename": self.filename,
            "file_type": self.file_type,
            "mime_type": self.mime_type,
            "preview_url": self.preview_url,
            "size_bytes": self.size_bytes,
            "extracted_text": self.extracted_text,
            "vision_metadata": vm,
        }

