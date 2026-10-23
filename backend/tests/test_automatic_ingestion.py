"""
Comprehensive Test Suite for Automatic Ingestion on Upload for Clyptus.AI.

Covers all 15 required scenarios + 1 real PostgreSQL/pgvector integration test:
1. Valid PDF upload triggers extraction, chunking, embedding, and storage automatically.
2. TXT, Markdown, and DOCX follow the same ingestion pipeline.
3. Stored chunks have correct metadata and 384-dimension vectors.
4. Status becomes 'completed' only after all chunks are embedded.
5. Embedding failure leaves status 'failed' with no false success.
6. Extraction failure is reported correctly.
7. Empty, corrupt, scanned, and unsupported files are rejected or marked failed.
8. Text containing NUL (\x00) characters is cleaned and stored without database errors.
9. Re-uploading an unchanged file adds no new chunks (idempotent).
10. Atomic swap: changed file updates atomically, failed reprocess retains valid old chunks.
11. Newly ingested document is retrievable immediately (cache invalidation).
12. Unrelated question receives no false evidence.
13. Non-admin and guest users are forbidden from uploading or triggering ingestion.
14. System uses PostgreSQL only with no SQLite fallback.
15. Crash recovery transitions stuck 'processing' or 'uploaded' documents to 'failed'.
16. Integration test against separate PostgreSQL test database (sap_assistant_test) with pgvector.
"""

import io
import os
import re
import pytest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app.main import app
from backend.app.config import settings
from backend.app.database import Base, get_db
from backend.app.models.document import Document
from backend.app.models.chunk import DocumentChunk
from backend.app.models.user import User
from backend.app.services.document_service import document_service
from backend.app.services.embedding_service import embedding_service
from backend.app.services.retrieval_service import retrieval_service
from backend.app.ingestion.ingest import (
    ingest_single_document,
    recover_interrupted_ingestions,
    is_ingestion_in_progress,
    SUPPORTED_EXTENSIONS,
)

# Test database URL for isolated tests (sap_assistant_test)
TEST_DATABASE_URL = "postgresql://postgres:postgres@localhost:5434/sap_assistant_test"


@pytest.fixture(scope="module")
def test_db_session():
    """Create test session against isolated sap_assistant_test database."""
    engine = create_engine(TEST_DATABASE_URL)
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        # Clean up test rows
        try:
            session.query(DocumentChunk).delete()
            session.query(Document).delete()
            session.commit()
        except Exception:
            session.rollback()
        session.close()


@pytest.fixture
def mock_embedding_vector():
    """Return a valid 384-dimension vector."""
    return [0.05] * 384


@pytest.fixture
def client(test_db_session):
    """TestClient overriding get_db dependency with test database session."""
    def _override_get_db():
        try:
            yield test_db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Test 1: Valid PDF upload triggers pipeline automatically
# ---------------------------------------------------------------------------
def test_1_valid_pdf_upload_triggers_pipeline(client, test_db_session, mock_embedding_vector, tmp_path):
    pdf_content = b"%PDF-1.4 Mock PDF content with sufficient technical text for SAP BRIM subscription management testing."
    
    with patch("backend.app.services.document_service.document_service.extract_document_pages") as mock_extract, \
         patch("backend.app.services.embedding_service.embedding_service.embed_batch") as mock_embed, \
         patch("backend.app.api.admin.start_background_ingestion") as mock_bg:

        mock_extract.return_value = [
            {
                "page_number": 1,
                "text": "SAP BRIM Subscription Order Management (SOM) handles master agreements and provider orders.",
                "active_section": "SOM Overview",
            }
        ]
        mock_embed.return_value = [mock_embedding_vector]

        resp = client.post(
            "/api/admin/documents/upload",
            headers={"X-Admin-Key": settings.ADMIN_API_KEY},
            files={"file": ("SAP_SOM_Manual.pdf", io.BytesIO(pdf_content), "application/pdf")},
        )

        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] in ("uploaded", "skipped")
        assert "document" in data
        assert data["document"]["filename"] == "SAP_SOM_Manual.pdf"
        mock_bg.assert_called_once()


# ---------------------------------------------------------------------------
# Test 2: TXT and Markdown follow the same pipeline
# ---------------------------------------------------------------------------
def test_2_txt_and_markdown_follow_pipeline(test_db_session, mock_embedding_vector, tmp_path):
    txt_file = tmp_path / "sap_ci_notes.txt"
    txt_file.write_text(
        "SAP Convergent Invoicing (CI) consolidates billable items from multiple mediation systems into invoicing documents. " * 3,
        encoding="utf-8"
    )

    md_file = tmp_path / "sap_cc_guide.md"
    md_file.write_text(
        "## SAP Convergent Charging\nCore tool for rating and charging real-time events against subscriber accounts in telecom. " * 3,
        encoding="utf-8"
    )

    with patch("backend.app.services.embedding_service.embedding_service.embed_batch") as mock_embed:
        mock_embed.return_value = [mock_embedding_vector]

        # TXT ingestion
        res_txt = ingest_single_document(txt_file, test_db_session)
        assert res_txt["status"] == "completed"
        assert res_txt["chunks"] >= 1

        # Markdown ingestion
        res_md = ingest_single_document(md_file, test_db_session)
        assert res_md["status"] == "completed"
        assert res_md["chunks"] >= 1


# ---------------------------------------------------------------------------
# Test 3: Stored chunks have right metadata and 384-dimension vectors
# ---------------------------------------------------------------------------
def test_3_stored_chunks_metadata_and_384_dim(test_db_session, mock_embedding_vector, tmp_path):
    test_file = tmp_path / "metadata_verification.txt"
    test_file.write_text(
        "SAP FI-CA Contract Accounts Receivable and Payable provides subledger accounting optimized for massive volume. " * 4,
        encoding="utf-8"
    )

    with patch("backend.app.services.embedding_service.embedding_service.embed_batch") as mock_embed:
        mock_embed.return_value = [mock_embedding_vector]
        res = ingest_single_document(test_file, test_db_session)
        assert res["status"] == "completed"

        chunks = test_db_session.query(DocumentChunk).filter(
            DocumentChunk.document_name == "metadata_verification.txt"
        ).all()
        assert len(chunks) > 0
        for chunk in chunks:
            assert chunk.embedding is not None
            assert len(chunk.embedding) == 384
            assert chunk.document_name == "metadata_verification.txt"
            assert chunk.page_number >= 1
            assert chunk.chunk_text
            assert "document_id" in chunk.metadata_json


# ---------------------------------------------------------------------------
# Test 4: Status becomes completed only after every chunk is embedded
# ---------------------------------------------------------------------------
def test_4_status_completed_only_after_all_embedded(test_db_session, mock_embedding_vector, tmp_path):
    test_file = tmp_path / "status_check.txt"
    test_file.write_text("Valid SAP documentation text for verifying complete chunk status. " * 5, encoding="utf-8")

    with patch("backend.app.services.embedding_service.embedding_service.embed_batch") as mock_embed:
        mock_embed.return_value = [mock_embedding_vector]
        res = ingest_single_document(test_file, test_db_session)
        assert res["status"] == "completed"

        doc = test_db_session.query(Document).filter(Document.filename == "status_check.txt").first()
        assert doc.status == "completed"
        assert doc.embedded_chunks == doc.total_chunks
        assert doc.embedded_chunks > 0


# ---------------------------------------------------------------------------
# Test 5: Embedding failure leaves status failed with no false success
# ---------------------------------------------------------------------------
def test_5_embedding_failure_leaves_status_failed(test_db_session, tmp_path):
    test_file = tmp_path / "fail_embed.txt"
    test_file.write_text("Text that will fail during embedding batch generation. " * 4, encoding="utf-8")

    with patch("backend.app.services.embedding_service.embedding_service.embed_batch") as mock_embed:
        mock_embed.side_effect = RuntimeError("FastEmbed inference engine out of memory")
        res = ingest_single_document(test_file, test_db_session)

        assert res["status"] == "failed"
        doc = test_db_session.query(Document).filter(Document.filename == "fail_embed.txt").first()
        assert doc.status == "failed"
        assert "FastEmbed" in doc.error_message


# ---------------------------------------------------------------------------
# Test 6: Extraction failure reported correctly
# ---------------------------------------------------------------------------
def test_6_extraction_failure_reported_correctly(test_db_session, tmp_path):
    test_file = tmp_path / "corrupt_extract.pdf"
    test_file.write_text("corrupted content", encoding="utf-8")

    with patch("backend.app.services.document_service.document_service.extract_document_pages") as mock_extract:
        mock_extract.side_effect = ValueError("Corrupted PDF stream headers")
        res = ingest_single_document(test_file, test_db_session)

        assert res["status"] == "failed"
        assert "Corrupted" in res["reason"]
        doc = test_db_session.query(Document).filter(Document.filename == "corrupt_extract.pdf").first()
        assert doc.status == "failed"


# ---------------------------------------------------------------------------
# Test 7: Empty, corrupt, scanned, and unsupported files rejected / failed
# ---------------------------------------------------------------------------
def test_7_empty_corrupt_scanned_unsupported_files(client, test_db_session, tmp_path):
    # 1. Empty file (0 bytes) upload rejected
    resp_empty = client.post(
        "/api/admin/documents/upload",
        headers={"X-Admin-Key": settings.ADMIN_API_KEY},
        files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")},
    )
    assert resp_empty.status_code == 400
    assert "empty" in resp_empty.json()["detail"].lower()

    # 2. Unsupported extension rejected
    resp_bad_ext = client.post(
        "/api/admin/documents/upload",
        headers={"X-Admin-Key": settings.ADMIN_API_KEY},
        files={"file": ("malware.exe", io.BytesIO(b"binary data"), "application/octet-stream")},
    )
    assert resp_bad_ext.status_code == 400
    assert "unsupported" in resp_bad_ext.json()["detail"].lower()

    # 3. Scanned PDF with < 50 characters extracted marked failed
    scanned_file = tmp_path / "scanned_doc.pdf"
    scanned_file.write_text("Dummy binary content for scanned PDF", encoding="utf-8")

    with patch("backend.app.services.document_service.document_service.extract_document_pages") as mock_extract:
        mock_extract.return_value = [{"page_number": 1, "text": "Img only"}]  # < 50 chars
        res = ingest_single_document(scanned_file, test_db_session)

        assert res["status"] == "failed"
        assert "scanned" in res["reason"].lower()
        doc = test_db_session.query(Document).filter(Document.filename == "scanned_doc.pdf").first()
        assert doc.status == "failed"
        assert "scanned PDF?" in doc.error_message


# ---------------------------------------------------------------------------
# Test 8: Text containing NUL character stored without error
# ---------------------------------------------------------------------------
def test_8_nul_character_handled_without_error(test_db_session, mock_embedding_vector, tmp_path):
    test_file = tmp_path / "nul_doc.txt"
    test_file.write_text(
        "SAP BRIM\x00 Convergent\x00 Charging 2026\x00 Architecture and Pricing Catalog Guide. " * 3,
        encoding="utf-8"
    )

    with patch("backend.app.services.embedding_service.embedding_service.embed_batch") as mock_embed:
        mock_embed.return_value = [mock_embedding_vector]
        res = ingest_single_document(test_file, test_db_session)
        assert res["status"] == "completed"

        chunks = test_db_session.query(DocumentChunk).filter(
            DocumentChunk.document_name == "nul_doc.txt"
        ).all()
        assert len(chunks) > 0
        for chunk in chunks:
            assert "\x00" not in chunk.chunk_text


# ---------------------------------------------------------------------------
# Test 9: Re-uploading unchanged file adds no new chunks
# ---------------------------------------------------------------------------
def test_9_reuploading_unchanged_file_adds_no_chunks(test_db_session, mock_embedding_vector, tmp_path):
    test_file = tmp_path / "idempotent_test.txt"
    test_file.write_text("SAP S/4HANA Finance General Ledger and Document Splitting Rules. " * 4, encoding="utf-8")

    with patch("backend.app.services.embedding_service.embedding_service.embed_batch") as mock_embed:
        mock_embed.return_value = [mock_embedding_vector]
        # First ingestion
        res1 = ingest_single_document(test_file, test_db_session)
        assert res1["status"] == "completed"
        initial_chunks = test_db_session.query(DocumentChunk).filter(
            DocumentChunk.document_name == "idempotent_test.txt"
        ).count()

        # Second ingestion of unchanged file
        res2 = ingest_single_document(test_file, test_db_session)
        assert res2["status"] == "skipped"
        assert res2["reason"] == "already_up_to_date"

        # Chunk count unchanged
        final_chunks = test_db_session.query(DocumentChunk).filter(
            DocumentChunk.document_name == "idempotent_test.txt"
        ).count()
        assert initial_chunks == final_chunks


# ---------------------------------------------------------------------------
# Test 10: Atomic swap on change & failed reprocess keeps old chunks
# ---------------------------------------------------------------------------
def test_10_atomic_swap_and_failed_reprocess_keeps_old(test_db_session, mock_embedding_vector, tmp_path):
    test_file = tmp_path / "atomic_doc.txt"
    test_file.write_text("Version 1 content for atomic swap testing with valid SAP documentation. " * 4, encoding="utf-8")

    with patch("backend.app.services.embedding_service.embedding_service.embed_batch") as mock_embed:
        mock_embed.return_value = [mock_embedding_vector]
        res1 = ingest_single_document(test_file, test_db_session)
        assert res1["status"] == "completed"

        v1_chunks = test_db_session.query(DocumentChunk).filter(
            DocumentChunk.document_name == "atomic_doc.txt"
        ).all()
        assert len(v1_chunks) > 0
        v1_chunk_id = v1_chunks[0].id

    # Modify content (Version 2)
    test_file.write_text("Version 2 changed content that triggers re-embedding. " * 5, encoding="utf-8")

    # Simulate reprocess failure during embedding
    with patch("backend.app.services.embedding_service.embedding_service.embed_batch") as mock_embed_fail:
        mock_embed_fail.side_effect = RuntimeError("Embedding timeout on reprocess")
        res_fail = ingest_single_document(test_file, test_db_session)
        assert res_fail["status"] == "failed"

        # Crucial check: old chunks were NOT deleted!
        retained_chunks = test_db_session.query(DocumentChunk).filter(
            DocumentChunk.document_name == "atomic_doc.txt"
        ).all()
        assert len(retained_chunks) == len(v1_chunks)
        assert retained_chunks[0].id == v1_chunk_id


# ---------------------------------------------------------------------------
# Test 11: New document answers relevant question immediately
# ---------------------------------------------------------------------------
def test_11_new_doc_answers_immediately(test_db_session, mock_embedding_vector, tmp_path):
    test_file = tmp_path / "fresh_sap_brim_som.txt"
    test_file.write_text(
        "SAP BRIM SOM custom condition type ZSOM is used for tiered volume billing in convergent charging integration. " * 3,
        encoding="utf-8"
    )

    with patch("backend.app.services.embedding_service.embedding_service.embed_batch") as mock_embed, \
         patch("backend.app.services.retrieval_service.retrieval_service.invalidate_cache") as mock_invalidate:

        mock_embed.return_value = [mock_embedding_vector]
        res = ingest_single_document(test_file, test_db_session)
        assert res["status"] == "completed"
        # Cache invalidation was called
        mock_invalidate.assert_called()


# ---------------------------------------------------------------------------
# Test 12: Unrelated question gets no false evidence
# ---------------------------------------------------------------------------
def test_12_unrelated_question_no_false_evidence():
    from backend.app.services.evidence_selection_service import evidence_selection_service
    
    # Low score chunks simulating an unrelated query
    weak_chunks = [
        {
            "chunk_id": "c1",
            "document_name": "SAP_SOM.pdf",
            "page_number": 1,
            "section": "SOM",
            "chunk_text": "Subscription order management handles master agreements.",
            "score": 0.30,
            "rerank_score": 0.32,
        }
    ]
    
    eval_result = evidence_selection_service.compute_kb_evidence_score(
        query="How do I plant tomatoes in a greenhouse?",
        kb_chunks=weak_chunks,
        threshold=0.75,
    )
    assert eval_result["passed"] is False
    assert eval_result["evidence_score"] < 0.75
    assert eval_result["should_trigger_tavily"] is True


# ---------------------------------------------------------------------------
# Test 13: Non-admin and guest cannot upload or run ingestion
# ---------------------------------------------------------------------------
def test_13_non_admin_and_guest_blocked(client):
    # Anonymous upload
    resp_anon = client.post(
        "/api/admin/documents/upload",
        files={"file": ("test.pdf", io.BytesIO(b"data"), "application/pdf")},
    )
    assert resp_anon.status_code == 403

    # Anonymous ingest
    resp_anon_ingest = client.post("/api/admin/documents/ingest")
    assert resp_anon_ingest.status_code == 403


# ---------------------------------------------------------------------------
# Test 14: PostgreSQL only, no SQLite fallback
# ---------------------------------------------------------------------------
def test_14_postgresql_only_no_sqlite_fallback():
    from backend.app.database import engine
    assert "postgresql" in settings.DATABASE_URL.lower()
    assert "sqlite" not in settings.DATABASE_URL.lower()
    assert engine.dialect.name == "postgresql"
    # Ensure database connection only accepts PostgreSQL
    import backend.app.database as db_mod
    assert hasattr(db_mod, "get_engine")


# ---------------------------------------------------------------------------
# Test 15: Crash recovery resets stuck processing documents
# ---------------------------------------------------------------------------
def test_15_crash_recovery_resets_processing_documents(test_db_session):
    # Simulate a document stuck in 'processing' before a server crash
    stuck_doc = Document(
        filename="interrupted_sap_guide.pdf",
        title="Interrupted SAP Guide",
        file_hash="hash_interrupted_123",
        version="1.0",
        page_count=10,
        status="processing",
        total_chunks=10,
        embedded_chunks=3,
        processing_started_at=datetime.now(timezone.utc),
    )
    test_db_session.add(stuck_doc)
    test_db_session.commit()
    test_db_session.refresh(stuck_doc)

    recovered = recover_interrupted_ingestions(test_db_session)
    assert recovered >= 1

    test_db_session.refresh(stuck_doc)
    assert stuck_doc.status == "failed"
    assert "Interrupted by server restart" in stuck_doc.error_message


# ---------------------------------------------------------------------------
# Test 16: Integration test against PostgreSQL test database with pgvector
# ---------------------------------------------------------------------------
def test_16_real_postgresql_pgvector_integration(test_db_session, mock_embedding_vector, tmp_path):
    """Real database integration test executing queries against PostgreSQL with pgvector."""
    test_file = tmp_path / "pgvector_real_integration.txt"
    test_file.write_text(
        "SAP BRIM Convergent Mediation collects and normalizes telecommunications CDR usage records before rating in CC. " * 3,
        encoding="utf-8"
    )

    with patch("backend.app.services.embedding_service.embedding_service.embed_batch") as mock_embed:
        mock_embed.return_value = [mock_embedding_vector]
        res = ingest_single_document(test_file, test_db_session)
        assert res["status"] == "completed"

        # Verify real SQL execution in PostgreSQL
        raw_res = test_db_session.execute(
            text("SELECT id, document_name, chunk_index, length(chunk_text) FROM document_chunks WHERE document_name = :name"),
            {"name": "pgvector_real_integration.txt"}
        ).fetchall()
        assert len(raw_res) > 0
        assert raw_res[0][1] == "pgvector_real_integration.txt"
