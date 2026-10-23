-- Migration: 001_add_document_status_columns.sql
-- Description: Adds ingestion lifecycle status and progress tracking columns to 'documents' table.
-- Safety: Completely idempotent via IF NOT EXISTS. Safe to run against PostgreSQL.
-- Backfill: Backfills existing documents as 'completed' and populates chunk counts from 'document_chunks'.

-- 1. Add status tracking columns
ALTER TABLE documents ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'completed';
ALTER TABLE documents ADD COLUMN IF NOT EXISTS total_pages INTEGER DEFAULT 0;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS extracted_chars INTEGER DEFAULT 0;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS total_chunks INTEGER DEFAULT 0;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS embedded_chunks INTEGER DEFAULT 0;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS error_message TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS processing_started_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS processing_completed_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;

-- 2. Index status for high-performance job queue & admin polling
CREATE INDEX IF NOT EXISTS ix_documents_status ON documents(status);

-- 3. Backfill existing 28 documents as completed (do not mark them failed or uploaded)
UPDATE documents 
SET status = 'completed',
    total_pages = COALESCE(NULLIF(total_pages, 0), page_count, 0),
    updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)
WHERE status IS NULL OR status = 'completed';

-- 4. Backfill chunk counts for existing documents from document_chunks
UPDATE documents d
SET total_chunks = sub.chunk_count,
    embedded_chunks = sub.embedded_count
FROM (
    SELECT document_id, 
           COUNT(*) as chunk_count,
           COUNT(CASE WHEN embedding IS NOT NULL THEN 1 END) as embedded_count
    FROM document_chunks
    GROUP BY document_id
) sub
WHERE d.id = sub.document_id;
