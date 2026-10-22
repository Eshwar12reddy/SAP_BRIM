"""
PostgreSQL-backed integration tests for Visual Asset Foreign Key Integrity,
UUID handling, user isolation, and resilient error recovery.
Runs against dedicated test database (TEST_DATABASE_URL).
"""

import os
import uuid
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app.config import settings
from backend.app.database import Base
from backend.app.models.user import User
from backend.app.models.chat import Chat
from backend.app.models.message import Message
from backend.app.models.visual import VisualAsset
from backend.app.services.visual.visual_service import visual_service
from backend.app.services.visual.visual_cache import get_cached_visual, compute_cache_key

# Ground rule: Tests must run against a dedicated PostgreSQL test database or schema
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    settings.DATABASE_URL.rsplit("/", 1)[0] + "/sap_assistant_test"
)


@pytest.fixture(scope="module")
def pg_engine():
    if not TEST_DATABASE_URL.startswith("postgresql"):
        pytest.skip("PostgreSQL test database required.")
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(bind=engine)
    yield engine
    # Cleanup tables on teardown
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def pg_session(pg_engine):
    Session = sessionmaker(bind=pg_engine, autocommit=False, autoflush=False)
    session = Session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def test_visual_asset_fk_with_valid_uuid(pg_session):
    """Valid UUID chat ID succeeds in creating visual placeholder in PostgreSQL."""
    user_id = str(uuid.uuid4())
    chat_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())

    user = User(id=user_id, email=f"user_{user_id[:8]}@example.com", name="Test User", password_hash="dummy")
    chat = Chat(id=chat_id, user_id=user_id, title="Valid UUID Chat")
    msg = Message(id=message_id, chat_id=chat_id, role="assistant", content="Here is the architecture.")

    pg_session.add_all([user, chat, msg])
    pg_session.commit()

    # Plan visual with explicit request
    placeholders = visual_service.plan_and_create_placeholders(
        db=pg_session,
        user_id=user_id,
        chat_id=chat_id,
        message_id=message_id,
        query="show an architecture diagram of SAP BRIM",
        answer_text="Here is the architecture.",
    )

    assert len(placeholders) > 0
    asset_id = placeholders[0]["visual_id"]

    # Verify asset is persisted in PostgreSQL with correct UUID chat_id
    asset = pg_session.query(VisualAsset).filter(VisualAsset.id == asset_id).first()
    assert asset is not None
    assert str(asset.chat_id) == chat_id
    assert str(asset.user_id) == user_id
    assert str(asset.message_id) == message_id


def test_visual_asset_fk_nonexistent_chat_rejected_cleanly(pg_session):
    """Nonexistent chat is rejected cleanly without PostgreSQL ForeignKeyViolation exception."""
    user_id = str(uuid.uuid4())
    fake_chat_id = str(uuid.uuid4())
    fake_msg_id = str(uuid.uuid4())

    user = User(id=user_id, email=f"user_{user_id[:8]}@example.com", name="Test User", password_hash="dummy")
    pg_session.add(user)
    pg_session.commit()

    # Attempt visual placeholder on nonexistent chat (or hardcoded '1')
    placeholders = visual_service.plan_and_create_placeholders(
        db=pg_session,
        user_id=user_id,
        chat_id=fake_chat_id,
        message_id=fake_msg_id,
        query="show an architecture diagram of SAP BRIM",
        answer_text="Here is the architecture.",
    )

    # Must be safely skipped, returning empty list without DB exception
    assert placeholders == []


def test_visual_asset_cross_user_isolation(pg_session):
    """User B cannot create or view visual assets for User A's chat."""
    user_a_id = str(uuid.uuid4())
    user_b_id = str(uuid.uuid4())
    chat_a_id = str(uuid.uuid4())

    user_a = User(id=user_a_id, email=f"user_a_{user_a_id[:8]}@example.com", name="User A", password_hash="dummy")
    user_b = User(id=user_b_id, email=f"user_b_{user_b_id[:8]}@example.com", name="User B", password_hash="dummy")
    chat_a = Chat(id=chat_a_id, user_id=user_a_id, title="User A Chat")

    pg_session.add_all([user_a, user_b, chat_a])
    pg_session.commit()

    # User B attempts to plan visual on User A's chat -> rejected
    b_placeholders = visual_service.plan_and_create_placeholders(
        db=pg_session,
        user_id=user_b_id,
        chat_id=chat_a_id,
        query="show an architecture diagram of SAP BRIM",
        answer_text="Here is the architecture.",
    )
    assert b_placeholders == []

    # Now User A plans visual on own chat -> succeeds
    a_placeholders = visual_service.plan_and_create_placeholders(
        db=pg_session,
        user_id=user_a_id,
        chat_id=chat_a_id,
        query="show an architecture diagram of SAP BRIM",
        answer_text="Here is the architecture.",
    )
    assert len(a_placeholders) > 0
    vis_id = a_placeholders[0]["visual_id"]

    # User B cannot access User A's visual metadata
    meta_for_b = visual_service.get_visual_meta(pg_session, visual_id=vis_id, user_id=user_b_id)
    assert meta_for_b is None

    # User A can access own visual metadata
    meta_for_a = visual_service.get_visual_meta(pg_session, visual_id=vis_id, user_id=user_a_id)
    assert meta_for_a is not None


def test_visual_failure_preserves_text_answer(pg_session):
    """If visual generation fails, the already-generated text response is kept and persisted."""
    user_id = str(uuid.uuid4())
    chat_id = str(uuid.uuid4())
    msg_id = str(uuid.uuid4())

    user = User(id=user_id, email=f"user_{user_id[:8]}@example.com", name="Test User", password_hash="dummy")
    chat = Chat(id=chat_id, user_id=user_id, title="Resilience Chat")
    msg = Message(
        id=msg_id,
        chat_id=chat_id,
        role="assistant",
        content="This is the fully completed answer explaining SOM and CI.",
        source_type="knowledge_base",
    )
    pg_session.add_all([user, chat, msg])
    pg_session.commit()

    # Simulate an error inside visual planning (e.g. invalid DB state or broken spec)
    try:
        # Pass a bogus chat_id to simulate an error in visual planning
        visual_service.plan_and_create_placeholders(
            db=pg_session,
            user_id=user_id,
            chat_id="nonexistent-chat-id",
            message_id=msg_id,
            query="draw something",
            answer_text=msg.content,
        )
    except Exception:
        pg_session.rollback()

    # Verify the message in DB remains intact and committed
    persisted_msg = pg_session.query(Message).filter(Message.id == msg_id).first()
    assert persisted_msg is not None
    assert persisted_msg.content == "This is the fully completed answer explaining SOM and CI."
