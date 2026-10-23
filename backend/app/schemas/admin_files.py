from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class FileStatsResponse(BaseModel):
    total_documents: int = 0
    completed: int = 0
    pending: int = 0
    processing: int = 0
    failed: int = 0
    total_chunks: int = 0
    missing_embeddings: int = 0


class FileUploadItemResult(BaseModel):
    filename: str
    status: str  # "uploaded", "skipped", "failed"
    message: str
    document_id: Optional[str] = None
    file_hash: Optional[str] = None
    size_bytes: int = 0
    error: Optional[str] = None


class BulkUploadResponse(BaseModel):
    total_received: int
    successful: int
    skipped: int
    failed: int
    results: List[FileUploadItemResult]


class FileListItem(BaseModel):
    id: str
    filename: str
    title: str
    category: Optional[str] = "General"
    description: Optional[str] = None
    file_type: str
    size_bytes: int = 0
    status: str
    total_pages: int = 0
    extracted_chars: int = 0
    total_chunks: int = 0
    embedded_chunks: int = 0
    has_binary: bool = False
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class FileListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    items: List[FileListItem]


class FileDetailResponse(BaseModel):
    id: str
    filename: str
    title: str
    category: Optional[str] = "General"
    description: Optional[str] = None
    file_type: str
    size_bytes: int = 0
    file_hash: str
    version: str = "1.0"
    status: str
    total_pages: int = 0
    extracted_chars: int = 0
    total_chunks: int = 0
    embedded_chunks: int = 0
    has_binary: bool = False
    error_message: Optional[str] = None
    processing_started_at: Optional[str] = None
    processing_completed_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ChunkItem(BaseModel):
    id: str
    document_id: str
    chunk_index: int
    page_number: int
    section: Optional[str] = None
    chunk_text: str
    has_embedding: bool
    text_length: int


class FileChunksResponse(BaseModel):
    document_id: str
    document_title: str
    total_chunks: int
    page: int
    page_size: int
    total_pages: int
    chunks: List[ChunkItem]


class FileMetadataUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    category: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None


class BulkDeleteRequest(BaseModel):
    ids: List[str] = Field(..., min_length=1)


class DeleteAllRequest(BaseModel):
    confirmation: str = Field(
        ...,
        description="Must be strictly 'DELETE' to confirm destructive purge of all files."
    )


class AuditLogItem(BaseModel):
    id: str
    user_id: Optional[str] = None
    admin_email: str
    action: str
    target_id: Optional[str] = None
    target_name: Optional[str] = None
    details: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: Optional[str] = None


class AuditLogListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[AuditLogItem]
