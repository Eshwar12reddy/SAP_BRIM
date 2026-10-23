-- Migration: 002_add_chat_attachments_table.sql
-- Description: Ensures 'chat_attachments' table exists with all necessary columns and user-isolation indexes.
-- Safety: Completely additive and idempotent via IF NOT EXISTS. Safe to execute against PostgreSQL.

CREATE TABLE IF NOT EXISTS chat_attachments (
    id VARCHAR(36) PRIMARY KEY,
    chat_id VARCHAR(36) NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    message_id VARCHAR(36) REFERENCES messages(id) ON DELETE CASCADE,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    file_type VARCHAR(50) NOT NULL DEFAULT 'document',
    mime_type VARCHAR(100) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    extracted_text TEXT,
    vision_metadata TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Indexes for fast query lookup and user isolation
CREATE INDEX IF NOT EXISTS ix_chat_attachments_chat_id ON chat_attachments(chat_id);
CREATE INDEX IF NOT EXISTS ix_chat_attachments_message_id ON chat_attachments(message_id);
CREATE INDEX IF NOT EXISTS ix_chat_attachments_user_id ON chat_attachments(user_id);
