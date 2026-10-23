import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Text,
    LargeBinary,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from backend.app.database import Base


class KBDocumentBinary(Base):
    """
    Stores original uploaded file bytes directly in PostgreSQL (BYTEA).
    Ensures zero dependency on local filesystem persistence when running in containerized environments.
    """
    __tablename__ = "kb_document_binaries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    file_bytes = Column(LargeBinary, nullable=False)
    file_size = Column(Integer, nullable=False, default=0)
    content_type = Column(String(100), nullable=False, default="application/octet-stream")
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "document_id": str(self.document_id),
            "file_size": self.file_size,
            "content_type": self.content_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AdminAuditLog(Base):
    """
    Enterprise audit trail logging every admin action (upload, replace, edit, reindex, delete).
    """
    __tablename__ = "admin_audit_log"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    admin_email = Column(String(255), nullable=False, index=True)
    action = Column(String(50), nullable=False, index=True)  # UPLOAD, REPLACE, EDIT_METADATA, REINDEX, DELETE, BULK_DELETE, DELETE_ALL
    target_id = Column(String(255), nullable=True)
    target_name = Column(String(255), nullable=True)
    details = Column(Text, nullable=True)  # Serialized JSON
    ip_address = Column(String(100), nullable=True)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "user_id": str(self.user_id) if self.user_id else None,
            "admin_email": self.admin_email,
            "action": self.action,
            "target_id": self.target_id,
            "target_name": self.target_name,
            "details": self.details,
            "ip_address": self.ip_address,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
