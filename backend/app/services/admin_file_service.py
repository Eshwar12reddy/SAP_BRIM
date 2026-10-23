import os
import re
import csv
import io
import uuid
import json
import hashlib
import logging
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple, BinaryIO

from fastapi import UploadFile, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text, func, desc, or_

from backend.app.config import settings
from backend.app.database import engine, SessionLocal
from backend.app.models.document import Document
from backend.app.models.chunk import DocumentChunk
from backend.app.models.user import User
from backend.app.models.admin_portal import KBDocumentBinary, AdminAuditLog
from backend.app.services.document_service import DocumentService
from backend.app.services.embedding_service import embedding_service
from backend.app.services.retrieval_service import retrieval_service

logger = logging.getLogger("admin_file_service")

# Permitted extensions and defaults
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown", ".csv"}
ADMIN_UPLOAD_MAX_MB = int(os.getenv("ADMIN_UPLOAD_MAX_MB", str(getattr(settings, "MAX_UPLOAD_SIZE_MB", 50))))
ADMIN_UPLOAD_MAX_FILES = int(os.getenv("ADMIN_UPLOAD_MAX_FILES", "25"))
STORE_ORIGINAL_FILE = os.getenv("STORE_ORIGINAL_FILE", "true").lower() in ("true", "1", "yes")

# Single lock for background worker execution to prevent thread collisions
_BACKGROUND_WORKER_LOCK = threading.Lock()


def ensure_admin_portal_schema():
    """
    Idempotent database migration executed automatically on service startup.
    Ensures kb_document_binaries and admin_audit_log exist, and adds additive columns to documents.
    """
    try:
        with engine.begin() as conn:
            # 1. Additive columns on 'documents'
            conn.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS category VARCHAR(100) DEFAULT 'General'"))
            conn.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS description TEXT"))
            conn.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS size_bytes INTEGER DEFAULT 0"))

            # 2. kb_document_binaries table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS kb_document_binaries (
                    id VARCHAR(36) PRIMARY KEY,
                    document_id VARCHAR(36) NOT NULL UNIQUE REFERENCES documents(id) ON DELETE CASCADE,
                    file_bytes BYTEA NOT NULL,
                    file_size INTEGER NOT NULL DEFAULT 0,
                    content_type VARCHAR(100) NOT NULL DEFAULT 'application/octet-stream',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_kb_document_binaries_doc_id ON kb_document_binaries(document_id)"))

            # 3. admin_audit_log table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS admin_audit_log (
                    id VARCHAR(36) PRIMARY KEY,
                    user_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
                    admin_email VARCHAR(255) NOT NULL,
                    action VARCHAR(50) NOT NULL,
                    target_id VARCHAR(255),
                    target_name VARCHAR(255),
                    details TEXT,
                    ip_address VARCHAR(100),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_admin_audit_log_email ON admin_audit_log(admin_email)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_admin_audit_log_action ON admin_audit_log(action)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_admin_audit_log_created_at ON admin_audit_log(created_at)"))

        logger.info("Admin portal schema checked and validated successfully.")
    except Exception as exc:
        logger.warning("Admin portal schema check encountered error (continuing if tables exist): %s", exc)


# Run schema check once on module load
ensure_admin_portal_schema()


class AdminFileService:
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitizes filename against path traversal, control chars, and weird characters."""
        clean_name = Path(filename).name
        clean_name = clean_name.replace("\x00", "").strip()
        clean_name = re.sub(r"[^\w\.\-\s]", "_", clean_name)
        clean_name = re.sub(r"\s+", " ", clean_name)
        if not clean_name or clean_name.startswith("."):
            clean_name = f"doc_{int(datetime.now(timezone.utc).timestamp())}_{clean_name}"
        return clean_name

    @staticmethod
    def validate_magic_bytes_and_mime(file_bytes: bytes, filename: str) -> Tuple[bool, str, Optional[str]]:
        """
        Validates magic bytes / MIME type using python-magic if available,
        with a deterministic pure-Python signature fallback.
        """
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            return False, "application/octet-stream", f"Unsupported file extension '{suffix}'. Permitted: {', '.join(sorted(ALLOWED_EXTENSIONS))}"

        # 1. Try python-magic if available
        try:
            import magic
            mime = magic.from_buffer(file_bytes[:2048], mime=True)
            if suffix == ".pdf" and "pdf" in mime.lower():
                return True, mime, None
            if suffix == ".docx" and ("officedocument" in mime.lower() or "zip" in mime.lower()):
                return True, mime, None
            if suffix in {".txt", ".md", ".markdown", ".csv"} and ("text" in mime.lower() or "plain" in mime.lower() or "csv" in mime.lower() or "empty" in mime.lower()):
                return True, mime, None
        except Exception:
            pass  # Fall back to pure-Python inspection

        # 2. Pure-Python signature verification
        if suffix == ".pdf":
            if file_bytes.startswith(b"%PDF"):
                return True, "application/pdf", None
            return False, "application/octet-stream", "Invalid PDF file: Missing %PDF magic signature."

        if suffix == ".docx":
            # Word documents are zip containers with PK header
            if file_bytes.startswith(b"PK\x03\x04"):
                return True, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", None
            return False, "application/octet-stream", "Invalid DOCX file: Missing ZIP/PK magic signature."

        if suffix in {".txt", ".md", ".markdown"}:
            if b"\x00" in file_bytes[:1024]:
                return False, "application/octet-stream", "Invalid text file: Contains binary null characters."
            try:
                file_bytes[:4096].decode("utf-8")
                return True, "text/plain" if suffix == ".txt" else "text/markdown", None
            except UnicodeDecodeError:
                return False, "application/octet-stream", "Invalid text file: Not valid UTF-8 text."

        if suffix == ".csv":
            if b"\x00" in file_bytes[:1024]:
                return False, "application/octet-stream", "Invalid CSV file: Contains binary null characters."
            try:
                sample = file_bytes[:4096].decode("utf-8")
                return True, "text/csv", None
            except UnicodeDecodeError:
                return False, "application/octet-stream", "Invalid CSV file: Not valid UTF-8 text."

        return True, "application/octet-stream", None

    @staticmethod
    def compute_sha256(file_bytes: bytes) -> str:
        return hashlib.sha256(file_bytes).hexdigest()

    @staticmethod
    def extract_csv_pages(file_bytes: bytes) -> List[Dict[str, Any]]:
        """Parses CSV rows into structured, semantic pages for chunking."""
        try:
            text_data = file_bytes.decode("utf-8", errors="replace")
            reader = csv.reader(io.StringIO(text_data))
            rows = [r for r in reader if r and any(c.strip() for c in r)]
            if not rows:
                return []

            headers = rows[0]
            data_rows = rows[1:] if len(rows) > 1 else []
            if not data_rows:
                return [{
                    "page_number": 1,
                    "text": "CSV Schema Headers: " + ", ".join(headers),
                    "headings": ["CSV Schema"],
                    "active_section": "CSV Schema",
                    "active_subsection": "",
                }]

            page_size = 40
            pages: List[Dict[str, Any]] = []
            for i in range(0, len(data_rows), page_size):
                batch = data_rows[i:i + page_size]
                page_num = (i // page_size) + 1
                lines = [f"CSV Table Records {i + 1} to {i + len(batch)}:"]
                for r_idx, r in enumerate(batch, start=i + 1):
                    parts = []
                    for c_idx, val in enumerate(r):
                        col = headers[c_idx] if c_idx < len(headers) else f"Field_{c_idx + 1}"
                        if val.strip():
                            parts.append(f"{col}: {val.strip()}")
                    if parts:
                        lines.append(f"[Row {r_idx}] " + " | ".join(parts))

                pages.append({
                    "page_number": page_num,
                    "text": "\n".join(lines),
                    "headings": [f"CSV Records {i + 1}-{i + len(batch)}"],
                    "active_section": "CSV Data",
                    "active_subsection": f"Rows {i + 1} to {i + len(batch)}",
                })
            return pages
        except Exception as exc:
            logger.error("Error parsing CSV: %s", exc)
            return []

    @staticmethod
    def extract_document_pages(file_path: Path, file_bytes: bytes) -> List[Dict[str, Any]]:
        """Extracts pages based on format."""
        suffix = file_path.suffix.lower()
        if suffix == ".csv":
            return AdminFileService.extract_csv_pages(file_bytes)
        if suffix in {".txt", ".md", ".markdown"}:
            try:
                text_str = file_bytes.decode("utf-8", errors="replace")
                cleaned = DocumentService.clean_text(text_str)
                if cleaned:
                    sections = re.split(r"\n(?=#{1,2}\s+)", cleaned)
                    pages_data = []
                    for idx, section in enumerate(sections, start=1):
                        section_clean = section.strip()
                        if not section_clean:
                            continue
                        first_line = section_clean.split("\n")[0].strip("# ").strip()
                        heading = first_line if first_line and len(first_line) < 80 else f"Section {idx}"
                        pages_data.append({
                            "page_number": idx,
                            "text": section_clean,
                            "headings": [heading],
                            "active_section": heading,
                            "active_subsection": "",
                        })
                    if pages_data:
                        return pages_data
            except Exception:
                pass
        # Use existing DocumentService for PDF, DOCX, etc.
        return DocumentService.extract_document_pages(file_path)

    @classmethod
    def process_and_index_document(
        cls,
        db: Session,
        document_id: str,
        file_path: Path,
        file_bytes: bytes,
    ) -> bool:
        """
        Full atomic extraction, chunking, and embedding generation for a document.
        Reuses the SAME chunk table (document_chunks), embedding model, and dimension (384).
        Refreshes retrieval_service cache immediately.
        """
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            logger.error("Document %s not found for processing", document_id)
            return False

        doc.status = "processing"
        doc.processing_started_at = datetime.now(timezone.utc)
        doc.error_message = None
        db.commit()

        try:
            # 1. Extract text and pages
            pages_data = cls.extract_document_pages(file_path, file_bytes)
            if not pages_data:
                raise ValueError(f"No extractable text found in file '{doc.filename}'.")

            total_pages = len(pages_data)
            extracted_chars = sum(len(p.get("text", "")) for p in pages_data)

            # 2. Chunk pages
            chunks_to_create: List[Dict[str, Any]] = []
            chunk_idx = 0
            for page in pages_data:
                page_text = page.get("text", "").strip()
                if not page_text:
                    continue
                p_num = page.get("page_number", 1)
                active_sec = page.get("active_section", "") or f"Page {p_num}"
                active_subsec = page.get("active_subsection", "")

                page_chunks = DocumentService.chunk_page_text(
                    text=page_text,
                    page_number=p_num,
                    document_name=doc.filename,
                    active_section=active_sec,
                    active_subsection=active_subsec,
                    target_chunk_size=getattr(settings, "CHUNK_SIZE", 1200),
                    chunk_overlap=getattr(settings, "CHUNK_OVERLAP", 200),
                )

                for c in page_chunks:
                    chunks_to_create.append({
                        "chunk_index": chunk_idx,
                        "page_number": p_num,
                        "section": c.get("section", active_sec),
                        "chunk_text": c.get("text", ""),
                        "metadata_json": json.dumps(c.get("metadata", {})),
                    })
                    chunk_idx += 1

            if not chunks_to_create:
                raise ValueError(f"File '{doc.filename}' produced 0 chunks after text segmentation.")

            # 3. Generate embeddings using existing embedding_service
            texts = [c["chunk_text"] for c in chunks_to_create]
            embeddings = embedding_service.embed_batch(texts)

            # 4. Atomic swap in DB: delete old chunks and insert new chunks
            db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).delete()

            chunk_records = []
            for c_info, emb in zip(chunks_to_create, embeddings):
                chunk_records.append(
                    DocumentChunk(
                        id=str(uuid.uuid4()),
                        document_id=doc.id,
                        document_name=doc.filename,
                        chunk_index=c_info["chunk_index"],
                        page_number=c_info["page_number"],
                        section=c_info["section"][:255] if c_info["section"] else None,
                        chunk_text=c_info["chunk_text"],
                        metadata_json=c_info["metadata_json"],
                        embedding=emb,
                    )
                )

            db.bulk_save_objects(chunk_records)

            # 5. Update document record
            doc.status = "completed"
            doc.page_count = total_pages
            doc.total_pages = total_pages
            doc.extracted_chars = extracted_chars
            doc.total_chunks = len(chunk_records)
            doc.embedded_chunks = len(chunk_records)
            doc.processing_completed_at = datetime.now(timezone.utc)
            doc.updated_at = datetime.now(timezone.utc)
            db.commit()

            # 6. Invalidate retrieval in-memory cache to make new data immediately searchable
            retrieval_service.invalidate_cache()
            logger.info("Successfully indexed document %s (%s chunks)", doc.filename, len(chunk_records))
            return True

        except Exception as exc:
            db.rollback()
            logger.error("Failed to process document: %s", exc, exc_info=True)
            try:
                doc_check = db.query(Document).filter(Document.id == document_id).first()
                if doc_check:
                    doc_check.status = "failed"
                    doc_check.error_message = str(exc)[:1000]
                    doc_check.processing_completed_at = datetime.now(timezone.utc)
                    doc_check.updated_at = datetime.now(timezone.utc)
                    db.commit()
            except Exception:
                db.rollback()
            return False

    @classmethod
    def run_background_ingest(cls, document_id: str, file_path_str: str, file_bytes: bytes):
        """Spawns an asynchronous background worker for file processing."""
        def _worker():
            with _BACKGROUND_WORKER_LOCK:
                db = SessionLocal()
                try:
                    cls.process_and_index_document(
                        db=db,
                        document_id=document_id,
                        file_path=Path(file_path_str),
                        file_bytes=file_bytes,
                    )
                finally:
                    db.close()

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

    @staticmethod
    def log_audit(
        db: Session,
        admin_user: User,
        action: str,
        target_id: Optional[str] = None,
        target_name: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
    ):
        """Creates an enterprise audit log entry."""
        try:
            entry = AdminAuditLog(
                id=str(uuid.uuid4()),
                user_id=admin_user.id if admin_user else None,
                admin_email=admin_user.email if admin_user else "unknown@clyptus.ai",
                action=action,
                target_id=target_id,
                target_name=target_name,
                details=json.dumps(details) if details else None,
                ip_address=ip_address,
                created_at=datetime.now(timezone.utc),
            )
            db.add(entry)
            db.commit()
        except Exception as exc:
            logger.warning("Audit logging failed: %s", exc)


admin_file_service = AdminFileService()
