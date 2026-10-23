import os
import sys
import json
import time
import logging
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Union

from sqlalchemy.orm import Session

# Ensure the project root is available when this script is run directly.
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.config import settings
from backend.app.database import SessionLocal, init_db
from backend.app.models.document import Document
from backend.app.models.chunk import DocumentChunk
from backend.app.services.document_service import document_service
from backend.app.services.embedding_service import embedding_service
from backend.app.services.retrieval_service import retrieval_service


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("ingestion")


# Supported document formats
SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown", ".docx"}


# Chunk configuration: values come from the backend/.env file or settings.
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", str(settings.CHUNK_SIZE)))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", str(settings.CHUNK_OVERLAP)))

# Embedding batch size
BATCH_EMBED_SIZE = int(os.getenv("BATCH_EMBED_SIZE", "64"))

# Set FORCE_REINGEST=true to reprocess documents even if their
# source file has not changed. This is useful after changing chunk settings.
FORCE_REINGEST = (
    os.getenv("FORCE_REINGEST", "false").strip().lower()
    in {"1", "true", "yes", "on"}
)

# Concurrency lock to enforce single active ingestion job
INGESTION_LOCK = threading.Lock()


def is_ingestion_in_progress() -> bool:
    """Return True if an ingestion job is currently executing."""
    acquired = INGESTION_LOCK.acquire(blocking=False)
    if acquired:
        INGESTION_LOCK.release()
        return False
    return True


def validate_configuration() -> None:
    """Validate chunking and embedding batch settings."""

    if CHUNK_SIZE <= 0:
        raise ValueError("CHUNK_SIZE must be greater than zero.")

    if CHUNK_OVERLAP < 0:
        raise ValueError("CHUNK_OVERLAP cannot be negative.")

    if CHUNK_OVERLAP >= CHUNK_SIZE:
        raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE.")

    if BATCH_EMBED_SIZE <= 0:
        raise ValueError("BATCH_EMBED_SIZE must be greater than zero.")

    logger.info(
        "Ingestion configuration: chunk_size=%s, chunk_overlap=%s, "
        "embedding_batch_size=%s, force_reingest=%s",
        CHUNK_SIZE,
        CHUNK_OVERLAP,
        BATCH_EMBED_SIZE,
        FORCE_REINGEST,
    )


def discover_knowledge_base_files() -> List[Path]:
    """
    Recursively discover supported documents in configured directories.

    Searches KNOWLEDGE_BASE_DIR, DOCUMENTS_DIR and FULL_RAG_DATA_DIR
    when those directories exist.

    Files with identical filenames are deduplicated, keeping the first
    discovered occurrence.
    """

    search_dirs: List[Path] = []

    for setting_name in (
        "KNOWLEDGE_BASE_DIR",
        "DOCUMENTS_DIR",
        "FULL_RAG_DATA_DIR",
    ):
        directory = getattr(settings, setting_name, None)

        if not directory:
            continue

        directory = Path(directory)

        if directory.is_dir() and directory not in search_dirs:
            search_dirs.append(directory)

            if setting_name == "FULL_RAG_DATA_DIR":
                logger.info(
                    "Including FULL_RAG_DATA_DIR: %s",
                    directory,
                )

    discovered_files: Dict[str, Path] = {}

    for directory in search_dirs:
        logger.info("Scanning directory recursively: %s", directory)

        for path in directory.rglob("*"):
            if not path.is_file():
                continue

            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue

            # Preserve the existing filename-based deduplication behavior.
            if path.name not in discovered_files:
                discovered_files[path.name] = path

    file_list = sorted(
        discovered_files.values(),
        key=lambda path: path.name.lower(),
    )

    logger.info(
        "Total supported documents discovered: %s",
        len(file_list),
    )

    return file_list


def ingest_single_document(
    file_path: Union[str, Path],
    db: Session,
    document_id: Optional[str] = None,
    force_reingest: bool = False,
) -> Dict[str, Any]:
    """
    Ingest a single document end-to-end:
    1. Validate source path and compute SHA-256 hash.
    2. Check idempotency: skip if unchanged and chunks exist.
    3. Extract text page-by-page, removing NUL (\x00) characters.
    4. Detect empty or scanned PDFs (< 50 characters extracted) and mark failed.
    5. Chunk with structure-aware logic and environment settings.
    6. Generate embeddings in batches with bounded retries and 384-dim check.
    7. Atomically swap in new chunks (retaining old chunks if process fails).
    8. Update document status and invalidate retrieval caches.
    """
    doc_path = Path(file_path)
    filename = doc_path.name

    if not doc_path.exists() or not doc_path.is_file():
        logger.error("Document file not found at path: %s", doc_path)
        if document_id:
            doc = db.query(Document).filter(Document.id == document_id).first()
            if doc:
                doc.status = "failed"
                doc.error_message = f"File not found on disk: {filename}"
                db.commit()
        return {
            "filename": filename,
            "status": "failed",
            "reason": f"File not found on disk: {filename}",
            "chunks": 0,
        }

    try:
        file_hash = document_service.compute_file_hash(doc_path)

        # Locate existing document record by ID or filename
        existing_doc: Optional[Document] = None
        if document_id:
            existing_doc = db.query(Document).filter(Document.id == document_id).first()
        if not existing_doc:
            existing_doc = db.query(Document).filter(Document.filename == filename).first()

        # Idempotency check: unchanged file with existing chunks
        if existing_doc and existing_doc.file_hash == file_hash and not force_reingest and not FORCE_REINGEST:
            chunk_count = (
                db.query(DocumentChunk)
                .filter(DocumentChunk.document_id == existing_doc.id)
                .count()
            )
            # If already has chunks and is completed
            if chunk_count > 0 and getattr(existing_doc, "status", "completed") == "completed":
                logger.info(
                    "Skipping '%s': unchanged file with %s existing chunks.",
                    filename,
                    chunk_count,
                )
                return {
                    "filename": filename,
                    "status": "skipped",
                    "reason": "already_up_to_date",
                    "document_id": str(existing_doc.id),
                    "chunks": chunk_count,
                }

        file_size_mb = doc_path.stat().st_size / (1024 * 1024)
        logger.info("Processing '%s' (%.2f MB).", filename, file_size_mb)

        # Initialize or update document record to 'processing'
        if existing_doc:
            doc_record = existing_doc
            doc_record.file_hash = file_hash
            doc_record.status = "processing"
            doc_record.processing_started_at = datetime.now(timezone.utc)
            doc_record.error_message = None
            doc_record.embedded_chunks = 0
            doc_record.updated_at = datetime.now(timezone.utc)
            db.commit()
        else:
            doc_info = document_service.get_document_info(filename)
            doc_record = Document(
                filename=filename,
                title=doc_info["title"],
                file_hash=file_hash,
                version="1.0",
                page_count=0,
                status="processing",
                total_pages=0,
                extracted_chars=0,
                total_chunks=0,
                embedded_chunks=0,
                processing_started_at=datetime.now(timezone.utc),
            )
            db.add(doc_record)
            db.commit()
            db.refresh(doc_record)

        # Extract pages, text, and structural metadata
        pages = document_service.extract_document_pages(doc_path)
        page_count = len(pages)
        total_extracted_chars = sum(len(p.get("text", "").replace("\x00", "")) for p in pages)

        # Detection of scanned/empty documents: must fail cleanly
        if not pages or total_extracted_chars < 50:
            err_reason = "no extractable text (scanned PDF?)"
            logger.warning("Extraction failure for '%s': %s (chars=%s)", filename, err_reason, total_extracted_chars)
            doc_record.status = "failed"
            doc_record.error_message = err_reason
            doc_record.extracted_chars = total_extracted_chars
            doc_record.total_pages = page_count
            doc_record.page_count = page_count
            doc_record.processing_completed_at = datetime.now(timezone.utc)
            doc_record.updated_at = datetime.now(timezone.utc)
            db.commit()
            return {
                "filename": filename,
                "status": "failed",
                "reason": err_reason,
                "document_id": str(doc_record.id),
                "chunks": 0,
            }

        doc_record.page_count = page_count
        doc_record.total_pages = page_count
        doc_record.extracted_chars = total_extracted_chars
        db.commit()

        # Chunk extracted text
        all_chunk_dicts: List[Dict[str, Any]] = []
        for page_data in pages:
            page_num = page_data["page_number"]
            # Clean NUL characters
            page_text = page_data["text"].replace("\x00", "")
            active_section = page_data.get("active_section", "Overview")
            active_subsection = page_data.get("active_subsection", "")

            chunks = document_service.chunk_page_text(
                text=page_text,
                page_number=page_num,
                document_name=filename,
                active_section=active_section,
                active_subsection=active_subsection,
                target_chunk_size=CHUNK_SIZE,
                chunk_overlap=CHUNK_OVERLAP,
            )

            for c in chunks:
                cleaned_chunk_text = c["chunk_text"].replace("\x00", "").strip()
                if cleaned_chunk_text:
                    c["chunk_text"] = cleaned_chunk_text
                    all_chunk_dicts.append(c)

        total_chunks = len(all_chunk_dicts)
        logger.info(
            "Generated %s chunks for '%s' using chunk_size=%s and chunk_overlap=%s.",
            total_chunks,
            filename,
            CHUNK_SIZE,
            CHUNK_OVERLAP,
        )

        if total_chunks == 0:
            err_reason = "No chunks generated from extracted text."
            doc_record.status = "failed"
            doc_record.error_message = err_reason
            doc_record.processing_completed_at = datetime.now(timezone.utc)
            doc_record.updated_at = datetime.now(timezone.utc)
            db.commit()
            return {
                "filename": filename,
                "status": "failed",
                "reason": err_reason,
                "document_id": str(doc_record.id),
                "chunks": 0,
            }

        doc_record.total_chunks = total_chunks
        doc_record.embedded_chunks = 0
        db.commit()

        # Generate embeddings in batches and stage DocumentChunk objects in memory
        prepared_chunks: List[DocumentChunk] = []
        for start_index in range(0, total_chunks, BATCH_EMBED_SIZE):
            batch = all_chunk_dicts[start_index : start_index + BATCH_EMBED_SIZE]
            texts_to_embed = [chunk["chunk_text"] for chunk in batch]

            # Bounded retry mechanism for embedding generation
            embeddings = None
            last_embed_err = None
            for attempt in range(3):
                try:
                    embeddings = embedding_service.embed_batch(texts_to_embed)
                    if len(embeddings) == len(batch):
                        break
                except Exception as emb_exc:
                    last_embed_err = emb_exc
                    logger.warning(
                        "Embedding attempt %s/3 failed for '%s': %s",
                        attempt + 1,
                        filename,
                        emb_exc,
                    )
                    time.sleep(0.5 * (attempt + 1))

            if embeddings is None or len(embeddings) != len(batch):
                raise RuntimeError(
                    f"Embedding generation failed for '{filename}': {last_embed_err}"
                )

            # Validate each embedding vector (non-empty, exactly 384 dimensions)
            for offset, emb in enumerate(embeddings):
                if not emb or len(emb) != settings.EMBEDDING_DIM:
                    raise ValueError(
                        f"Invalid embedding vector for chunk {start_index + offset}: "
                        f"expected dimension {settings.EMBEDDING_DIM}, got {len(emb) if emb else 0}"
                    )

                chunk_data = batch[offset]
                metadata = dict(chunk_data.get("metadata", {}))
                metadata["document_id"] = str(doc_record.id)

                chunk_record = DocumentChunk(
                    document_id=doc_record.id,
                    document_name=filename,
                    chunk_index=start_index + offset,
                    page_number=chunk_data["page_number"],
                    section=chunk_data["section"],
                    chunk_text=chunk_data["chunk_text"],
                    metadata_json=json.dumps(metadata),
                    embedding=emb,
                )
                prepared_chunks.append(chunk_record)

            # Update live progress so status queries can observe real-time progress
            doc_record.embedded_chunks = len(prepared_chunks)
            doc_record.updated_at = datetime.now(timezone.utc)
            db.commit()

        # ATOMIC SWAP: All chunks and embeddings are validated.
        # Now remove any previous chunks and insert the newly prepared chunks.
        db.query(DocumentChunk).filter(
            DocumentChunk.document_id == doc_record.id
        ).delete(synchronize_session=False)

        db.add_all(prepared_chunks)

        doc_record.status = "completed"
        doc_record.total_chunks = total_chunks
        doc_record.embedded_chunks = total_chunks
        doc_record.processing_completed_at = datetime.now(timezone.utc)
        doc_record.updated_at = datetime.now(timezone.utc)
        doc_record.error_message = None
        db.commit()

        logger.info(
            "Successfully completed ingestion for '%s': %s pages, %s chunks.",
            filename,
            page_count,
            total_chunks,
        )

        # Invalidate retrieval caches immediately so new chunks are searchable
        try:
            retrieval_service.invalidate_cache()
            logger.info("Retrieval cache successfully invalidated.")
        except Exception as cache_exc:
            logger.warning("Could not invalidate retrieval cache: %s", cache_exc)

        return {
            "filename": filename,
            "status": "completed",
            "page_count": page_count,
            "chunks": total_chunks,
            "document_id": str(doc_record.id),
        }

    except Exception as exc:
        db.rollback()
        logger.exception("Failed during ingestion of '%s': %s", filename, exc)
        try:
            # Mark document as failed without deleting existing chunks
            if existing_doc or "doc_record" in locals():
                target_doc = existing_doc if existing_doc else doc_record
                target_doc.status = "failed"
                target_doc.error_message = str(exc)
                target_doc.processing_completed_at = datetime.now(timezone.utc)
                target_doc.updated_at = datetime.now(timezone.utc)
                db.commit()
        except Exception as status_err:
            logger.error("Could not record failure status for '%s': %s", filename, status_err)
            db.rollback()

        return {
            "filename": filename,
            "status": "failed",
            "reason": str(exc),
            "document_id": str(existing_doc.id) if existing_doc else None,
        }


def start_background_ingestion(
    file_path: Union[str, Path],
    document_id: str,
) -> None:
    """Run single document ingestion in a background thread guarded by INGESTION_LOCK."""
    def _worker():
        logger.info("Background ingestion thread started for document ID %s", document_id)
        with INGESTION_LOCK:
            db = SessionLocal()
            try:
                ingest_single_document(file_path, db, document_id=document_id)
            except Exception as e:
                logger.exception("Background worker error for document %s: %s", document_id, e)
            finally:
                db.close()
                logger.info("Background ingestion completed for document ID %s", document_id)

    worker_thread = threading.Thread(target=_worker, daemon=True)
    worker_thread.start()


def recover_interrupted_ingestions(db: Session) -> int:
    """
    On server startup, recover any documents stuck in 'processing' or 'uploaded'
    due to a crash or restart, transitioning them to 'failed' with a retryable message.
    """
    try:

        stuck_docs = (
            db.query(Document)
            .filter(Document.status.in_(["processing", "uploaded"]))
            .all()
        )
        count = len(stuck_docs)
        for doc in stuck_docs:
            doc.status = "failed"
            doc.error_message = "Interrupted by server restart (retryable)"
            doc.updated_at = datetime.now(timezone.utc)

        if count > 0:
            db.commit()
            logger.info("Recovered %s interrupted document ingestion(s).", count)
        return count
    except Exception as exc:
        logger.warning("Could not recover interrupted ingestions: %s", exc)
        db.rollback()
        return 0


def run_ingestion(
    db: Optional[Session] = None,
) -> List[Dict[str, Any]]:
    """
    Run the knowledge-base ingestion pipeline over all discovered files.
    Guarded by INGESTION_LOCK to ensure single-job concurrency.
    """
    validate_configuration()

    should_close_db = db is None
    if db is None:
        init_db()
        db = SessionLocal()

    with INGESTION_LOCK:
        results: List[Dict[str, Any]] = []
        try:
            doc_files = discover_knowledge_base_files()

            if not doc_files:
                logger.warning("No documents found in configured knowledge-base directories.")
                return results

            for doc_path in doc_files:
                result = ingest_single_document(
                    file_path=doc_path,
                    db=db,
                    force_reingest=FORCE_REINGEST,
                )
                results.append(result)

            try:
                retrieval_service.invalidate_cache()
            except Exception as exc:
                logger.warning("Retrieval cache invalidation failed: %s", exc)

            return results
        finally:
            if should_close_db:
                db.close()


if __name__ == "__main__":
    logger.info("Starting SAP Knowledge Assistant ingestion pipeline.")
    try:
        ingestion_results = run_ingestion()

        successful = sum(
            item["status"] in ("completed", "ingested")
            for item in ingestion_results
        )
        skipped = sum(
            item["status"] == "skipped"
            for item in ingestion_results
        )
        failed = sum(
            item["status"] == "failed"
            for item in ingestion_results
        )

        logger.info(
            "Ingestion summary: %s ingested/completed, %s skipped, %s failed.",
            successful,
            skipped,
            failed,
        )

        for item in ingestion_results:
            logger.info("%s", item)

        if failed:
            sys.exit(1)

    except Exception:
        logger.exception("Ingestion pipeline terminated unexpectedly.")
        sys.exit(1)
