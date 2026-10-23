-- Migration: 003_add_admin_portal_tables.sql
-- Description: Creates kb_document_binaries, admin_audit_log, and adds additive metadata columns to documents.
-- Safety: Completely additive and idempotent via IF NOT EXISTS. Safe to execute against PostgreSQL.

-- 1. Add additive columns to documents table
ALTER TABLE documents ADD COLUMN IF NOT EXISTS category VARCHAR(100) DEFAULT 'General';
ALTER TABLE documents ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS size_bytes INTEGER DEFAULT 0;

-- 2. Create kb_document_binaries table for storing original file binaries directly in PostgreSQL
CREATE TABLE IF NOT EXISTS kb_document_binaries (
    id VARCHAR(36) PRIMARY KEY,
    document_id VARCHAR(36) NOT NULL UNIQUE REFERENCES documents(id) ON DELETE CASCADE,
    file_bytes BYTEA NOT NULL,
    file_size INTEGER NOT NULL DEFAULT 0,
    content_type VARCHAR(100) NOT NULL DEFAULT 'application/octet-stream',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_kb_document_binaries_doc_id ON kb_document_binaries(document_id);

-- 3. Create admin_audit_log table for tracking all admin CRUD activities
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
);

CREATE INDEX IF NOT EXISTS ix_admin_audit_log_email ON admin_audit_log(admin_email);
CREATE INDEX IF NOT EXISTS ix_admin_audit_log_action ON admin_audit_log(action);
CREATE INDEX IF NOT EXISTS ix_admin_audit_log_created_at ON admin_audit_log(created_at);
