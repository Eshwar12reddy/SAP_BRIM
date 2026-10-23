import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.main import app
from backend.app.database import Base, get_db
from backend.app.models.user import User
from backend.app.models.chat import Chat
from backend.app.models.message import Message
from backend.app.models.citation import Citation
from backend.app.security.auth import hash_password, create_access_token

from sqlalchemy.pool import StaticPool

# Test database in memory with StaticPool to share connection across FastAPI test threads
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)

Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def create_user_and_token(email: str = "test@clyptus.ai") -> tuple[User, str]:
    db = TestingSessionLocal()
    user = User(
        email=email,
        password_hash=hash_password("password123"),
        name="Test User",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(data={"sub": user.id, "email": user.email, "role": user.role})
    db.close()
    return user, token


def test_submit_message_feedback_up():
    user, token = create_user_and_token()
    headers = {"Authorization": f"Bearer {token}"}

    db = TestingSessionLocal()
    chat = Chat(user_id=user.id, title="SAP SOM Config Chat")
    db.add(chat)
    db.commit()

    msg = Message(
        chat_id=chat.id,
        role="assistant",
        content="Configure provider contracts via SPRO.",
        source_type="knowledge_base",
    )
    db.add(msg)
    db.commit()
    chat_id = chat.id
    msg_id = msg.id
    db.close()

    resp = client.post(
        f"/api/chats/{chat_id}/messages/{msg_id}/feedback",
        headers=headers,
        json={"rating": "up"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["message_id"] == msg_id
    assert data["feedback"] == "up"

    # Verify persisted in database
    db = TestingSessionLocal()
    persisted = db.query(Message).filter(Message.id == msg_id).first()
    assert persisted.feedback == "up"
    db.close()


def test_submit_message_feedback_down_with_comment():
    user, token = create_user_and_token()
    headers = {"Authorization": f"Bearer {token}"}

    db = TestingSessionLocal()
    chat = Chat(user_id=user.id, title="SAP CC Charging Chat")
    db.add(chat)
    db.commit()

    msg = Message(
        chat_id=chat.id,
        role="assistant",
        content="Initial answer was too generic.",
        source_type="web",
    )
    db.add(msg)
    db.commit()
    chat_id = chat.id
    msg_id = msg.id
    db.close()

    resp = client.post(
        f"/api/chats/{chat_id}/messages/{msg_id}/feedback",
        headers=headers,
        json={"rating": "down", "comment": "Need specific transaction codes."},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["feedback"] == "down"
    assert data["feedback_comment"] == "Need specific transaction codes."


def test_feedback_user_isolation():
    user1, token1 = create_user_and_token("user1@clyptus.ai")
    user2, token2 = create_user_and_token("user2@clyptus.ai")

    db = TestingSessionLocal()
    chat = Chat(user_id=user1.id, title="User 1 Secret Chat")
    db.add(chat)
    db.commit()

    msg = Message(chat_id=chat.id, role="assistant", content="User 1 answer")
    db.add(msg)
    db.commit()
    chat_id = chat.id
    msg_id = msg.id
    db.close()

    # User 2 attempts to submit feedback on User 1's message -> 404
    resp = client.post(
        f"/api/chats/{chat_id}/messages/{msg_id}/feedback",
        headers={"Authorization": f"Bearer {token2}"},
        json={"rating": "up"},
    )
    assert resp.status_code == 404


def test_export_chat_markdown():
    user, token = create_user_and_token()
    headers = {"Authorization": f"Bearer {token}"}

    db = TestingSessionLocal()
    chat = Chat(user_id=user.id, title="SAP BRIM Troubleshooting")
    db.add(chat)
    db.commit()

    m1 = Message(chat_id=chat.id, role="user", content="How to resolve duplicate invoices?")
    m2 = Message(chat_id=chat.id, role="assistant", content="1. Check DFKKINVDOC in CI.", source_type="knowledge_base")
    db.add_all([m1, m2])
    db.commit()
    chat_id = chat.id
    db.close()

    resp = client.get(f"/api/chats/{chat_id}/export?format=markdown", headers=headers)
    assert resp.status_code == 200
    assert "text/markdown" in resp.headers["content-type"]
    text = resp.text
    assert "# SAP BRIM Troubleshooting" in text
    assert "How to resolve duplicate invoices?" in text
    assert "Check DFKKINVDOC in CI." in text
    assert "attachment; filename=" in resp.headers["content-disposition"]


def test_export_chat_json():
    user, token = create_user_and_token()
    headers = {"Authorization": f"Bearer {token}"}

    db = TestingSessionLocal()
    chat = Chat(user_id=user.id, title="FI-CA Account Balance")
    db.add(chat)
    db.commit()

    m1 = Message(chat_id=chat.id, role="user", content="What is FPL9?")
    m2 = Message(chat_id=chat.id, role="assistant", content="FPL9 is the account balance display transaction.")
    db.add_all([m1, m2])
    db.commit()
    chat_id = chat.id
    db.close()

    resp = client.get(f"/api/chats/{chat_id}/export?format=json", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "FI-CA Account Balance"
    assert data["message_count"] == 2
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][1]["role"] == "assistant"


def test_export_chat_txt():
    user, token = create_user_and_token()
    headers = {"Authorization": f"Bearer {token}"}

    db = TestingSessionLocal()
    chat = Chat(user_id=user.id, title="Plain Text Chat")
    db.add(chat)
    db.commit()

    m1 = Message(chat_id=chat.id, role="user", content="Question 1")
    db.add(m1)
    db.commit()
    chat_id = chat.id
    db.close()

    resp = client.get(f"/api/chats/{chat_id}/export?format=txt", headers=headers)
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    assert "CLYPTUS.AI CONVERSATION EXPORT" in resp.text
    assert "Question 1" in resp.text


def test_export_chat_isolation():
    user1, token1 = create_user_and_token("user1@clyptus.ai")
    user2, token2 = create_user_and_token("user2@clyptus.ai")

    db = TestingSessionLocal()
    chat = Chat(user_id=user1.id, title="User 1 Private Chat")
    db.add(chat)
    db.commit()
    chat_id = chat.id
    db.close()

    # User 2 attempts to export User 1's chat -> 404
    resp = client.get(
        f"/api/chats/{chat_id}/export?format=markdown",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp.status_code == 404


def test_upload_chat_attachment_text():
    import io
    user, token = create_user_and_token()
    headers = {"Authorization": f"Bearer {token}"}

    db = TestingSessionLocal()
    chat = Chat(user_id=user.id, title="Attachment Chat")
    db.add(chat)
    db.commit()
    chat_id = chat.id
    db.close()

    file_content = b"SAP SOM Provider Contract configuration notes: SPRO path: Cross-Industry Solutions."
    files = {"file": ("config_notes.txt", io.BytesIO(file_content), "text/plain")}

    resp = client.post(f"/api/chats/{chat_id}/attachment", headers=headers, files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["filename"] == "config_notes.txt"
    assert "Provider Contract" in data["extracted_text"]
    assert data["size_bytes"] == len(file_content)


def test_upload_chat_attachment_isolation():
    import io
    user1, token1 = create_user_and_token("user1_att@clyptus.ai")
    user2, token2 = create_user_and_token("user2_att@clyptus.ai")

    db = TestingSessionLocal()
    chat = Chat(user_id=user1.id, title="User 1 Secret Attachment Chat")
    db.add(chat)
    db.commit()
    chat_id = chat.id
    db.close()

    files = {"file": ("test.txt", io.BytesIO(b"Confidential spec"), "text/plain")}

    # User 2 tries to attach file to User 1's chat -> 404
    resp = client.post(
        f"/api/chats/{chat_id}/attachment",
        headers={"Authorization": f"Bearer {token2}"},
        files=files,
    )
    assert resp.status_code == 404


def test_upload_chat_attachment_invalid_extension():
    import io
    user, token = create_user_and_token()
    headers = {"Authorization": f"Bearer {token}"}

    db = TestingSessionLocal()
    chat = Chat(user_id=user.id, title="Bad Attachment Chat")
    db.add(chat)
    db.commit()
    chat_id = chat.id
    db.close()

    files = {"file": ("malicious.exe", io.BytesIO(b"executable content"), "application/octet-stream")}
    resp = client.post(f"/api/chats/{chat_id}/attachment", headers=headers, files=files)
    assert resp.status_code == 400
    assert "Unsupported file type" in resp.json()["detail"]


def test_custom_instructions_get_and_put():
    user, token = create_user_and_token("custom_inst@clyptus.ai")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Initially empty
    get_resp = client.get("/api/auth/custom-instructions", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["about_user"] is None
    assert get_resp.json()["how_to_respond"] is None

    # 2. Update custom instructions
    put_resp = client.put(
        "/api/auth/custom-instructions",
        headers=headers,
        json={
            "about_user": "Senior Solution Architect for SAP CI/CC high volume telco billing",
            "how_to_respond": "Always provide SPRO customizing paths and database tables",
        },
    )
    assert put_resp.status_code == 200
    data = put_resp.json()
    assert "telco billing" in data["about_user"]
    assert "SPRO" in data["how_to_respond"]

    # 3. Verify persisted in DB
    get_resp2 = client.get("/api/auth/custom-instructions", headers=headers)
    assert get_resp2.status_code == 200
    assert get_resp2.json()["about_user"] == data["about_user"]
    assert get_resp2.json()["how_to_respond"] == data["how_to_respond"]


def test_temporary_chat_creation_and_listing():
    user, token = create_user_and_token("temp_chat_user@clyptus.ai")
    headers = {"Authorization": f"Bearer {token}"}

    # Create temporary chat
    temp_resp = client.post(
        "/api/chats",
        headers=headers,
        json={"title": "Private Incognito Chat", "is_temporary": True},
    )
    assert temp_resp.status_code == 201
    assert temp_resp.json()["is_temporary"] is True
    temp_id = temp_resp.json()["id"]

    # Temporary chat should NOT be listed in persistent chat list
    list_resp = client.get("/api/chats", headers=headers)
    assert list_resp.status_code == 200
    chat_ids = [c["id"] for c in list_resp.json()]
    assert temp_id not in chat_ids


def test_chat_archiving_and_filtering():
    user, token = create_user_and_token("archive_user@clyptus.ai")
    headers = {"Authorization": f"Bearer {token}"}

    # Create regular chat
    chat_resp = client.post(
        "/api/chats",
        headers=headers,
        json={"title": "Archivable Chat"},
    )
    chat_id = chat_resp.json()["id"]

    # Archive the chat
    patch_resp = client.patch(
        f"/api/chats/{chat_id}",
        headers=headers,
        json={"is_archived": True},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["is_archived"] is True

    # By default, list_chats excludes archived
    normal_list = client.get("/api/chats", headers=headers).json()
    assert chat_id not in [c["id"] for c in normal_list]

    # When include_archived=true, it is returned
    archived_list = client.get("/api/chats?include_archived=true", headers=headers).json()
    assert chat_id in [c["id"] for c in archived_list]


def test_refresh_after_completion_restores_persisted_history():
    """Scenario B: Refresh after completion restores complete response and does not regenerate."""
    user, token = create_user_and_token("refresh_b@clyptus.ai")
    headers = {"Authorization": f"Bearer {token}"}

    db = TestingSessionLocal()
    chat = Chat(user_id=user.id, title="SAP SOM Replication Chat")
    db.add(chat)
    db.commit()
    chat_id = chat.id

    u_msg = Message(chat_id=chat_id, role="user", content="How does SOM replication work?")
    db.add(u_msg)
    db.commit()

    a_msg = Message(
        chat_id=chat_id,
        role="assistant",
        content="SOM provider contracts replicate to SAP CC as charged items.",
        source_type="knowledge_base",
        grounding_score=0.92,
    )
    db.add(a_msg)
    db.commit()
    db.refresh(a_msg)

    # Attach citation
    cit = Citation(
        message_id=a_msg.id,
        source_type="knowledge_base",
        document_id="doc-som-guide",
        document_name="SOM_Replication_Guide.pdf",
        chunk_id="chunk-1",
        page_number=14,
        section="Contract Replication",
        similarity_score=0.89,
        citation_text="Provider contracts replicate to CC charging.",
    )
    db.add(cit)
    db.commit()
    db.close()

    # Simulate browser refresh: GET /chats/{chat_id}/messages
    resp = client.get(f"/api/chats/{chat_id}/messages", headers=headers)
    assert resp.status_code == 200
    msgs = resp.json()

    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "How does SOM replication work?"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["content"] == "SOM provider contracts replicate to SAP CC as charged items."
    assert msgs[1]["source_type"] == "knowledge_base"
    assert msgs[1]["grounding_score"] == 0.92
    assert len(msgs[1]["citations"]) == 1
    assert msgs[1]["citations"][0]["document"] == "SOM_Replication_Guide.pdf"


def test_refresh_during_streaming_preserves_prior_messages_and_marks_interrupted():
    """Scenario A: Refresh during streaming recovers interrupted state and preserves prior history."""
    user, token = create_user_and_token("refresh_a@clyptus.ai")
    headers = {"Authorization": f"Bearer {token}"}

    db = TestingSessionLocal()
    chat = Chat(user_id=user.id, title="Interrupted Stream Chat")
    db.add(chat)
    db.commit()
    chat_id = chat.id

    # Prior completed turn
    db.add(Message(chat_id=chat_id, role="user", content="Prior completed question"))
    db.add(Message(chat_id=chat_id, role="assistant", content="Prior completed answer", source_type="knowledge_base"))
    # Incomplete turn: user message was submitted, but refresh occurred before stream completed
    db.add(Message(chat_id=chat_id, role="user", content="Interrupted query mid-stream"))
    db.commit()
    db.close()

    # Browser refreshes and reloads messages
    resp = client.get(f"/api/chats/{chat_id}/messages", headers=headers)
    assert resp.status_code == 200
    msgs = resp.json()

    # Prior messages preserved
    assert len(msgs) == 4
    assert msgs[0]["content"] == "Prior completed question"
    assert msgs[1]["content"] == "Prior completed answer"
    assert msgs[2]["content"] == "Interrupted query mid-stream"

    # Interrupted state generated safely without crashing
    assert msgs[3]["role"] == "assistant"
    assert msgs[3]["source_type"] == "interrupted"
    assert "interrupted" in msgs[3]["content"].lower()


def test_no_duplicate_assistant_messages_on_save_partial_and_refresh():
    """Scenario A & C: Stopping or disconnecting does not create duplicate assistant rows."""
    user, token = create_user_and_token("duplicate_guard@clyptus.ai")
    headers = {"Authorization": f"Bearer {token}"}

    db = TestingSessionLocal()
    chat = Chat(user_id=user.id, title="Clearing Chat")
    db.add(chat)
    db.commit()
    chat_id = chat.id

    db.add(Message(chat_id=chat_id, role="user", content="Explain FPL9 clearing"))
    db.commit()
    db.close()

    # Frontend calls /save-partial when user clicks stop
    resp1 = client.post(
        f"/api/chats/{chat_id}/messages/save-partial",
        headers=headers,
        json={"content": "FPL9 contract account balance shows..."},
    )
    assert resp1.status_code == 200
    saved_id = resp1.json()["message_id"]

    # If stream disconnect handler or another save-partial fires with updated content
    resp2 = client.post(
        f"/api/chats/{chat_id}/messages/save-partial",
        headers=headers,
        json={"content": "FPL9 contract account balance shows all open items and clearing."},
    )
    assert resp2.status_code == 200
    # Must update the existing interrupted message rather than creating duplicate
    assert resp2.json()["status"] == "updated"
    assert resp2.json()["message_id"] == saved_id

    # On page refresh, messages query should only contain 1 user and 1 assistant message
    get_resp = client.get(f"/api/chats/{chat_id}/messages", headers=headers)
    assert get_resp.status_code == 200
    msgs = get_resp.json()
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["id"] == saved_id
    assert msgs[1]["source_type"] == "interrupted"


def test_reopening_conversation_restores_complete_history():
    """Scenario C: Reopening chat restores all messages in chronological order."""
    user, token = create_user_and_token("reopen_chat@clyptus.ai")
    headers = {"Authorization": f"Bearer {token}"}

    db = TestingSessionLocal()
    chat = Chat(user_id=user.id, title="Chronological Chat")
    db.add(chat)
    db.commit()
    chat_id = chat.id

    for i in range(3):
        db.add(Message(chat_id=chat_id, role="user", content=f"Question {i+1}"))
        db.add(Message(chat_id=chat_id, role="assistant", content=f"Answer {i+1}", source_type="knowledge_base"))
    db.commit()
    db.close()

    resp = client.get(f"/api/chats/{chat_id}/messages", headers=headers)
    assert resp.status_code == 200
    msgs = resp.json()
    assert len(msgs) == 6
    assert [m["content"] for m in msgs] == [
        "Question 1", "Answer 1",
        "Question 2", "Answer 2",
        "Question 3", "Answer 3"
    ]


