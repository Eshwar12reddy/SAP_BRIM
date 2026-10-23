import { getStoredToken } from './api';

const API_BASE_URL = 'http://localhost:8000/api';

const getAuthHeaders = (): Record<string, string> => {
  const token = getStoredToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
};

export interface FileStats {
  total_documents: number;
  completed: number;
  pending: number;
  processing: number;
  failed: number;
  total_chunks: number;
  missing_embeddings: number;
}

export interface FileUploadItem {
  filename: string;
  status: 'uploaded' | 'skipped' | 'failed';
  message: string;
  document_id?: string;
  file_hash?: string;
  size_bytes?: number;
  error?: string;
}

export interface BulkUploadResponse {
  total_received: number;
  successful: number;
  skipped: number;
  failed: number;
  results: FileUploadItem[];
}

export interface AdminFileItem {
  id: string;
  filename: string;
  title: string;
  category: string;
  description?: string | null;
  file_type: string;
  size_bytes: number;
  status: 'completed' | 'processing' | 'pending' | 'failed' | 'uploaded';
  total_pages: number;
  extracted_chars: number;
  total_chunks: number;
  embedded_chunks: number;
  has_binary: boolean;
  error_message?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface AdminFileListResponse {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  items: AdminFileItem[];
}

export interface ChunkItem {
  id: string;
  document_id: string;
  chunk_index: number;
  page_number: number;
  section?: string | null;
  chunk_text: string;
  has_embedding: boolean;
  text_length: number;
}

export interface FileChunksResponse {
  document_id: string;
  document_title: string;
  total_chunks: number;
  page: number;
  page_size: number;
  total_pages: number;
  chunks: ChunkItem[];
}

export interface AuditLogItem {
  id: string;
  user_id?: string | null;
  admin_email: string;
  action: string;
  target_id?: string | null;
  target_name?: string | null;
  details?: string | null;
  ip_address?: string | null;
  created_at?: string;
}

export interface AuditLogListResponse {
  total: number;
  page: number;
  page_size: number;
  items: AuditLogItem[];
}

// 1. Get File Stats
export const apiGetFileStats = async (): Promise<FileStats> => {
  const resp = await fetch(`${API_BASE_URL}/admin/files/stats`, {
    headers: { ...getAuthHeaders() },
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to fetch knowledge base stats');
  }
  return resp.json();
};

// 2. Bulk Upload Files
export const apiBulkUploadFiles = async (files: File[]): Promise<BulkUploadResponse> => {
  const formData = new FormData();
  files.forEach((file) => {
    formData.append('files', file);
  });

  const headers = getAuthHeaders();
  // Do NOT set Content-Type header so browser sets multipart boundary automatically
  const resp = await fetch(`${API_BASE_URL}/admin/files/upload`, {
    method: 'POST',
    headers,
    body: formData,
  });

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || 'Bulk upload failed');
  }
  return resp.json();
};

// 3. List Files with Search & Filters
export const apiGetFilesList = async (params: {
  page?: number;
  page_size?: number;
  search?: string;
  status?: string;
  file_type?: string;
  sort_by?: string;
  sort_order?: string;
}): Promise<AdminFileListResponse> => {
  const searchParams = new URLSearchParams();
  if (params.page) searchParams.set('page', params.page.toString());
  if (params.page_size) searchParams.set('page_size', params.page_size.toString());
  if (params.search) searchParams.set('search', params.search);
  if (params.status && params.status !== 'all') searchParams.set('status', params.status);
  if (params.file_type && params.file_type !== 'all') searchParams.set('file_type', params.file_type);
  if (params.sort_by) searchParams.set('sort_by', params.sort_by);
  if (params.sort_order) searchParams.set('sort_order', params.sort_order);

  const resp = await fetch(`${API_BASE_URL}/admin/files/list?${searchParams.toString()}`, {
    headers: { ...getAuthHeaders() },
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to fetch files list');
  }
  return resp.json();
};

// 4. Get File Detail
export const apiGetFileDetail = async (id: string): Promise<AdminFileItem> => {
  const resp = await fetch(`${API_BASE_URL}/admin/files/${id}`, {
    headers: { ...getAuthHeaders() },
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to fetch file details');
  }
  return resp.json();
};

// 5. Get File Chunks
export const apiGetFileChunks = async (
  id: string,
  page: number = 1,
  pageSize: number = 10
): Promise<FileChunksResponse> => {
  const resp = await fetch(`${API_BASE_URL}/admin/files/${id}/chunks?page=${page}&page_size=${pageSize}`, {
    headers: { ...getAuthHeaders() },
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to fetch chunks');
  }
  return resp.json();
};

// 6. Download Original File
export const apiDownloadFile = async (id: string, filename: string): Promise<void> => {
  const resp = await fetch(`${API_BASE_URL}/admin/files/${id}/download`, {
    headers: { ...getAuthHeaders() },
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to download file');
  }
  const blob = await resp.blob();
  const downloadUrl = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = downloadUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(downloadUrl);
};

// 7. Update Metadata
export const apiUpdateFileMetadata = async (
  id: string,
  updates: { title?: string; category?: string; description?: string }
): Promise<AdminFileItem> => {
  const resp = await fetch(`${API_BASE_URL}/admin/files/${id}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify(updates),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to update file metadata');
  }
  return resp.json();
};

// 8. Replace File
export const apiReplaceFile = async (id: string, file: File): Promise<AdminFileItem> => {
  const formData = new FormData();
  formData.append('file', file);

  const resp = await fetch(`${API_BASE_URL}/admin/files/${id}/replace`, {
    method: 'POST',
    headers: { ...getAuthHeaders() },
    body: formData,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to replace file');
  }
  return resp.json();
};

// 9. Re-index File
export const apiReindexFile = async (id: string): Promise<AdminFileItem> => {
  const resp = await fetch(`${API_BASE_URL}/admin/files/${id}/reindex`, {
    method: 'POST',
    headers: { ...getAuthHeaders() },
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to reindex file');
  }
  return resp.json();
};

// 10. Delete Single File
export const apiDeleteFile = async (id: string): Promise<void> => {
  const resp = await fetch(`${API_BASE_URL}/admin/files/${id}`, {
    method: 'DELETE',
    headers: { ...getAuthHeaders() },
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to delete file');
  }
};

// 11. Bulk Delete Files
export const apiBulkDeleteFiles = async (ids: string[]): Promise<{ deleted_count: number }> => {
  const resp = await fetch(`${API_BASE_URL}/admin/files/bulk`, {
    method: 'DELETE',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify({ ids }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to perform bulk delete');
  }
  return resp.json();
};

// 12. Delete ALL Files (Requires "DELETE" confirmation)
export const apiDeleteAllFiles = async (confirmation: string): Promise<void> => {
  const resp = await fetch(`${API_BASE_URL}/admin/files/all`, {
    method: 'DELETE',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify({ confirmation }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to delete all files');
  }
};

// 13. Audit Logs
export const apiGetAuditLogs = async (
  page: number = 1,
  pageSize: number = 20,
  action?: string
): Promise<AuditLogListResponse> => {
  const searchParams = new URLSearchParams();
  searchParams.set('page', page.toString());
  searchParams.set('page_size', pageSize.toString());
  if (action) searchParams.set('action', action);

  const resp = await fetch(`${API_BASE_URL}/admin/files/audit-logs?${searchParams.toString()}`, {
    headers: { ...getAuthHeaders() },
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to fetch audit logs');
  }
  return resp.json();
};
