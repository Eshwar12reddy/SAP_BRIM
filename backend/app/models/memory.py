import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Float, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from backend.app.database import Base
from backend.app.models.chunk import EmbeddingVector

class ConversationMemory(Base):
    """
    Persistent cross-chat memory facts, preferences, environment details, and technical assumptions.
    Carries explicit provenance/trust label.
    """
    __tablename__ = "conversation_memories"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    memory_type = Column(String(50), nullable=False, default="fact")  # 'preference', 'environment', 'assumption', 'fact', 'issue', 'solution'
    summary = Column(Text, nullable=False)
    entities = Column(Text, nullable=True)  # JSON-encoded string
    provenance = Column(String(50), nullable=False, default="user_stated")  # 'user_stated', 'user_confirmed', 'assistant_hypothesis', 'kb_verified'
    status = Column(String(50), nullable=False, default="active")  # 'active', 'superseded', 'resolved', 'expired'
    confidence = Column(Float, nullable=False, default=1.0)
    embedding = Column(EmbeddingVector, nullable=True)
    content_hash = Column(String(64), nullable=True, index=True)
    superseded_by = Column(String(36), nullable=True)
    source_chat_id = Column(String(36), ForeignKey("chats.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    last_accessed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=True)
    expires_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="conversation_memories")
    chat = relationship("Chat")

    __table_args__ = (
        Index("ix_conv_mem_user_updated", "user_id", "updated_at"),
        Index("ix_conv_mem_user_status", "user_id", "status"),
    )


class SAPScenarioMemory(Base):
    """
    Structured SAP BRIM incident/scenario record spanning multi-turn or cross-chat diagnostics.
    """
    __tablename__ = "sap_scenario_memories"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    scenario_title = Column(String(255), nullable=False)
    symptoms = Column(Text, nullable=True)
    affected_modules = Column(Text, nullable=True)  # JSON-encoded list: e.g. ["SOM", "FI-CA"]
    entities = Column(Text, nullable=True)  # JSON-encoded dict
    investigation_steps = Column(Text, nullable=True)  # JSON-encoded list
    confirmed_findings = Column(Text, nullable=True)  # JSON-encoded list
    attempted_solutions = Column(Text, nullable=True)  # JSON-encoded list
    unresolved_questions = Column(Text, nullable=True)  # JSON-encoded list
    hypotheses = Column(Text, nullable=True)  # JSON-encoded list
    status = Column(String(50), nullable=False, default="open")  # 'open', 'resolved', 'in_progress'
    embedding = Column(EmbeddingVector, nullable=True)
    source_chat_id = Column(String(36), ForeignKey("chats.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    last_accessed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=True)

    user = relationship("User", back_populates="sap_scenario_memories")
    chat = relationship("Chat")

    __table_args__ = (
        Index("ix_sap_scen_user_updated", "user_id", "updated_at"),
        Index("ix_sap_scen_user_status", "user_id", "status"),
    )


class ConversationSummary(Base):
    """
    Per-chat rolling summary and unresolved topics.
    """
    __tablename__ = "conversation_summaries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    chat_id = Column(String(36), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    summary = Column(Text, nullable=False)
    key_entities = Column(Text, nullable=True)  # JSON-encoded list
    unresolved_topics = Column(Text, nullable=True)  # JSON-encoded list
    embedding = Column(EmbeddingVector, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="conversation_summaries")
    chat = relationship("Chat")

    __table_args__ = (
        Index("ix_conv_sum_user_chat", "user_id", "chat_id"),
    )
