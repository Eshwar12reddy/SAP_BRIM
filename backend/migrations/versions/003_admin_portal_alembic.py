"""add admin portal tables and columns

Revision ID: 003_admin_portal
Revises: 002_add_chat_attachments
Create Date: 2026-10-16 16:50:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003_admin_portal'
down_revision = '002_add_chat_attachments'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Additive columns on documents
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS category VARCHAR(100) DEFAULT 'General'")
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS description TEXT")
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS size_bytes INTEGER DEFAULT 0")

    # 2. kb_document_binaries
    op.execute("""
        CREATE TABLE IF NOT EXISTS kb_document_binaries (
            id VARCHAR(36) PRIMARY KEY,
            document_id VARCHAR(36) NOT NULL UNIQUE REFERENCES documents(id) ON DELETE CASCADE,
            file_bytes BYTEA NOT NULL,
            file_size INTEGER NOT NULL DEFAULT 0,
            content_type VARCHAR(100) NOT NULL DEFAULT 'application/octet-stream',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_kb_document_binaries_doc_id ON kb_document_binaries(document_id)")

    # 3. admin_audit_log
    op.execute("""
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
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_admin_audit_log_email ON admin_audit_log(admin_email)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_admin_audit_log_action ON admin_audit_log(action)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_admin_audit_log_created_at ON admin_audit_log(created_at)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS admin_audit_log")
    op.execute("DROP TABLE IF EXISTS kb_document_binaries")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS size_bytes")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS description")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS category")
