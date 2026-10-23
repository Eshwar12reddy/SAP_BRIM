
import logging
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.app.config import settings

logger = logging.getLogger(__name__)

Base = declarative_base()


def get_engine():
    """Create a PostgreSQL-only engine. Never fall back to SQLite."""
    database_url = settings.DATABASE_URL

    if not database_url.startswith(("postgresql://", "postgresql+")):
        raise RuntimeError(
            "PostgreSQL is required. Configure DATABASE_URL with a PostgreSQL URL."
        )

    db_engine = create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5},
    )

    try:
        with db_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()

        logger.info("Successfully connected to PostgreSQL.")
        return db_engine

    except Exception as exc:
        db_engine.dispose()
        logger.critical(
            "PostgreSQL connection or pgvector initialization failed. "
            "SQLite fallback is disabled."
        )
        raise RuntimeError(
            "Cannot start the SAP Knowledge Assistant: PostgreSQL is unavailable "
            "or pgvector could not be initialized. Check DATABASE_URL, PostgreSQL, "
            "and database permissions."
        ) from exc


# PostgreSQL is the only supported database.
engine = get_engine()

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator:
    """Yield a database session and always close it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create tables and apply lightweight PostgreSQL schema migrations."""
    from backend.app.models import (
        user,
        chat,
        project,
        message,
        document,
        chunk,
        citation,
        web_source,
        memory,
        visual,
        attachment,
    )  # noqa: F401

    # Create tables declared by the SQLAlchemy models.
    Base.metadata.create_all(bind=engine)
    logger.info("PostgreSQL database tables initialized.")

    # Apply schema migrations in a PostgreSQL transaction.
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        # Chat sidebar pin state.
        conn.execute(
            text(
                "ALTER TABLE chats "
                "ADD COLUMN IF NOT EXISTS is_pinned "
                "BOOLEAN NOT NULL DEFAULT false"
            )
        )

        # User role.
        conn.execute(
            text(
                "ALTER TABLE users "
                "ADD COLUMN IF NOT EXISTS role VARCHAR(50) DEFAULT 'consultant'"
            )
        )

        conn.execute(
            text(
                "UPDATE users "
                "SET role = 'admin' "
                "WHERE is_admin = true "
                "AND (role IS NULL OR role = 'consultant')"
            )
        )

        # User memory preference.
        conn.execute(
            text(
                "ALTER TABLE users "
                "ADD COLUMN IF NOT EXISTS memory_enabled "
                "BOOLEAN NOT NULL DEFAULT true"
            )
        )

        # Message feedback.
        conn.execute(
            text(
                "ALTER TABLE messages "
                "ADD COLUMN IF NOT EXISTS feedback VARCHAR(20)"
            )
        )

        conn.execute(
            text(
                "ALTER TABLE messages "
                "ADD COLUMN IF NOT EXISTS feedback_comment TEXT"
            )
        )

        # Chat archive and temporary-chat state.
        conn.execute(
            text(
                "ALTER TABLE chats "
                "ADD COLUMN IF NOT EXISTS is_archived "
                "BOOLEAN NOT NULL DEFAULT false"
            )
        )

        conn.execute(
            text(
                "ALTER TABLE chats "
                "ADD COLUMN IF NOT EXISTS is_temporary "
                "BOOLEAN NOT NULL DEFAULT false"
            )
        )

        # User custom instructions.
        conn.execute(
            text(
                "ALTER TABLE users "
                "ADD COLUMN IF NOT EXISTS "
                "custom_instructions_about_user TEXT"
            )
        )

        conn.execute(
            text(
                "ALTER TABLE users "
                "ADD COLUMN IF NOT EXISTS "
                "custom_instructions_how_to_respond TEXT"
            )
        )

        # Chat attachments table and indexes
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS chat_attachments ("
                "id VARCHAR(36) PRIMARY KEY, "
                "chat_id VARCHAR(36) NOT NULL REFERENCES chats(id) ON DELETE CASCADE, "
                "message_id VARCHAR(36) REFERENCES messages(id) ON DELETE CASCADE, "
                "user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                "filename VARCHAR(255) NOT NULL, "
                "file_type VARCHAR(50) NOT NULL DEFAULT 'document', "
                "mime_type VARCHAR(100) NOT NULL, "
                "file_path VARCHAR(500) NOT NULL, "
                "size_bytes INTEGER NOT NULL DEFAULT 0, "
                "extracted_text TEXT, "
                "vision_metadata TEXT, "
                "created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL"
                ")"
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_chat_attachments_chat_id ON chat_attachments(chat_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_chat_attachments_message_id ON chat_attachments(message_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_chat_attachments_user_id ON chat_attachments(user_id)"))

    logger.info("PostgreSQL schema migrations completed.")

    # Create indexes for vector similarity and full-text retrieval.
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_document_chunks_embedding_hnsw "
                    "ON document_chunks USING hnsw "
                    "(embedding vector_cosine_ops)"
                )
            )

            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_document_chunks_fts "
                    "ON document_chunks USING gin "
                    "(to_tsvector('english', chunk_text))"
                )
            )

        logger.info(
            "PostgreSQL vector and full-text search indexes initialized."
        )

    except Exception:
        logger.exception(
            "Failed to initialize PostgreSQL retrieval indexes. "
            "Check pgvector, the document_chunks table, and embedding column."
        )
        raise


# Initialize at import time. Startup must fail if initialization fails.
init_db()
