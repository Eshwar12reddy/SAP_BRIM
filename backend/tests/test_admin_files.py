import io
import time
import uuid
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.main import app
from backend.app.database import get_db, SessionLocal
from backend.app.models.user import User
from backend.app.models.document import Document
from backend.app.models.chunk import DocumentChunk
from backend.app.models.admin_portal import KBDocumentBinary, AdminAuditLog
from backend.app.security.auth import hash_password, create_access_token

client = TestClient(app)


@pytest.fixture
def admin_auth_headers():
    db: Session = SessionLocal()
    try:
        email = f"admin_test_{uuid.uuid4().hex[:6]}@clyptus.ai"
        user = User(
            id=str(uuid.uuid4()),
            email=email,
            name="Super Admin",
            password_hash=hash_password("AdminPass123!"),
            is_admin=True,
            role="admin",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        token = create_access_token(data={"sub": str(user.id)})
        return {"Authorization": f"Bearer {token}"}, user
    finally:
        db.close()


@pytest.fixture
def non_admin_auth_headers():
    db: Session = SessionLocal()
    try:
        email = f"consultant_{uuid.uuid4().hex[:6]}@clyptus.ai"
        user = User(
            id=str(uuid.uuid4()),
            email=email,
            name="Normal Consultant",
            password_hash=hash_password("ConsultantPass123!"),
            is_admin=False,
            role="consultant",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        token = create_access_token(data={"sub": str(user.id)})
        return {"Authorization": f"Bearer {token}"}, user
    finally:
        db.close()


def test_admin_access_control(non_admin_auth_headers):
    headers, _ = non_admin_auth_headers

    # 1. Non-admin must get 403 Forbidden
    resp = client.get("/api/admin/files/stats", headers=headers)
    assert resp.status_code == 403
    assert "administrator" in resp.json()["detail"].lower()

    # 2. Unauthenticated must get 401 Unauthorized
    resp_unauth = client.get("/api/admin/files/stats")
    assert resp_unauth.status_code in (401, 403)


def test_admin_stats(admin_auth_headers):
    headers, _ = admin_auth_headers
    resp = client.get("/api/admin/files/stats", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_documents" in data
    assert "completed" in data
    assert "total_chunks" in data
    assert "missing_embeddings" in data


def test_upload_and_crud_lifecycle(admin_auth_headers):
    headers, admin_user = admin_auth_headers

    # Mock embeddings to be fast 384-dim dummy vectors
    with patch(
        "backend.app.services.embedding_service.EmbeddingService.embed_batch",
        return_value=[[0.05] * 384, [0.08] * 384],
    ):
        # 1. Upload new document
        unique_name = f"test_sap_brim_{uuid.uuid4().hex[:6]}.txt"
        sample_txt = f"Run ID: {unique_name}\nSection 1.0: SAP Billing and Revenue Overview.\nBRIM provides convergent charging and invoicing.\n"
        files = [
            ("files", (unique_name, io.BytesIO(sample_txt.encode("utf-8")), "text/plain"))
        ]

        upload_resp = client.post("/api/admin/files/upload", files=files, headers=headers)
        assert upload_resp.status_code == 201
        upload_data = upload_resp.json()
        assert upload_data["successful"] == 1
        doc_id = upload_data["results"][0]["document_id"]
        assert doc_id is not None
        time.sleep(1.0)

        # 2. Duplicate detection
        dup_files = [
            ("files", (unique_name, io.BytesIO(sample_txt.encode("utf-8")), "text/plain"))
        ]
        dup_resp = client.post("/api/admin/files/upload", files=dup_files, headers=headers)
        assert dup_resp.status_code == 201
        assert dup_resp.json()["skipped"] == 1

        # 3. List files
        list_resp = client.get(f"/api/admin/files/list?search={unique_name[:15]}", headers=headers)
        assert list_resp.status_code == 200
        items = list_resp.json()["items"]
        assert len(items) >= 1
        matched = next((item for item in items if item["id"] == doc_id), None)
        assert matched is not None
        assert matched["filename"] == unique_name

        # 4. Get File Detail
        detail_resp = client.get(f"/api/admin/files/{doc_id}", headers=headers)
        assert detail_resp.status_code == 200
        assert detail_resp.json()["id"] == doc_id

        # 5. Get File Chunks
        chunks_resp = client.get(f"/api/admin/files/{doc_id}/chunks", headers=headers)
        assert chunks_resp.status_code == 200
        chunks_data = chunks_resp.json()
        assert "chunks" in chunks_data

        # 6. Update Metadata
        update_resp = client.put(
            f"/api/admin/files/{doc_id}",
            json={"title": "Updated SAP BRIM Guide Title", "category": "SOM", "description": "Core SOM handbook"},
            headers=headers,
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["title"] == "Updated SAP BRIM Guide Title"
        assert update_resp.json()["category"] == "SOM"

        # 7. Download original binary
        dl_resp = client.get(f"/api/admin/files/{doc_id}/download", headers=headers)
        assert dl_resp.status_code == 200
        assert len(dl_resp.content) > 0

        # 8. Re-index
        reindex_resp = client.post(f"/api/admin/files/{doc_id}/reindex", headers=headers)
        assert reindex_resp.status_code == 200

        # 9. Audit log entry check
        audit_resp = client.get("/api/admin/files/audit-logs", headers=headers)
        assert audit_resp.status_code == 200
        assert audit_resp.json()["total"] > 0

        # 10. Delete Single Document
        del_resp = client.delete(f"/api/admin/files/{doc_id}", headers=headers)
        assert del_resp.status_code == 200

        # Verify deletion
        get_deleted = client.get(f"/api/admin/files/{doc_id}", headers=headers)
        assert get_deleted.status_code == 404


def test_bulk_delete(admin_auth_headers):
    headers, _ = admin_auth_headers

    with patch(
        "backend.app.services.embedding_service.EmbeddingService.embed_batch",
        return_value=[[0.1] * 384],
    ):
        files = [
            ("files", ("bulk_doc_1.txt", io.BytesIO(b"Doc 1 content for bulk delete testing."), "text/plain")),
            ("files", ("bulk_doc_2.txt", io.BytesIO(b"Doc 2 content for bulk delete testing."), "text/plain")),
        ]
        upload_resp = client.post("/api/admin/files/upload", files=files, headers=headers)
        doc_ids = [r["document_id"] for r in upload_resp.json()["results"] if r["document_id"]]

        assert len(doc_ids) == 2
        time.sleep(1.0)

        bulk_del_resp = client.request(
            "DELETE",
            "/api/admin/files/bulk",
            json={"ids": doc_ids},
            headers=headers,
        )
        assert bulk_del_resp.status_code == 200
        assert bulk_del_resp.json()["deleted_count"] == 2


def test_delete_all_confirmation_protection(admin_auth_headers):
    headers, _ = admin_auth_headers

    # 1. Invalid confirmation string must be rejected
    bad_req = client.request(
        "DELETE",
        "/api/admin/files/all",
        json={"confirmation": "delete"},  # Lowercase should fail
        headers=headers,
    )
    assert bad_req.status_code == 400

    bad_req_wrong = client.request(
        "DELETE",
        "/api/admin/files/all",
        json={"confirmation": "YES"},
        headers=headers,
    )
    assert bad_req_wrong.status_code == 400
