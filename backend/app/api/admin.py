import os
import re
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    status,
)
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.database import get_db
from backend.app.security.auth import verify_admin_key_or_user
from backend.app.models.document import Document
from backend.app.models.chunk import DocumentChunk
from backend.app.services.document_service import document_service
from backend.app.ingestion.ingest import (
    run_ingestion,
    ingest_single_document,
    start_background_ingestion,
    is_ingestion_in_progress,
    SUPPORTED_EXTENSIONS,
)

router = APIRouter(prefix="/admin", tags=["Admin / Developer Ingestion"])


def _sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent directory traversal and filesystem attacks."""
    # Remove path elements
    name = Path(filename).name
    # Strip any null bytes or control characters
    name = name.replace("\x00", "").strip()
    # Replace any traversal dots or unusual characters
    name = re.sub(r"[^\w\.\-\s]", "_", name)
    # Collapse consecutive spaces
    name = re.sub(r"\s+", " ", name)
    # Ensure not empty
    if not name or name.startswith("."):
        name = f"upload_{int(datetime.now(timezone.utc).timestamp())}_{name}"
    return name


@router.post("/documents/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile = File(...),
    authorized: bool = Depends(verify_admin_key_or_user),
    db: Session = Depends(get_db),
):
    """
    Admin-only document upload endpoint.
    1. Validates admin permissions, file format, and size limit.
    2. Persists original file safely to knowledge_base/documents.
    3. Creates or updates document record with 'uploaded' status.
    4. Automatically launches ingestion pipeline in the background.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No filename provided in upload payload.",
        )

    clean_filename = _sanitize_filename(file.filename)
    file_ext = Path(clean_filename).suffix.lower()

    if file_ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported file format '{file_ext}'. "
                f"Allowed formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            ),
        )

    # Prepare storage directory
    storage_dir = Path(settings.DOCUMENTS_DIR)
    storage_dir.mkdir(parents=True, exist_ok=True)
    destination_path = storage_dir / clean_filename

    # Stream file to disk and validate size limit
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    total_bytes = 0

    try:
        with open(destination_path, "wb") as buffer:
            while True:
                chunk = await file.read(65536)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    # Clean up oversized file
                    buffer.close()
                    if destination_path.exists():
                        destination_path.unlink()
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=(
                            f"File size exceeds maximum permitted limit of "
                            f"{settings.MAX_UPLOAD_SIZE_MB} MB."
                        ),
                    )
                buffer.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:
        if destination_path.exists():
            destination_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save uploaded file: {exc}",
        )

    if total_bytes == 0:
        if destination_path.exists():
            destination_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty (0 bytes).",
        )

    # Compute content hash
    file_hash = document_service.compute_file_hash(destination_path)

    # Check for existing document by filename or hash
    existing_doc = (
        db.query(Document)
        .filter(Document.filename == clean_filename)
        .first()
    )

    if existing_doc and existing_doc.file_hash == file_hash and existing_doc.status == "completed":
        # Check if it already has valid stored chunks
        chunk_count = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == existing_doc.id)
            .count()
        )
        if chunk_count > 0:
            return {
                "status": "skipped",
                "message": f"File '{clean_filename}' is identical to existing document and already up-to-date.",
                "document": existing_doc.to_dict(),
            }

    if existing_doc:
        doc_record = existing_doc
        doc_record.file_hash = file_hash
        doc_record.status = "uploaded"
        doc_record.error_message = None
        doc_record.embedded_chunks = 0
        doc_record.processing_started_at = None
        doc_record.processing_completed_at = None
        doc_record.updated_at = datetime.now(timezone.utc)
        db.commit()
    else:
        doc_info = document_service.get_document_info(clean_filename)
        doc_record = Document(
            filename=clean_filename,
            title=doc_info["title"],
            file_hash=file_hash,
            version="1.0",
            page_count=0,
            status="uploaded",
            total_pages=0,
            extracted_chars=0,
            total_chunks=0,
            embedded_chunks=0,
        )
        db.add(doc_record)
        db.commit()
        db.refresh(doc_record)

    # Trigger automatic ingestion in the background
    start_background_ingestion(destination_path, str(doc_record.id))

    return {
        "status": "uploaded",
        "message": f"File '{clean_filename}' uploaded successfully. Ingestion started automatically.",
        "document": doc_record.to_dict(),
    }


@router.get("/documents/status")
@router.get("/documents")
def list_documents_status(
    authorized: bool = Depends(verify_admin_key_or_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve status and ingestion progress for all documents in the knowledge base.
    """
    documents = db.query(Document).order_by(Document.created_at.desc()).all()
    return {
        "is_ingesting": is_ingestion_in_progress(),
        "total_documents": len(documents),
        "documents": [doc.to_dict() for doc in documents],
    }


@router.get("/documents/{document_id}/status")
def get_document_status(
    document_id: str,
    authorized: bool = Depends(verify_admin_key_or_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve real-time ingestion progress and status for a specific document.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )
    return {
        "is_ingesting": is_ingestion_in_progress(),
        "document": doc.to_dict(),
    }


@router.post("/documents/{document_id}/retry")
def retry_document_ingestion(
    document_id: str,
    authorized: bool = Depends(verify_admin_key_or_user),
    db: Session = Depends(get_db),
):
    """
    Retry ingestion for a document that failed or was interrupted.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )

    # Find file on disk
    file_path = Path(settings.DOCUMENTS_DIR) / doc.filename
    if not file_path.exists():
        # Check fallback directories
        for search_dir in (settings.KNOWLEDGE_BASE_DIR, settings.FULL_RAG_DATA_DIR):
            candidate = Path(search_dir) / doc.filename
            if candidate.exists():
                file_path = candidate
                break

    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source file '{doc.filename}' not found in storage.",
        )

    doc.status = "uploaded"
    doc.error_message = None
    doc.updated_at = datetime.now(timezone.utc)
    db.commit()

    start_background_ingestion(file_path, str(doc.id))

    return {
        "status": "success",
        "message": f"Retry initiated for document '{doc.filename}'.",
        "document": doc.to_dict(),
    }


@router.post("/documents/ingest")
def trigger_ingestion(
    authorized: bool = Depends(verify_admin_key_or_user),
    db: Session = Depends(get_db),
):
    """
    Developer-only ingestion endpoint.
    Scans backend/knowledge_base/documents/ for supported documents, extracts, chunks, embeds, and stores them.
    Skips unchanged files based on SHA-256 hash.
    """
    results = run_ingestion(db)
    return {
        "status": "success",
        "message": "Ingestion process completed successfully.",
        "details": results,
    }
