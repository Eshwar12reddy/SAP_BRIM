import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, Text
from sqlalchemy.orm import relationship
from backend.app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    role = Column(String(50), default="consultant", nullable=False)
    memory_enabled = Column(Boolean, default=True, nullable=False)
    custom_instructions_about_user = Column(Text, nullable=True)
    custom_instructions_how_to_respond = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    chats = relationship("Chat", back_populates="user", cascade="all, delete-orphan")
    conversation_memories = relationship("ConversationMemory", back_populates="user", cascade="all, delete-orphan")
    sap_scenario_memories = relationship("SAPScenarioMemory", back_populates="user", cascade="all, delete-orphan")
    conversation_summaries = relationship("ConversationSummary", back_populates="user", cascade="all, delete-orphan")
    visual_assets = relationship("VisualAsset", back_populates="user", cascade="all, delete-orphan")
    attachments = relationship("ChatAttachment", back_populates="user", cascade="all, delete-orphan")
