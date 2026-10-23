import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy import Column, String, Integer, DateTime, Text, inspect
from sqlalchemy.orm import relationship
from backend.app.database import Base

logger = logging.getLogger(__name__)





class Document(Base):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    filename = Column(String(255), unique=True, index=True, nullable=False)
    title = Column(String(255), nullable=False)
    file_hash = Column(String(64), index=True, nullable=False)
    version = Column(String(50), default="1.0", nullable=False)
    page_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Ingestion status and tracking columns
    status = Column(String(50), default="completed", nullable=True, index=True)
    total_pages = Column(Integer, default=0, nullable=True)
    extracted_chars = Column(Integer, default=0, nullable=True)
    total_chunks = Column(Integer, default=0, nullable=True)
    embedded_chunks = Column(Integer, default=0, nullable=True)
    error_message = Column(Text, nullable=True)
    processing_started_at = Column(DateTime, nullable=True)
    processing_completed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=True)

    # Enterprise Admin Portal Additive Columns
    category = Column(String(100), default="General", nullable=True)
    description = Column(Text, nullable=True)
    size_bytes = Column(Integer, default=0, nullable=True)

    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "filename": self.filename,
            "title": self.title,
            "file_hash": self.file_hash,
            "version": self.version,
            "page_count": self.page_count or 0,
            "total_pages": self.total_pages or self.page_count or 0,
            "extracted_chars": self.extracted_chars or 0,
            "total_chunks": self.total_chunks or 0,
            "embedded_chunks": self.embedded_chunks or 0,
            "status": self.status or "completed",
            "error_message": self.error_message,
            "processing_started_at": self.processing_started_at.isoformat() if self.processing_started_at else None,
            "processing_completed_at": self.processing_completed_at.isoformat() if self.processing_completed_at else None,
            "category": self.category or "General",
            "description": self.description,
            "size_bytes": self.size_bytes or 0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
