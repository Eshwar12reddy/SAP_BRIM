import os
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc, asc

from backend.app.config import settings
from backend.app.database import get_db
from backend.app.security.auth import get_current_admin_user
from backend.app.models.user import User
from backend.app.models.document import Document
from backend.app.models.chunk import DocumentChunk
from backend.app.models.admin_portal import KBDocumentBinary, AdminAuditLog
from backend.app.schemas.admin_files import (
    FileStatsResponse,
    BulkUploadResponse,
    FileUploadItemResult,
    FileListResponse,
    FileListItem,
    FileDetailResponse,
    FileChunksResponse,
    ChunkItem,
    FileMetadataUpdate,
    BulkDeleteRequest,
    DeleteAllRequest,
    AuditLogListResponse,
    AuditLogItem,
)
from backend.app.services.admin_file_service import (
    admin_file_service,
    ALLOWED_EXTENSIONS,
    ADMIN_UPLOAD_MAX_MB,
    ADMIN_UPLOAD_MAX_FILES,
    STORE_ORIGINAL_FILE,
)
from backend.app.services.retrieval_service import retrieval_service

router = APIRouter(
    prefix="/admin/files",
    tags=["Admin Knowledge Base Files"],
    dependencies=[Depends(get_current_admin_user)],
)


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.get("/stats", response_model=FileStatsResponse)
def get_file_stats(
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user),
):
    """Returns aggregated real-time metrics for documents and embeddings."""
    total_docs = db.query(Document).count()
    completed = db.query(Document).filter(Document.status == "completed").count()
    pending = db.query(Document).filter(Document.status.in_(["pending", "uploaded"])).count()
    processing = db.query(Document).filter(Document.status == "processing").count()
    failed = db.query(Document).filter(Document.status == "failed").count()
    total_chunks = db.query(DocumentChunk).count()
    missing_embeddings = db.query(DocumentChunk).filter(DocumentChunk.embedding == None).count()

    return FileStatsResponse(
        total_documents=total_docs,
        completed=completed,
        pending=pending,
        processing=processing,
        failed=failed,
        total_chunks=total_chunks,
        missing_embeddings=missing_embeddings,
    )


@router.post("/upload", response_model=BulkUploadResponse, status_code=status.HTTP_201_CREATED)
async def bulk_upload_files(
    request: Request,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user),
):
    """
    Enterprise bulk upload endpoint:
    - Validates extensions (PDF, DOCX, TXT, MD, CSV) & magic bytes.
    - Enforces max file size (ADMIN_UPLOAD_MAX_MB) & batch limit (ADMIN_UPLOAD_MAX_FILES).
    - Prevents directory traversal through sanitization.
    - Detects duplicates via SHA-256.
    - Persists original file bytes in PostgreSQL BYTEA when STORE_ORIGINAL_FILE=true.
    - Spawns background worker to extract, chunk, and embed.
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided in upload request.",
        )

    if len(files) > ADMIN_UPLOAD_MAX_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Exceeded maximum batch limit of {ADMIN_UPLOAD_MAX_FILES} files. Received: {len(files)}.",
        )

    results: List[FileUploadItemResult] = []
    successful_count = 0
    skipped_count = 0
    failed_count = 0

    storage_dir = Path(settings.DOCUMENTS_DIR)
    storage_dir.mkdir(parents=True, exist_ok=True)
    max_bytes = ADMIN_UPLOAD_MAX_MB * 1024 * 1024
    client_ip = _get_client_ip(request)

    for upload in files:
        original_name = upload.filename or "unnamed_file"
        clean_name = admin_file_service.sanitize_filename(original_name)
        suffix = Path(clean_name).suffix.lower()

        # 1. Extension check
        if suffix not in ALLOWED_EXTENSIONS:
            failed_count += 1
            results.append(
                FileUploadItemResult(
                    filename=original_name,
                    status="failed",
                    message=f"File extension '{suffix}' not allowed.",
                    error=f"Allowed extensions: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
                )
            )
            continue

        # 2. Read bytes & check size
        try:
            file_bytes = await upload.read()
        except Exception as exc:
            failed_count += 1
            results.append(
                FileUploadItemResult(
                    filename=original_name,
                    status="failed",
                    message="Failed to read file stream.",
                    error=str(exc),
                )
            )
            continue

        if len(file_bytes) == 0:
            failed_count += 1
            results.append(
                FileUploadItemResult(
                    filename=original_name,
                    status="failed",
                    message="File is empty (0 bytes).",
                    error="Uploaded file contains 0 bytes.",
                )
            )
            continue

        if len(file_bytes) > max_bytes:
            failed_count += 1
            results.append(
                FileUploadItemResult(
                    filename=original_name,
                    status="failed",
                    size_bytes=len(file_bytes),
                    message=f"File size exceeds maximum permitted limit of {ADMIN_UPLOAD_MAX_MB} MB.",
                    error=f"Actual size: {len(file_bytes) / (1024*1024):.2f} MB",
                )
            )
            continue

        # 3. Magic bytes / MIME validation
        is_valid, detected_mime, mime_err = admin_file_service.validate_magic_bytes_and_mime(
            file_bytes, clean_name
        )
        if not is_valid:
            failed_count += 1
            results.append(
                FileUploadItemResult(
                    filename=original_name,
                    status="failed",
                    size_bytes=len(file_bytes),
                    message="Magic bytes validation failed.",
                    error=mime_err or "File signature does not match extension.",
                )
            )
            continue

        # 4. SHA-256 duplicate detection
        file_hash = admin_file_service.compute_sha256(file_bytes)
        existing_doc = db.query(Document).filter(
            or_(Document.filename == clean_name, Document.file_hash == file_hash)
        ).first()

        if existing_doc and existing_doc.file_hash == file_hash and existing_doc.status in ("completed", "processing", "uploaded", "pending"):
            skipped_count += 1
            results.append(
                FileUploadItemResult(
                    filename=clean_name,
                    status="skipped",
                    document_id=str(existing_doc.id),
                    file_hash=file_hash,
                    size_bytes=len(file_bytes),
                    message="Identical file already exists and is in the knowledge base.",
                )
            )
            continue

        # 5. Persist to disk and create / update document record
        destination_path = storage_dir / clean_name
        with open(destination_path, "wb") as f:
            f.write(file_bytes)

        title = clean_name.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").title()

        if existing_doc:
            doc_record = existing_doc
            doc_record.file_hash = file_hash
            doc_record.status = "processing"
            doc_record.error_message = None
            doc_record.updated_at = datetime.now(timezone.utc)
            if hasattr(doc_record, "size_bytes"):
                doc_record.size_bytes = len(file_bytes)
            db.commit()
        else:
            doc_record = Document(
                id=str(uuid.uuid4()),
                filename=clean_name,
                title=title,
                file_hash=file_hash,
                version="1.0",
                page_count=0,
                status="processing",
                total_pages=0,
                extracted_chars=0,
                total_chunks=0,
                embedded_chunks=0,
            )
            if hasattr(doc_record, "size_bytes"):
                doc_record.size_bytes = len(file_bytes)
            if hasattr(doc_record, "category"):
                doc_record.category = "General"
            db.add(doc_record)
            db.commit()
            db.refresh(doc_record)

        # 6. Store original file bytes in PostgreSQL if configured
        if STORE_ORIGINAL_FILE:
            kb_binary = db.query(KBDocumentBinary).filter(
                KBDocumentBinary.document_id == doc_record.id
            ).first()
            if kb_binary:
                kb_binary.file_bytes = file_bytes
                kb_binary.file_size = len(file_bytes)
                kb_binary.content_type = detected_mime
                kb_binary.updated_at = datetime.now(timezone.utc)
            else:
                kb_binary = KBDocumentBinary(
                    id=str(uuid.uuid4()),
                    document_id=doc_record.id,
                    file_bytes=file_bytes,
                    file_size=len(file_bytes),
                    content_type=detected_mime,
                )
                db.add(kb_binary)
            db.commit()

        # 7. Spawn background processing for extraction, chunking, and embeddings
        admin_file_service.run_background_ingest(
            document_id=str(doc_record.id),
            file_path_str=str(destination_path),
            file_bytes=file_bytes,
        )

        # 8. Audit log
        admin_file_service.log_audit(
            db=db,
            admin_user=admin_user,
            action="UPLOAD",
            target_id=str(doc_record.id),
            target_name=clean_name,
            details={"file_size": len(file_bytes), "mime": detected_mime, "hash": file_hash},
            ip_address=client_ip,
        )

        successful_count += 1
        results.append(
            FileUploadItemResult(
                filename=clean_name,
                status="uploaded",
                document_id=str(doc_record.id),
                file_hash=file_hash,
                size_bytes=len(file_bytes),
                message="File uploaded. Ingestion processing initiated.",
            )
        )

    return BulkUploadResponse(
        total_received=len(files),
        successful=successful_count,
        skipped=skipped_count,
        failed=failed_count,
        results=results,
    )


@router.get("/list", response_model=FileListResponse)
def list_files(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    file_type: Optional[str] = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user),
):
    """Paginated list of files with search, filtering, and sorting."""
    query = db.query(Document)

    # Search filter
    if search:
        search_pattern = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Document.filename.ilike(search_pattern),
                Document.title.ilike(search_pattern),
            )
        )

    # Status filter
    if status and status.lower() != "all":
        query = query.filter(Document.status == status.lower())

    # File type filter
    if file_type and file_type.lower() != "all":
        type_ext = file_type.lower()
        if not type_ext.startswith("."):
            type_ext = f".{type_ext}"
        query = query.filter(Document.filename.ilike(f"%{type_ext}"))

    # Sorting
    sort_column = getattr(Document, sort_by, Document.created_at)
    if sort_order.lower() == "asc":
        query = query.order_by(asc(sort_column))
    else:
        query = query.order_by(desc(sort_column))

    total = query.count()
    total_pages = max(1, (total + page_size - 1) // page_size)
    offset = (page - 1) * page_size
    docs = query.offset(offset).limit(page_size).all()

    # Pre-fetch binary status
    doc_ids = [d.id for d in docs]
    binary_doc_ids = set()
    if doc_ids:
        binaries = db.query(KBDocumentBinary.document_id).filter(
            KBDocumentBinary.document_id.in_(doc_ids)
        ).all()
        binary_doc_ids = {b[0] for b in binaries}

    items: List[FileListItem] = []
    for d in docs:
        ext = Path(d.filename).suffix.lower()
        file_type_name = ext.lstrip(".").upper() if ext else "UNKNOWN"
        size = getattr(d, "size_bytes", 0) or 0

        # Fallback to disk size if 0
        if size == 0:
            disk_file = Path(settings.DOCUMENTS_DIR) / d.filename
            if disk_file.exists():
                size = disk_file.stat().st_size

        items.append(
            FileListItem(
                id=str(d.id),
                filename=d.filename,
                title=d.title or d.filename,
                category=getattr(d, "category", "General") or "General",
                description=getattr(d, "description", None),
                file_type=file_type_name,
                size_bytes=size,
                status=d.status or "completed",
                total_pages=d.total_pages or d.page_count or 0,
                extracted_chars=d.extracted_chars or 0,
                total_chunks=d.total_chunks or 0,
                embedded_chunks=d.embedded_chunks or 0,
                has_binary=d.id in binary_doc_ids,
                error_message=d.error_message,
                created_at=d.created_at.isoformat() if d.created_at else None,
                updated_at=d.updated_at.isoformat() if d.updated_at else None,
            )
        )

    return FileListResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        items=items,
    )


@router.get("/audit-logs", response_model=AuditLogListResponse)
def get_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user),
):
    """Paginated list of enterprise admin audit trails."""
    query = db.query(AdminAuditLog)
    if action:
        query = query.filter(AdminAuditLog.action == action.upper())

    total = query.count()
    total_pages = max(1, (total + page_size - 1) // page_size)
    offset = (page - 1) * page_size
    logs = query.order_by(desc(AdminAuditLog.created_at)).offset(offset).limit(page_size).all()

    items = [
        AuditLogItem(
            id=str(log.id),
            user_id=str(log.user_id) if log.user_id else None,
            admin_email=log.admin_email,
            action=log.action,
            target_id=log.target_id,
            target_name=log.target_name,
            details=log.details,
            ip_address=log.ip_address,
            created_at=log.created_at.isoformat() if log.created_at else None,
        )
        for log in logs
    ]

    return AuditLogListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=items,
    )


# =========================================================================
# CRITICAL: Bulk and All Delete endpoints MUST precede /{id} in router registration!
# =========================================================================

@router.delete("/bulk")
def bulk_delete_files(
    payload: BulkDeleteRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user),
):
    """Deletes multiple selected files and their chunks/embeddings/binaries in a single transaction."""
    target_ids = payload.ids
    if not target_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No IDs provided.")

    docs = db.query(Document).filter(Document.id.in_(target_ids)).all()
    if not docs:
        return {"status": "success", "deleted_count": 0, "message": "No matching documents found."}

    deleted_names = [d.filename for d in docs]
    client_ip = _get_client_ip(request)

    # 1. Remove disk files
    for d in docs:
        p = Path(settings.DOCUMENTS_DIR) / d.filename
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass

    # 2. Database cleanup (DocumentChunk & KBDocumentBinary cascade or explicit)
    db.query(DocumentChunk).filter(DocumentChunk.document_id.in_(target_ids)).delete(synchronize_session=False)
    db.query(KBDocumentBinary).filter(KBDocumentBinary.document_id.in_(target_ids)).delete(synchronize_session=False)
    db.query(Document).filter(Document.id.in_(target_ids)).delete(synchronize_session=False)
    db.commit()

    # 3. Invalidate cache
    retrieval_service.invalidate_cache()

    # 4. Audit log
    admin_file_service.log_audit(
        db=db,
        admin_user=admin_user,
        action="BULK_DELETE",
        target_id=",".join(target_ids[:10]),
        target_name=f"{len(deleted_names)} files",
        details={"deleted_ids": target_ids, "filenames": deleted_names},
        ip_address=client_ip,
    )

    return {
        "status": "success",
        "deleted_count": len(docs),
        "message": f"Successfully deleted {len(docs)} files.",
    }


@router.delete("/all")
def delete_all_files(
    payload: DeleteAllRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user),
):
    """
    Destructive purge of ALL knowledge base files.
    Enforces strict typing check: body must contain confirmation='DELETE'.
    """
    if payload.confirmation != "DELETE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation string must be exactly 'DELETE' to confirm irreversible purge.",
        )

    client_ip = _get_client_ip(request)
    total_docs = db.query(Document).count()
    total_chunks = db.query(DocumentChunk).count()

    # 1. Remove all files from disk
    storage_dir = Path(settings.DOCUMENTS_DIR)
    if storage_dir.exists():
        for item in storage_dir.glob("*"):
            if item.is_file():
                try:
                    item.unlink()
                except Exception:
                    pass

    # 2. Delete all records
    db.query(DocumentChunk).delete(synchronize_session=False)
    db.query(KBDocumentBinary).delete(synchronize_session=False)
    db.query(Document).delete(synchronize_session=False)
    db.commit()

    # 3. Invalidate cache
    retrieval_service.invalidate_cache()

    # 4. Audit log
    admin_file_service.log_audit(
        db=db,
        admin_user=admin_user,
        action="DELETE_ALL",
        target_id="ALL",
        target_name="ALL_DOCUMENTS",
        details={"purged_documents": total_docs, "purged_chunks": total_chunks},
        ip_address=client_ip,
    )

    return {
        "status": "success",
        "purged_documents": total_docs,
        "purged_chunks": total_chunks,
        "message": f"All knowledge base files purged successfully ({total_docs} documents, {total_chunks} chunks).",
    }


# =========================================================================
# Single Document Endpoints (/{id})
# =========================================================================

@router.get("/{id}", response_model=FileDetailResponse)
def get_file_detail(
    id: str,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user),
):
    """Detailed file metadata, chunk counts, and processing lifecycle."""
    doc = db.query(Document).filter(Document.id == id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document '{id}' not found.")

    has_binary = db.query(KBDocumentBinary).filter(KBDocumentBinary.document_id == doc.id).first() is not None
    ext = Path(doc.filename).suffix.lower()
    file_type_name = ext.lstrip(".").upper() if ext else "UNKNOWN"

    size = getattr(doc, "size_bytes", 0) or 0
    if size == 0:
        disk_file = Path(settings.DOCUMENTS_DIR) / doc.filename
        if disk_file.exists():
            size = disk_file.stat().st_size

    return FileDetailResponse(
        id=str(doc.id),
        filename=doc.filename,
        title=doc.title or doc.filename,
        category=getattr(doc, "category", "General") or "General",
        description=getattr(doc, "description", None),
        file_type=file_type_name,
        size_bytes=size,
        file_hash=doc.file_hash,
        version=doc.version or "1.0",
        status=doc.status or "completed",
        total_pages=doc.total_pages or doc.page_count or 0,
        extracted_chars=doc.extracted_chars or 0,
        total_chunks=doc.total_chunks or 0,
        embedded_chunks=doc.embedded_chunks or 0,
        has_binary=has_binary,
        error_message=doc.error_message,
        processing_started_at=doc.processing_started_at.isoformat() if doc.processing_started_at else None,
        processing_completed_at=doc.processing_completed_at.isoformat() if doc.processing_completed_at else None,
        created_at=doc.created_at.isoformat() if doc.created_at else None,
        updated_at=doc.updated_at.isoformat() if doc.updated_at else None,
    )


@router.get("/{id}/chunks", response_model=FileChunksResponse)
def get_file_chunks(
    id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user),
):
    """Paginated chunks with page numbers and embedding status."""
    doc = db.query(Document).filter(Document.id == id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document '{id}' not found.")

    query = db.query(DocumentChunk).filter(DocumentChunk.document_id == id).order_by(asc(DocumentChunk.chunk_index))
    total_chunks = query.count()
    total_pages = max(1, (total_chunks + page_size - 1) // page_size)
    offset = (page - 1) * page_size
    chunks = query.offset(offset).limit(page_size).all()

    items = [
        ChunkItem(
            id=str(c.id),
            document_id=str(c.document_id),
            chunk_index=c.chunk_index,
            page_number=c.page_number,
            section=c.section,
            chunk_text=c.chunk_text,
            has_embedding=c.embedding is not None,
            text_length=len(c.chunk_text),
        )
        for c in chunks
    ]

    return FileChunksResponse(
        document_id=str(doc.id),
        document_title=doc.title or doc.filename,
        total_chunks=total_chunks,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        chunks=items,
    )


@router.get("/{id}/download")
def download_file(
    id: str,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user),
):
    """Downloads original file binary from PostgreSQL BYTEA (or local disk storage fallback)."""
    doc = db.query(Document).filter(Document.id == id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document '{id}' not found.")

    # 1. Try DB binary
    kb_binary = db.query(KBDocumentBinary).filter(KBDocumentBinary.document_id == doc.id).first()
    if kb_binary and kb_binary.file_bytes:
        return Response(
            content=kb_binary.file_bytes,
            media_type=kb_binary.content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{doc.filename}"',
                "Content-Length": str(len(kb_binary.file_bytes)),
            },
        )

    # 2. Disk fallback
    file_path = Path(settings.DOCUMENTS_DIR) / doc.filename
    if not file_path.exists():
        # Fallback check
        for cand_dir in (settings.KNOWLEDGE_BASE_DIR, settings.FULL_RAG_DATA_DIR):
            cand = Path(cand_dir) / doc.filename
            if cand.exists():
                file_path = cand
                break

    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Source file '{doc.filename}' not found.")

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    return Response(
        content=file_bytes,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{doc.filename}"',
            "Content-Length": str(len(file_bytes)),
        },
    )


@router.put("/{id}", response_model=FileDetailResponse)
def update_file_metadata(
    id: str,
    payload: FileMetadataUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user),
):
    """Updates document metadata (title, category, description)."""
    doc = db.query(Document).filter(Document.id == id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document '{id}' not found.")

    client_ip = _get_client_ip(request)
    old_meta = {
        "title": doc.title,
        "category": getattr(doc, "category", None),
        "description": getattr(doc, "description", None),
    }

    if payload.title is not None:
        doc.title = payload.title.strip()
    if payload.category is not None and hasattr(doc, "category"):
        doc.category = payload.category.strip()
    if payload.description is not None and hasattr(doc, "description"):
        doc.description = payload.description.strip()

    doc.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(doc)

    admin_file_service.log_audit(
        db=db,
        admin_user=admin_user,
        action="EDIT_METADATA",
        target_id=str(doc.id),
        target_name=doc.filename,
        details={"before": old_meta, "after": payload.model_dump(exclude_unset=True)},
        ip_address=client_ip,
    )

    return get_file_detail(id=id, db=db, admin_user=admin_user)


@router.post("/{id}/replace", response_model=FileDetailResponse)
async def replace_file(
    id: str,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user),
):
    """
    Replaces an existing document with a new version:
    - Validates extension, magic bytes, and size limit.
    - Re-extracts, re-chunks, re-embeds.
    - Swaps old chunks atomically in one transaction.
    - Updates binary and invalidates retrieval cache.
    """
    doc = db.query(Document).filter(Document.id == id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document '{id}' not found.")

    original_name = file.filename or doc.filename
    clean_name = admin_file_service.sanitize_filename(original_name)
    suffix = Path(clean_name).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{suffix}'.",
        )

    file_bytes = await file.read()
    max_bytes = ADMIN_UPLOAD_MAX_MB * 1024 * 1024
    if len(file_bytes) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Replacement file is empty.")
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum permitted limit of {ADMIN_UPLOAD_MAX_MB} MB.",
        )

    is_valid, detected_mime, mime_err = admin_file_service.validate_magic_bytes_and_mime(file_bytes, clean_name)
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=mime_err)

    new_hash = admin_file_service.compute_sha256(file_bytes)
    destination_path = Path(settings.DOCUMENTS_DIR) / clean_name
    with open(destination_path, "wb") as f:
        f.write(file_bytes)

    # Increment version
    try:
        curr_v = float(doc.version or "1.0")
        doc.version = f"{curr_v + 1.0:.1f}"
    except Exception:
        doc.version = "2.0"

    doc.filename = clean_name
    doc.file_hash = new_hash
    if hasattr(doc, "size_bytes"):
        doc.size_bytes = len(file_bytes)
    doc.updated_at = datetime.now(timezone.utc)
    db.commit()

    # Update binary
    if STORE_ORIGINAL_FILE:
        kb_binary = db.query(KBDocumentBinary).filter(KBDocumentBinary.document_id == doc.id).first()
        if kb_binary:
            kb_binary.file_bytes = file_bytes
            kb_binary.file_size = len(file_bytes)
            kb_binary.content_type = detected_mime
            kb_binary.updated_at = datetime.now(timezone.utc)
        else:
            kb_binary = KBDocumentBinary(
                id=str(uuid.uuid4()),
                document_id=doc.id,
                file_bytes=file_bytes,
                file_size=len(file_bytes),
                content_type=detected_mime,
            )
            db.add(kb_binary)
        db.commit()

    # Perform atomic re-index
    success = admin_file_service.process_and_index_document(
        db=db,
        document_id=str(doc.id),
        file_path=destination_path,
        file_bytes=file_bytes,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Replacement indexing failed: {doc.error_message}",
        )

    client_ip = _get_client_ip(request)
    admin_file_service.log_audit(
        db=db,
        admin_user=admin_user,
        action="REPLACE",
        target_id=str(doc.id),
        target_name=clean_name,
        details={"version": doc.version, "hash": new_hash, "size": len(file_bytes)},
        ip_address=client_ip,
    )

    return get_file_detail(id=id, db=db, admin_user=admin_user)


@router.post("/{id}/reindex", response_model=FileDetailResponse)
def reindex_file(
    id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user),
):
    """Re-indexes an existing document from stored binary or disk file."""
    doc = db.query(Document).filter(Document.id == id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document '{id}' not found.")

    # Retrieve bytes
    file_bytes: Optional[bytes] = None
    kb_binary = db.query(KBDocumentBinary).filter(KBDocumentBinary.document_id == doc.id).first()
    if kb_binary and kb_binary.file_bytes:
        file_bytes = bytes(kb_binary.file_bytes)

    file_path = Path(settings.DOCUMENTS_DIR) / doc.filename
    if not file_path.exists() and not file_bytes:
        for cand_dir in (settings.KNOWLEDGE_BASE_DIR, settings.FULL_RAG_DATA_DIR):
            cand = Path(cand_dir) / doc.filename
            if cand.exists():
                file_path = cand
                break

    if not file_path.exists() and not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source content for '{doc.filename}' not found in DB or disk.",
        )

    if not file_bytes and file_path.exists():
        with open(file_path, "rb") as f:
            file_bytes = f.read()

    success = admin_file_service.process_and_index_document(
        db=db,
        document_id=str(doc.id),
        file_path=file_path,
        file_bytes=file_bytes or b"",
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Re-indexing failed: {doc.error_message}",
        )

    client_ip = _get_client_ip(request)
    admin_file_service.log_audit(
        db=db,
        admin_user=admin_user,
        action="REINDEX",
        target_id=str(doc.id),
        target_name=doc.filename,
        details={"chunks": doc.total_chunks, "status": doc.status},
        ip_address=client_ip,
    )

    return get_file_detail(id=id, db=db, admin_user=admin_user)


@router.delete("/{id}")
def delete_file(
    id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user),
):
    """Deletes a single file, its chunks, embeddings, and binary in one transaction."""
    doc = db.query(Document).filter(Document.id == id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document '{id}' not found.")

    doc_name = doc.filename
    client_ip = _get_client_ip(request)

    # 1. Disk removal
    disk_file = Path(settings.DOCUMENTS_DIR) / doc.filename
    if disk_file.exists():
        try:
            disk_file.unlink()
        except Exception:
            pass

    # 2. DB cleanup
    db.query(DocumentChunk).filter(DocumentChunk.document_id == id).delete(synchronize_session=False)
    db.query(KBDocumentBinary).filter(KBDocumentBinary.document_id == id).delete(synchronize_session=False)
    db.delete(doc)
    db.commit()

    # 3. Invalidate cache
    retrieval_service.invalidate_cache()

    # 4. Audit log
    admin_file_service.log_audit(
        db=db,
        admin_user=admin_user,
        action="DELETE",
        target_id=id,
        target_name=doc_name,
        details={"deleted_file": doc_name},
        ip_address=client_ip,
    )

    return {
        "status": "success",
        "message": f"Document '{doc_name}' and all associated chunks were successfully deleted.",
    }
