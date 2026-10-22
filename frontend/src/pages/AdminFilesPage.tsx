import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import {
  UploadCloud,
  FileText,
  CheckCircle2,
  Clock,
  AlertTriangle,
  Layers,
  Search,
  Filter,
  RefreshCw,
  Trash2,
  Download,
  Edit3,
  RotateCw,
  FileCode,
  FileSpreadsheet,
  AlertCircle,
  X,
  ChevronLeft,
  ChevronRight,
  ShieldAlert,
  ArrowLeft,
  Check,
  FileUp,
  History,
  Info,
  Database,
  ArrowUpDown,
  Sun,
  Moon,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import {
  apiGetFileStats,
  apiGetFilesList,
  apiBulkUploadFiles,
  apiGetFileChunks,
  apiDownloadFile,
  apiUpdateFileMetadata,
  apiReplaceFile,
  apiReindexFile,
  apiDeleteFile,
  apiBulkDeleteFiles,
  apiDeleteAllFiles,
  apiGetAuditLogs,
} from '../services/adminApi';
import type {
  FileStats,
  AdminFileItem,
  ChunkItem,
  AuditLogItem,
  FileUploadItem,
} from '../services/adminApi';

export const AdminFilesPage: React.FC = () => {
  const navigate = useNavigate();
  const { user } = useAuth();

  // State: Theme (Default to White Backed / Light Mode as requested)
  const [isDark, setIsDark] = useState<boolean>(() => {
    const saved = localStorage.getItem('clyptus-admin-theme');
    if (saved) return saved === 'dark';
    return false; // Default to clean white-backed interface
  });

  useEffect(() => {
    localStorage.setItem('clyptus-admin-theme', isDark ? 'dark' : 'light');
    if (isDark) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [isDark]);

  // State: Stats
  const [stats, setStats] = useState<FileStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);

  // State: File List & Pagination
  const [files, setFiles] = useState<AdminFileItem[]>([]);
  const [totalFiles, setTotalFiles] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all');
  const [sortBy, setSortBy] = useState('created_at');
  const [sortOrder, setSortOrder] = useState('desc');
  const [listLoading, setListLoading] = useState(false);

  // State: Selection
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  // State: Upload
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadResults, setUploadResults] = useState<FileUploadItem[] | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // State: Modals
  const [chunksModalDoc, setChunksModalDoc] = useState<AdminFileItem | null>(null);
  const [chunks, setChunks] = useState<ChunkItem[]>([]);
  const [chunksPage, setChunksPage] = useState(1);
  const [chunksTotalPages, setChunksTotalPages] = useState(1);
  const [chunksTotalCount, setChunksTotalCount] = useState(0);
  const [chunksLoading, setChunksLoading] = useState(false);

  const [editModalDoc, setEditModalDoc] = useState<AdminFileItem | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [editCategory, setEditCategory] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [isSavingEdit, setIsSavingEdit] = useState(false);

  const [replaceModalDoc, setReplaceModalDoc] = useState<AdminFileItem | null>(null);
  const [replaceFile, setReplaceFile] = useState<File | null>(null);
  const [isReplacing, setIsReplacing] = useState(false);

  const [deleteConfirmDoc, setDeleteConfirmDoc] = useState<AdminFileItem | null>(null);
  const [isDeletingSingle, setIsDeletingSingle] = useState(false);

  const [isBulkDeleteModalOpen, setIsBulkDeleteModalOpen] = useState(false);
  const [isBulkDeleting, setIsBulkDeleting] = useState(false);

  const [isDeleteAllModalOpen, setIsDeleteAllModalOpen] = useState(false);
  const [deleteAllConfirmation, setDeleteAllConfirmation] = useState('');
  const [isDeletingAll, setIsDeletingAll] = useState(false);

  const [isAuditModalOpen, setIsAuditModalOpen] = useState(false);
  const [auditLogs, setAuditLogs] = useState<AuditLogItem[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditPage, setAuditPage] = useState(1);
  const [auditTotalPages, setAuditTotalPages] = useState(1);

  // Notification Toast
  const [toast, setToast] = useState<{ type: 'success' | 'error' | 'info'; message: string } | null>(null);

  const showToast = useCallback((message: string, type: 'success' | 'error' | 'info' = 'info') => {
    setToast({ type, message });
    setTimeout(() => setToast(null), 4500);
  }, []);

  // 1. Fetch Stats
  const loadStats = useCallback(async () => {
    try {
      setStatsLoading(true);
      const data = await apiGetFileStats();
      setStats(data);
    } catch (err: any) {
      console.error('Failed to load stats:', err);
    } finally {
      setStatsLoading(false);
    }
  }, []);

  // 2. Fetch File List
  const loadFiles = useCallback(async () => {
    try {
      setListLoading(true);
      const res = await apiGetFilesList({
        page: currentPage,
        page_size: pageSize,
        search: searchQuery,
        status: statusFilter,
        file_type: typeFilter,
        sort_by: sortBy,
        sort_order: sortOrder,
      });
      setFiles(res.items);
      setTotalFiles(res.total);
      setTotalPages(res.total_pages);
    } catch (err: any) {
      showToast(err.message || 'Failed to load file list', 'error');
    } finally {
      setListLoading(false);
    }
  }, [currentPage, pageSize, searchQuery, statusFilter, typeFilter, sortBy, sortOrder, showToast]);

  // Initial load
  useEffect(() => {
    loadStats();
    loadFiles();
  }, [loadStats, loadFiles]);

  // Polling every 2.5s if any file is processing or pending
  useEffect(() => {
    const hasActiveJobs = files.some(
      (f) => f.status === 'processing' || f.status === 'pending' || f.status === 'uploaded'
    );
    if (!hasActiveJobs) return;

    const interval = setInterval(() => {
      loadStats();
      loadFiles();
    }, 2500);

    return () => clearInterval(interval);
  }, [files, loadStats, loadFiles]);

  // Drag and Drop handlers
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const newFiles = Array.from(e.dataTransfer.files);
      setUploadFiles((prev) => [...prev, ...newFiles]);
    }
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const newFiles = Array.from(e.target.files);
      setUploadFiles((prev) => [...prev, ...newFiles]);
    }
  };

  const removeUploadFile = (index: number) => {
    setUploadFiles((prev) => prev.filter((_, i) => i !== index));
  };

  // Submit Bulk Upload
  const handleStartUpload = async () => {
    if (uploadFiles.length === 0) return;
    try {
      setIsUploading(true);
      const res = await apiBulkUploadFiles(uploadFiles);
      setUploadResults(res.results);
      setUploadFiles([]);
      if (fileInputRef.current) fileInputRef.current.value = '';

      showToast(
        `Upload complete: ${res.successful} added, ${res.skipped} skipped, ${res.failed} failed.`,
        res.failed > 0 ? 'error' : 'success'
      );
      loadStats();
      loadFiles();
    } catch (err: any) {
      showToast(err.message || 'Bulk upload failed', 'error');
    } finally {
      setIsUploading(false);
    }
  };

  // Select / Deselect All
  const handleSelectAll = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.checked) {
      setSelectedIds(files.map((f) => f.id));
    } else {
      setSelectedIds([]);
    }
  };

  const toggleSelectOne = (id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  // Inspect Chunks Modal
  const openChunksModal = async (doc: AdminFileItem, page: number = 1) => {
    setChunksModalDoc(doc);
    setChunksPage(page);
    try {
      setChunksLoading(true);
      const res = await apiGetFileChunks(doc.id, page, 8);
      setChunks(res.chunks);
      setChunksTotalCount(res.total_chunks);
      setChunksTotalPages(res.total_pages);
    } catch (err: any) {
      showToast(err.message || 'Failed to load chunks', 'error');
    } finally {
      setChunksLoading(false);
    }
  };

  // Download File
  const handleDownload = async (file: AdminFileItem) => {
    try {
      showToast(`Initiating download for '${file.filename}'...`, 'info');
      await apiDownloadFile(file.id, file.filename);
      showToast(`Downloaded '${file.filename}'`, 'success');
    } catch (err: any) {
      showToast(err.message || 'Download failed', 'error');
    }
  };

  // Open Edit Metadata Modal
  const openEditModal = (file: AdminFileItem) => {
    setEditModalDoc(file);
    setEditTitle(file.title);
    setEditCategory(file.category || '');
    setEditDescription(file.description || '');
  };

  // Save Metadata Changes
  const handleSaveEdit = async () => {
    if (!editModalDoc) return;
    try {
      setIsSavingEdit(true);
      await apiUpdateFileMetadata(editModalDoc.id, {
        title: editTitle.trim(),
        category: editCategory.trim(),
        description: editDescription.trim(),
      });
      showToast('Document metadata updated successfully', 'success');
      setEditModalDoc(null);
      loadStats();
      loadFiles();
    } catch (err: any) {
      showToast(err.message || 'Failed to update metadata', 'error');
    } finally {
      setIsSavingEdit(false);
    }
  };

  // Replace File Version
  const handleReplaceSubmit = async () => {
    if (!replaceModalDoc || !replaceFile) return;
    try {
      setIsReplacing(true);
      await apiReplaceFile(replaceModalDoc.id, replaceFile);
      showToast(`'${replaceModalDoc.filename}' is being re-indexed with new content.`, 'success');
      setReplaceModalDoc(null);
      setReplaceFile(null);
      loadStats();
      loadFiles();
    } catch (err: any) {
      showToast(err.message || 'Failed to replace file', 'error');
    } finally {
      setIsReplacing(false);
    }
  };

  // Trigger Re-index
  const handleReindex = async (file: AdminFileItem) => {
    try {
      showToast(`Re-indexing '${file.filename}'...`, 'info');
      await apiReindexFile(file.id);
      showToast(`Re-indexing complete for '${file.filename}'`, 'success');
      loadStats();
      loadFiles();
    } catch (err: any) {
      showToast(err.message || 'Re-index failed', 'error');
    }
  };

  // Delete Single File
  const handleDeleteSingle = async () => {
    if (!deleteConfirmDoc) return;
    try {
      setIsDeletingSingle(true);
      await apiDeleteFile(deleteConfirmDoc.id);
      showToast(`Deleted '${deleteConfirmDoc.filename}'`, 'success');
      setDeleteConfirmDoc(null);
      setSelectedIds((prev) => prev.filter((id) => id !== deleteConfirmDoc.id));
      loadStats();
      loadFiles();
    } catch (err: any) {
      showToast(err.message || 'Delete failed', 'error');
    } finally {
      setIsDeletingSingle(false);
    }
  };

  // Bulk Delete
  const handleBulkDelete = async () => {
    if (selectedIds.length === 0) return;
    try {
      setIsBulkDeleting(true);
      const res = await apiBulkDeleteFiles(selectedIds);
      showToast(`Successfully deleted ${res.deleted_count} files`, 'success');
      setSelectedIds([]);
      setIsBulkDeleteModalOpen(false);
      loadStats();
      loadFiles();
    } catch (err: any) {
      showToast(err.message || 'Bulk delete failed', 'error');
    } finally {
      setIsBulkDeleting(false);
    }
  };

  // Delete ALL Files
  const handleDeleteAll = async () => {
    if (deleteAllConfirmation !== 'DELETE') {
      showToast("Please type 'DELETE' in all caps to confirm.", 'error');
      return;
    }
    try {
      setIsDeletingAll(true);
      await apiDeleteAllFiles('DELETE');
      showToast('All knowledge base files and vectors purged.', 'success');
      setDeleteAllConfirmation('');
      setIsDeleteAllModalOpen(false);
      setSelectedIds([]);
      loadStats();
      loadFiles();
    } catch (err: any) {
      showToast(err.message || 'Purge failed', 'error');
    } finally {
      setIsDeletingAll(false);
    }
  };

  // Audit Logs
  const openAuditModal = async (page: number = 1) => {
    setIsAuditModalOpen(true);
    setAuditPage(page);
    try {
      setAuditLoading(true);
      const res = await apiGetAuditLogs(page, 15);
      setAuditLogs(res.items);
      setAuditTotalPages(Math.max(1, Math.ceil(res.total / 15)));
    } catch (err: any) {
      showToast(err.message || 'Failed to load audit logs', 'error');
    } finally {
      setAuditLoading(false);
    }
  };

  // Access check
  const isAdmin = Boolean(user?.is_admin || user?.role === 'admin' || user?.role === 'superadmin');
  if (!isAdmin) {
    return (
      <div className={`min-h-screen flex flex-col items-center justify-center p-6 text-center ${isDark ? 'bg-slate-950 text-slate-100' : 'bg-slate-50 text-slate-900'}`}>
        <div className="w-16 h-16 rounded-2xl bg-rose-500/10 border border-rose-500/30 flex items-center justify-center text-rose-500 mb-4 animate-pulse">
          <ShieldAlert className="w-8 h-8" />
        </div>
        <h1 className="text-2xl font-bold mb-2">Administrator Access Required</h1>
        <p className="text-sm text-slate-500 max-w-md mb-6">
          This portal allows privileged enterprise document management, vector re-indexing, and destructive knowledge-base operations. Your account does not currently hold admin rights.
        </p>
        <button
          onClick={() => navigate('/app')}
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-orange-600 hover:bg-orange-500 text-white font-medium text-sm transition cursor-pointer shadow-lg shadow-orange-600/30"
        >
          <ArrowLeft className="w-4 h-4" />
          Return to Workspace
        </button>
      </div>
    );
  }

  const formatFileSize = (bytes: number) => {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
  };

  const getFileIcon = (type: string) => {
    const t = type.toUpperCase();
    if (t === 'PDF') return <FileText className="w-4 h-4 text-rose-500" />;
    if (t === 'DOCX') return <FileCode className="w-4 h-4 text-sky-500" />;
    if (t === 'CSV') return <FileSpreadsheet className="w-4 h-4 text-emerald-500" />;
    return <FileText className="w-4 h-4 text-slate-500" />;
  };

  const renderStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return (
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold border ${
            isDark
              ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
              : 'bg-emerald-50 text-emerald-700 border-emerald-200'
          }`}>
            <CheckCircle2 className="w-3 h-3" />
            Completed
          </span>
        );
      case 'processing':
        return (
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold border ${
            isDark
              ? 'bg-amber-500/15 text-amber-400 border-amber-500/30'
              : 'bg-amber-50 text-amber-700 border-amber-200'
          }`}>
            <RefreshCw className="w-3 h-3 animate-spin" />
            Processing
          </span>
        );
      case 'pending':
      case 'uploaded':
        return (
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold border ${
            isDark
              ? 'bg-sky-500/15 text-sky-400 border-sky-500/30'
              : 'bg-sky-50 text-sky-700 border-sky-200'
          }`}>
            <Clock className="w-3 h-3" />
            Pending
          </span>
        );
      case 'failed':
        return (
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold border ${
            isDark
              ? 'bg-rose-500/15 text-rose-400 border-rose-500/30'
              : 'bg-rose-50 text-rose-700 border-rose-200'
          }`}>
            <AlertTriangle className="w-3 h-3" />
            Failed
          </span>
        );
      default:
        return (
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold ${
            isDark ? 'bg-slate-800 text-slate-400' : 'bg-slate-100 text-slate-600'
          }`}>
            {status}
          </span>
        );
    }
  };

  return (
    <div className={`min-h-screen flex flex-col font-sans transition-colors duration-150 ${isDark ? 'bg-slate-950 text-slate-100' : 'bg-slate-50 text-slate-900'}`}>
      {/* Toast Notification */}
      {toast && (
        <div className="fixed top-5 right-5 z-50 animate-in fade-in slide-in-from-top-4">
          <div
            className={`flex items-center gap-2.5 px-4 py-3 rounded-xl border shadow-xl backdrop-blur-md text-xs font-medium ${
              toast.type === 'success'
                ? isDark
                  ? 'bg-emerald-950/90 border-emerald-700/60 text-emerald-200'
                  : 'bg-emerald-50 border-emerald-300 text-emerald-900'
                : toast.type === 'error'
                ? isDark
                  ? 'bg-rose-950/90 border-rose-700/60 text-rose-200'
                  : 'bg-rose-50 border-rose-300 text-rose-900'
                : isDark
                ? 'bg-slate-900/90 border-slate-700/60 text-slate-200'
                : 'bg-white border-slate-300 text-slate-800 shadow-md'
            }`}
          >
            {toast.type === 'success' ? (
              <Check className="w-4 h-4 text-emerald-500" />
            ) : toast.type === 'error' ? (
              <AlertCircle className="w-4 h-4 text-rose-500" />
            ) : (
              <Info className="w-4 h-4 text-sky-500" />
            )}
            <span>{toast.message}</span>
            <button
              onClick={() => setToast(null)}
              className="ml-2 text-slate-400 hover:text-slate-600 transition cursor-pointer"
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {/* Top Header */}
      <header className={`sticky top-0 z-30 backdrop-blur-md px-6 py-3.5 flex items-center justify-between border-b transition-colors ${
        isDark ? 'bg-slate-900/80 border-slate-800 text-slate-100' : 'bg-white/95 border-slate-200/90 text-slate-900 shadow-xs'
      }`}>
        <div className="flex items-center gap-3">
          <Link
            to="/app"
            className={`p-1.5 rounded-lg transition cursor-pointer ${
              isDark ? 'text-slate-400 hover:text-white hover:bg-slate-800' : 'text-slate-500 hover:text-slate-900 hover:bg-slate-100'
            }`}
            title="Return to Chat"
          >
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div className="flex items-center gap-2.5">
            <div className={`w-8 h-8 rounded-lg flex items-center justify-center font-bold border ${
              isDark ? 'bg-orange-600/20 border-orange-500/40 text-orange-400' : 'bg-orange-50 border-orange-200 text-orange-600'
            }`}>
              <Database className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base font-bold tracking-tight">Enterprise Knowledge Base Portal</h1>
                <span className={`px-2 py-0.5 rounded-md text-[10px] font-semibold border ${
                  isDark
                    ? 'bg-orange-500/15 text-orange-400 border-orange-500/30'
                    : 'bg-orange-50 text-orange-700 border-orange-200'
                }`}>
                  Admin Privileged
                </span>
              </div>
              <p className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                Manage raw enterprise documentation, vector chunk embeddings, and RAG retrieval storage.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          {/* Theme Toggle (Light / Dark) */}
          <button
            onClick={() => setIsDark((prev) => !prev)}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition cursor-pointer border ${
              isDark
                ? 'bg-slate-800 hover:bg-slate-750 border-slate-700/80 text-slate-200'
                : 'bg-white hover:bg-slate-50 border-slate-200 text-slate-700 shadow-xs'
            }`}
            title={isDark ? 'Switch to White Background (Light Mode)' : 'Switch to Dark Mode'}
          >
            {isDark ? (
              <>
                <Sun className="w-3.5 h-3.5 text-amber-400" />
                <span>Light Mode</span>
              </>
            ) : (
              <>
                <Moon className="w-3.5 h-3.5 text-slate-600" />
                <span>Dark Mode</span>
              </>
            )}
          </button>

          <button
            onClick={() => openAuditModal(1)}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition cursor-pointer border ${
              isDark
                ? 'bg-slate-800 hover:bg-slate-750 border-slate-700/80 text-slate-200'
                : 'bg-white hover:bg-slate-50 border-slate-200 text-slate-700 shadow-xs'
            }`}
          >
            <History className={`w-3.5 h-3.5 ${isDark ? 'text-slate-400' : 'text-slate-500'}`} />
            <span>Audit Trail</span>
          </button>

          <button
            onClick={() => {
              loadStats();
              loadFiles();
            }}
            disabled={listLoading}
            className={`p-2 rounded-lg transition cursor-pointer border ${
              isDark
                ? 'bg-slate-800 hover:bg-slate-750 border-slate-700/80 text-slate-300 hover:text-white'
                : 'bg-white hover:bg-slate-50 border-slate-200 text-slate-700 shadow-xs'
            }`}
            title="Refresh files"
          >
            <RefreshCw className={`w-4 h-4 ${listLoading ? 'animate-spin text-orange-500' : ''}`} />
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-6 py-6 space-y-6">
        {/* Stat Cards */}
        <section className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3.5">
          <div className={`p-3.5 rounded-xl border flex flex-col justify-between transition ${
            isDark ? 'bg-slate-900/60 border-slate-800/80 shadow-xs' : 'bg-white border-slate-200/90 shadow-xs hover:border-slate-300'
          }`}>
            <span className={`text-[11px] font-medium uppercase tracking-wider ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Total Documents</span>
            <div className={`text-2xl font-bold mt-1 ${isDark ? 'text-white' : 'text-slate-900'}`}>
              {statsLoading ? '...' : stats?.total_documents ?? 0}
            </div>
          </div>

          <div className={`p-3.5 rounded-xl border flex flex-col justify-between transition ${
            isDark ? 'bg-slate-900/60 border-slate-800/80 shadow-xs' : 'bg-white border-slate-200/90 shadow-xs hover:border-slate-300'
          }`}>
            <span className={`text-[11px] font-medium uppercase tracking-wider flex items-center gap-1 ${isDark ? 'text-emerald-400' : 'text-emerald-700'}`}>
              <CheckCircle2 className="w-3 h-3" /> Completed
            </span>
            <div className={`text-2xl font-bold mt-1 ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>
              {statsLoading ? '...' : stats?.completed ?? 0}
            </div>
          </div>

          <div className={`p-3.5 rounded-xl border flex flex-col justify-between transition ${
            isDark ? 'bg-slate-900/60 border-slate-800/80 shadow-xs' : 'bg-white border-slate-200/90 shadow-xs hover:border-slate-300'
          }`}>
            <span className={`text-[11px] font-medium uppercase tracking-wider flex items-center gap-1 ${isDark ? 'text-amber-400' : 'text-amber-700'}`}>
              <RefreshCw className="w-3 h-3 animate-spin" /> Processing
            </span>
            <div className={`text-2xl font-bold mt-1 ${isDark ? 'text-amber-400' : 'text-amber-600'}`}>
              {statsLoading ? '...' : stats?.processing ?? 0}
            </div>
          </div>

          <div className={`p-3.5 rounded-xl border flex flex-col justify-between transition ${
            isDark ? 'bg-slate-900/60 border-slate-800/80 shadow-xs' : 'bg-white border-slate-200/90 shadow-xs hover:border-slate-300'
          }`}>
            <span className={`text-[11px] font-medium uppercase tracking-wider flex items-center gap-1 ${isDark ? 'text-sky-400' : 'text-sky-700'}`}>
              <Clock className="w-3 h-3" /> Pending
            </span>
            <div className={`text-2xl font-bold mt-1 ${isDark ? 'text-sky-400' : 'text-sky-600'}`}>
              {statsLoading ? '...' : stats?.pending ?? 0}
            </div>
          </div>

          <div className={`p-3.5 rounded-xl border flex flex-col justify-between transition ${
            isDark ? 'bg-slate-900/60 border-slate-800/80 shadow-xs' : 'bg-white border-slate-200/90 shadow-xs hover:border-slate-300'
          }`}>
            <span className={`text-[11px] font-medium uppercase tracking-wider flex items-center gap-1 ${isDark ? 'text-rose-400' : 'text-rose-700'}`}>
              <AlertTriangle className="w-3 h-3" /> Failed
            </span>
            <div className={`text-2xl font-bold mt-1 ${isDark ? 'text-rose-400' : 'text-rose-600'}`}>
              {statsLoading ? '...' : stats?.failed ?? 0}
            </div>
          </div>

          <div className={`p-3.5 rounded-xl border flex flex-col justify-between transition ${
            isDark ? 'bg-slate-900/60 border-slate-800/80 shadow-xs' : 'bg-white border-slate-200/90 shadow-xs hover:border-slate-300'
          }`}>
            <span className={`text-[11px] font-medium uppercase tracking-wider flex items-center gap-1 ${isDark ? 'text-purple-400' : 'text-purple-700'}`}>
              <Layers className="w-3 h-3" /> Total Chunks
            </span>
            <div className={`text-2xl font-bold mt-1 ${isDark ? 'text-purple-400' : 'text-purple-600'}`}>
              {statsLoading ? '...' : stats?.total_chunks ?? 0}
            </div>
          </div>

          <div className={`p-3.5 rounded-xl border flex flex-col justify-between transition ${
            isDark ? 'bg-slate-900/60 border-slate-800/80 shadow-xs' : 'bg-white border-slate-200/90 shadow-xs hover:border-slate-300'
          }`}>
            <span className={`text-[11px] font-medium uppercase tracking-wider flex items-center gap-1 ${isDark ? 'text-orange-400' : 'text-orange-700'}`}>
              <AlertCircle className="w-3 h-3" /> Missing Embed
            </span>
            <div className={`text-2xl font-bold mt-1 ${isDark ? 'text-orange-400' : 'text-orange-600'}`}>
              {statsLoading ? '...' : stats?.missing_embeddings ?? 0}
            </div>
          </div>
        </section>

        {/* Drag-and-Drop Bulk Upload Zone */}
        <section className={`border rounded-2xl p-5 space-y-4 transition ${
          isDark ? 'bg-slate-900/70 border-slate-800/90 shadow-lg' : 'bg-white border-slate-200 shadow-xs'
        }`}>
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold flex items-center gap-2">
                <FileUp className="w-4 h-4 text-orange-500" />
                Bulk Document Upload &amp; Background Ingestion
              </h2>
              <p className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                Upload up to 25 documents per batch (PDF, DOCX, TXT, MD, CSV) up to 50 MB each.
              </p>
            </div>
            {uploadFiles.length > 0 && (
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setUploadFiles([])}
                  className={`px-3 py-1.5 rounded-lg text-xs transition cursor-pointer ${
                    isDark ? 'text-slate-400 hover:text-white hover:bg-slate-800' : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                  }`}
                >
                  Clear Queue ({uploadFiles.length})
                </button>
                <button
                  type="button"
                  onClick={handleStartUpload}
                  disabled={isUploading}
                  className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-orange-600 hover:bg-orange-500 text-white text-xs font-semibold shadow-md shadow-orange-600/30 transition cursor-pointer disabled:opacity-50"
                >
                  {isUploading ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      Uploading &amp; Processing...
                    </>
                  ) : (
                    <>
                      <UploadCloud className="w-3.5 h-3.5" />
                      Upload {uploadFiles.length} {uploadFiles.length === 1 ? 'File' : 'Files'}
                    </>
                  )}
                </button>
              </div>
            )}
          </div>

          {/* Dropzone area */}
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-xl p-8 flex flex-col items-center justify-center text-center cursor-pointer transition ${
              isDragging
                ? isDark
                  ? 'border-orange-500 bg-orange-500/10'
                  : 'border-orange-500 bg-orange-50'
                : isDark
                ? 'border-slate-800 hover:border-slate-700 bg-slate-950/40 hover:bg-slate-950/60'
                : 'border-slate-300 hover:border-orange-400 bg-slate-50/60 hover:bg-orange-50/20'
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".pdf,.docx,.txt,.md,.markdown,.csv"
              onChange={handleFileInputChange}
              className="hidden"
            />
            <div className={`w-12 h-12 rounded-2xl flex items-center justify-center mb-3 border ${
              isDark ? 'bg-orange-500/10 border-orange-500/20 text-orange-400' : 'bg-orange-50 border-orange-200 text-orange-600'
            }`}>
              <UploadCloud className="w-6 h-6" />
            </div>
            <p className={`text-sm font-semibold ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>
              Drag and drop files here, or <span className="text-orange-500 underline">browse</span>
            </p>
            <p className={`text-xs mt-1 ${isDark ? 'text-slate-500' : 'text-slate-500'}`}>
              Automated magic-byte check, SHA-256 duplicate detection, semantic chunking &amp; 384-dim dense embedding.
            </p>
          </div>

          {/* Selected queue */}
          {uploadFiles.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2 pt-2">
              {uploadFiles.map((f, i) => (
                <div
                  key={i}
                  className={`flex items-center justify-between p-2.5 rounded-xl border text-xs ${
                    isDark ? 'bg-slate-950 border-slate-800 text-slate-200' : 'bg-slate-50 border-slate-200 text-slate-800'
                  }`}
                >
                  <div className="flex items-center gap-2 overflow-hidden">
                    {getFileIcon(f.name.split('.').pop() || '')}
                    <div className="truncate">
                      <div className="truncate font-medium">{f.name}</div>
                      <div className="text-[10px] text-slate-500">{formatFileSize(f.size)}</div>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      removeUploadFile(i);
                    }}
                    className="p-1 text-slate-400 hover:text-rose-500 rounded-md transition cursor-pointer ml-2"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Upload results preview */}
          {uploadResults && uploadResults.length > 0 && (
            <div className={`p-3 rounded-xl border space-y-2 mt-2 ${
              isDark ? 'bg-slate-950 border-slate-800 text-slate-300' : 'bg-slate-50 border-slate-200 text-slate-800'
            }`}>
              <div className="flex items-center justify-between text-xs font-semibold">
                <span>Recent Upload Feedback</span>
                <button
                  onClick={() => setUploadResults(null)}
                  className="text-slate-400 hover:text-slate-600 transition"
                >
                  Dismiss
                </button>
              </div>
              <div className="max-h-40 overflow-y-auto space-y-1.5 pr-1">
                {uploadResults.map((r, idx) => (
                  <div
                    key={idx}
                    className={`flex items-center justify-between p-2 rounded-lg border text-xs ${
                      isDark ? 'bg-slate-900 border-slate-800/80 text-slate-200' : 'bg-white border-slate-200 text-slate-800'
                    }`}
                  >
                    <div className="truncate mr-2">
                      <span className="font-semibold">{r.filename}</span>
                      <span className="text-[11px] text-slate-500 block">{r.message}</span>
                      {r.error && <span className="text-[10px] text-rose-500 font-medium">{r.error}</span>}
                    </div>
                    {renderStatusBadge(r.status)}
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>

        {/* Files Table Section */}
        <section className={`border rounded-2xl shadow-xs overflow-hidden flex flex-col transition ${
          isDark ? 'bg-slate-900/70 border-slate-800/90 shadow-lg' : 'bg-white border-slate-200'
        }`}>
          {/* Table Header Filter Toolbar */}
          <div className={`p-4 border-b flex flex-col md:flex-row md:items-center justify-between gap-3 ${
            isDark ? 'border-slate-800/80 bg-slate-900/40' : 'border-slate-200 bg-slate-50/70'
          }`}>
            {/* Search Bar */}
            <div className="relative flex-1 max-w-md">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                placeholder="Search files by title or filename..."
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setCurrentPage(1);
                }}
                className={`w-full rounded-xl pl-9 pr-3 py-1.5 text-xs focus:outline-none focus:border-orange-500 focus:ring-1 focus:ring-orange-500 transition border ${
                  isDark
                    ? 'bg-slate-950 border-slate-800 text-slate-200 placeholder-slate-500'
                    : 'bg-white border-slate-300 text-slate-900 placeholder-slate-400'
                }`}
              />
            </div>

            {/* Filter Dropdowns */}
            <div className="flex items-center gap-2 flex-wrap">
              {/* Status Filter */}
              <div className={`flex items-center gap-1.5 border rounded-xl px-2.5 py-1 text-xs ${
                isDark ? 'bg-slate-950 border-slate-800 text-slate-300' : 'bg-white border-slate-300 text-slate-700 shadow-2xs'
              }`}>
                <Filter className="w-3 h-3 text-slate-400" />
                <span className="text-slate-400">Status:</span>
                <select
                  value={statusFilter}
                  onChange={(e) => {
                    setStatusFilter(e.target.value);
                    setCurrentPage(1);
                  }}
                  className={`bg-transparent focus:outline-none text-xs cursor-pointer ${
                    isDark ? 'text-slate-200' : 'text-slate-800'
                  }`}
                >
                  <option value="all">All</option>
                  <option value="completed">Completed</option>
                  <option value="processing">Processing</option>
                  <option value="pending">Pending</option>
                  <option value="failed">Failed</option>
                </select>
              </div>

              {/* Type Filter */}
              <div className={`flex items-center gap-1.5 border rounded-xl px-2.5 py-1 text-xs ${
                isDark ? 'bg-slate-950 border-slate-800 text-slate-300' : 'bg-white border-slate-300 text-slate-700 shadow-2xs'
              }`}>
                <span className="text-slate-400">Type:</span>
                <select
                  value={typeFilter}
                  onChange={(e) => {
                    setTypeFilter(e.target.value);
                    setCurrentPage(1);
                  }}
                  className={`bg-transparent focus:outline-none text-xs cursor-pointer ${
                    isDark ? 'text-slate-200' : 'text-slate-800'
                  }`}
                >
                  <option value="all">All</option>
                  <option value="pdf">PDF</option>
                  <option value="docx">DOCX</option>
                  <option value="txt">TXT</option>
                  <option value="md">Markdown</option>
                  <option value="csv">CSV</option>
                </select>
              </div>

              {/* Sort Dropdown */}
              <div className={`flex items-center gap-1.5 border rounded-xl px-2.5 py-1 text-xs ${
                isDark ? 'bg-slate-950 border-slate-800 text-slate-300' : 'bg-white border-slate-300 text-slate-700 shadow-2xs'
              }`}>
                <ArrowUpDown className="w-3 h-3 text-slate-400" />
                <span className="text-slate-400">Sort:</span>
                <select
                  value={`${sortBy}:${sortOrder}`}
                  onChange={(e) => {
                    const [field, order] = e.target.value.split(':');
                    setSortBy(field);
                    setSortOrder(order);
                    setCurrentPage(1);
                  }}
                  className={`bg-transparent focus:outline-none text-xs cursor-pointer ${
                    isDark ? 'text-slate-200' : 'text-slate-800'
                  }`}
                >
                  <option value="created_at:desc">Newest First</option>
                  <option value="created_at:asc">Oldest First</option>
                  <option value="title:asc">Title A-Z</option>
                  <option value="title:desc">Title Z-A</option>
                  <option value="total_chunks:desc">Most Chunks</option>
                  <option value="total_chunks:asc">Fewest Chunks</option>
                </select>
              </div>

              {/* Bulk Delete Button when selected */}
              {selectedIds.length > 0 && (
                <button
                  type="button"
                  onClick={() => setIsBulkDeleteModalOpen(true)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold shadow-md shadow-rose-600/30 transition cursor-pointer"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  Delete ({selectedIds.length})
                </button>
              )}
            </div>
          </div>

          {/* Table Element */}
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className={`border-b uppercase tracking-wider font-semibold ${
                isDark ? 'bg-slate-950/70 border-slate-800 text-slate-400' : 'bg-slate-50 border-slate-200 text-slate-600'
              }`}>
                <tr>
                  <th className="p-3 w-10 text-center">
                    <input
                      type="checkbox"
                      checked={files.length > 0 && selectedIds.length === files.length}
                      onChange={handleSelectAll}
                      className="rounded-sm border-slate-300 text-orange-600 focus:ring-0 cursor-pointer"
                    />
                  </th>
                  <th className="p-3">Document Title &amp; File</th>
                  <th className="p-3">Category</th>
                  <th className="p-3">Status</th>
                  <th className="p-3">Pages &amp; Size</th>
                  <th className="p-3">Updated</th>
                  <th className="p-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className={isDark ? 'divide-y divide-slate-800/60' : 'divide-y divide-slate-100'}>
                {listLoading && files.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="p-8 text-center text-slate-400">
                      <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-orange-500" />
                      Loading knowledge base files...
                    </td>
                  </tr>
                ) : files.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="p-8 text-center text-slate-400">
                      No documents found matching the filter criteria.
                    </td>
                  </tr>
                ) : (
                  files.map((file) => (
                    <tr
                      key={file.id}
                      className={`transition ${
                        isDark
                          ? selectedIds.includes(file.id) ? 'bg-orange-500/10' : 'hover:bg-slate-800/40'
                          : selectedIds.includes(file.id) ? 'bg-orange-50/70' : 'hover:bg-slate-50/80'
                      }`}
                    >
                      <td className="p-3 text-center">
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(file.id)}
                          onChange={() => toggleSelectOne(file.id)}
                          className="rounded-sm border-slate-300 text-orange-600 focus:ring-0 cursor-pointer"
                        />
                      </td>

                      <td className="p-3">
                        <div className="flex items-center gap-2.5">
                          <div className={`p-1.5 rounded-lg border ${
                            isDark ? 'bg-slate-800/70 border-slate-700/60' : 'bg-slate-100 border-slate-200'
                          }`}>
                            {getFileIcon(file.file_type)}
                          </div>
                          <div className="min-w-0 max-w-xs">
                            <div className={`font-semibold truncate ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>{file.title}</div>
                            <div className={`text-[11px] truncate flex items-center gap-1.5 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                              <span>{file.filename}</span>
                              {file.has_binary && (
                                <span className={`text-[9px] px-1 rounded-sm font-mono border ${
                                  isDark ? 'bg-slate-800 border-slate-700 text-slate-400' : 'bg-slate-100 border-slate-200 text-slate-600'
                                }`}>
                                  BYTEA
                                </span>
                              )}
                            </div>
                            {file.error_message && (
                              <div className="text-[10px] text-rose-500 truncate mt-0.5">
                                Error: {file.error_message}
                              </div>
                            )}
                          </div>
                        </div>
                      </td>

                      <td className="p-3">
                        <span className={`px-2 py-0.5 rounded-md text-[11px] font-medium border ${
                          isDark ? 'bg-slate-800/80 text-slate-300 border-slate-700/60' : 'bg-slate-100 text-slate-700 border-slate-200'
                        }`}>
                          {file.category || 'General'}
                        </span>
                      </td>

                      <td className="p-3">{renderStatusBadge(file.status)}</td>

                      <td className="p-3">
                        <div className={isDark ? 'text-slate-300' : 'text-slate-700'}>
                          {file.total_pages} {file.total_pages === 1 ? 'page' : 'pages'}
                        </div>
                        <div className="text-[11px] text-slate-400">{formatFileSize(file.size_bytes)}</div>
                      </td>

                      <td className="p-3 text-[11px] text-slate-400">
                        {file.updated_at
                          ? new Date(file.updated_at).toLocaleDateString()
                          : file.created_at
                          ? new Date(file.created_at).toLocaleDateString()
                          : '—'}
                      </td>

                      <td className="p-3 text-right">
                        <div className="inline-flex items-center gap-1">
                          {/* Chunks */}
                          <button
                            type="button"
                            onClick={() => openChunksModal(file, 1)}
                            className={`p-1.5 rounded-lg transition cursor-pointer ${
                              isDark ? 'text-slate-400 hover:text-white hover:bg-slate-800' : 'text-slate-500 hover:text-slate-900 hover:bg-slate-100'
                            }`}
                            title="Inspect Chunks & Vectors"
                          >
                            <Layers className="w-3.5 h-3.5" />
                          </button>

                          {/* Edit Metadata */}
                          <button
                            type="button"
                            onClick={() => openEditModal(file)}
                            className={`p-1.5 rounded-lg transition cursor-pointer ${
                              isDark ? 'text-slate-400 hover:text-sky-300 hover:bg-slate-800' : 'text-slate-500 hover:text-sky-600 hover:bg-slate-100'
                            }`}
                            title="Edit Metadata"
                          >
                            <Edit3 className="w-3.5 h-3.5" />
                          </button>

                          {/* Replace File */}
                          <button
                            type="button"
                            onClick={() => {
                              setReplaceModalDoc(file);
                              setReplaceFile(null);
                            }}
                            className={`p-1.5 rounded-lg transition cursor-pointer ${
                              isDark ? 'text-slate-400 hover:text-amber-300 hover:bg-slate-800' : 'text-slate-500 hover:text-amber-600 hover:bg-slate-100'
                            }`}
                            title="Replace File Version"
                          >
                            <FileUp className="w-3.5 h-3.5" />
                          </button>

                          {/* Re-index */}
                          <button
                            type="button"
                            onClick={() => handleReindex(file)}
                            className={`p-1.5 rounded-lg transition cursor-pointer ${
                              isDark ? 'text-slate-400 hover:text-emerald-300 hover:bg-slate-800' : 'text-slate-500 hover:text-emerald-600 hover:bg-slate-100'
                            }`}
                            title="Re-index Document"
                          >
                            <RotateCw className="w-3.5 h-3.5" />
                          </button>

                          {/* Download */}
                          <button
                            type="button"
                            onClick={() => handleDownload(file)}
                            className={`p-1.5 rounded-lg transition cursor-pointer ${
                              isDark ? 'text-slate-400 hover:text-purple-300 hover:bg-slate-800' : 'text-slate-500 hover:text-purple-600 hover:bg-slate-100'
                            }`}
                            title="Download Original File"
                          >
                            <Download className="w-3.5 h-3.5" />
                          </button>

                          {/* Delete */}
                          <button
                            type="button"
                            onClick={() => setDeleteConfirmDoc(file)}
                            className={`p-1.5 rounded-lg transition cursor-pointer ${
                              isDark ? 'text-slate-400 hover:text-rose-400 hover:bg-slate-800' : 'text-slate-500 hover:text-rose-600 hover:bg-slate-100'
                            }`}
                            title="Delete Document"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Table Footer Pagination */}
          <div className={`p-3 border-t flex items-center justify-between text-xs ${
            isDark ? 'border-slate-800/80 bg-slate-950/60 text-slate-400' : 'border-slate-200 bg-slate-50/80 text-slate-600'
          }`}>
            <div>
              Showing <span className={`font-semibold ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>{files.length}</span> of{' '}
              <span className={`font-semibold ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>{totalFiles}</span> documents
            </div>

            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5">
                <span>Page size:</span>
                <select
                  value={pageSize}
                  onChange={(e) => {
                    setPageSize(Number(e.target.value));
                    setCurrentPage(1);
                  }}
                  className={`border rounded-lg px-2 py-0.5 text-xs focus:outline-none cursor-pointer ${
                    isDark ? 'bg-slate-900 border-slate-800 text-slate-200' : 'bg-white border-slate-300 text-slate-800'
                  }`}
                >
                  <option value={10}>10</option>
                  <option value={25}>25</option>
                  <option value={50}>50</option>
                </select>
              </div>

              <div className="flex items-center gap-1">
                <button
                  type="button"
                  disabled={currentPage <= 1}
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  className={`p-1 rounded-md border disabled:opacity-30 disabled:cursor-not-allowed transition cursor-pointer ${
                    isDark ? 'bg-slate-900 border-slate-800 hover:bg-slate-800' : 'bg-white border-slate-300 hover:bg-slate-100'
                  }`}
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <span>
                  Page {currentPage} of {totalPages}
                </span>
                <button
                  type="button"
                  disabled={currentPage >= totalPages}
                  onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                  className={`p-1 rounded-md border disabled:opacity-30 disabled:cursor-not-allowed transition cursor-pointer ${
                    isDark ? 'bg-slate-900 border-slate-800 hover:bg-slate-800' : 'bg-white border-slate-300 hover:bg-slate-100'
                  }`}
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        </section>

        {/* Danger Zone: Purge All Files */}
        <section className={`rounded-2xl p-5 border flex flex-col md:flex-row md:items-center justify-between gap-4 transition ${
          isDark
            ? 'border-rose-900/60 bg-rose-950/20 shadow-lg'
            : 'border-rose-200 bg-rose-50/50 shadow-xs'
        }`}>
          <div className="flex items-start gap-3.5">
            <div className={`p-2.5 rounded-xl border shrink-0 ${
              isDark ? 'bg-rose-500/10 border-rose-500/30 text-rose-400' : 'bg-rose-100 border-rose-200 text-rose-600'
            }`}>
              <AlertTriangle className="w-6 h-6" />
            </div>
            <div>
              <h3 className={`text-sm font-bold ${isDark ? 'text-rose-300' : 'text-rose-900'}`}>Danger Zone: Purge Knowledge Base</h3>
              <p className={`text-xs mt-0.5 max-w-2xl leading-relaxed ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
                Permanently deletes all indexed documents, generated vector chunks, in-memory caches, and PostgreSQL byte binaries. This action is irreversible and requires explicit typed confirmation.
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={() => {
              setDeleteAllConfirmation('');
              setIsDeleteAllModalOpen(true);
            }}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold transition shadow-lg shadow-rose-600/30 shrink-0 cursor-pointer"
          >
            <Trash2 className="w-4 h-4" />
            Purge All Documents
          </button>
        </section>
      </main>

      {/* =========================================================================
          MODALS
         ========================================================================= */}

      {/* 1. Chunks Inspector Modal */}
      {chunksModalDoc && (
        <div className={`fixed inset-0 z-50 flex items-center justify-center p-4 backdrop-blur-xs ${isDark ? 'bg-black/80' : 'bg-slate-900/40'}`}>
          <div className={`w-full max-w-4xl border rounded-2xl shadow-2xl flex flex-col max-h-[85vh] overflow-hidden ${
            isDark ? 'bg-slate-900 border-slate-800 text-slate-100' : 'bg-white border-slate-200 text-slate-900'
          }`}>
            <div className={`p-4 border-b flex items-center justify-between ${
              isDark ? 'bg-slate-950/60 border-slate-800' : 'bg-slate-50 border-slate-200'
            }`}>
              <div className="flex items-center gap-2.5">
                <div className={`p-2 rounded-xl border ${
                  isDark ? 'bg-purple-500/10 text-purple-400 border-purple-500/20' : 'bg-purple-50 text-purple-600 border-purple-200'
                }`}>
                  <Layers className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold">Chunks Inspector: {chunksModalDoc.title}</h3>
                  <p className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                    Total {chunksTotalCount} chunks ({chunksModalDoc.embedded_chunks} embedded) • 384-dim Dense Vector Embeddings
                  </p>
                </div>
              </div>
              <button
                onClick={() => setChunksModalDoc(null)}
                className={`p-1 rounded-lg transition cursor-pointer ${
                  isDark ? 'text-slate-400 hover:text-white' : 'text-slate-400 hover:text-slate-700'
                }`}
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-4 flex-1 overflow-y-auto space-y-3">
              {chunksLoading ? (
                <div className="py-12 text-center text-slate-400">
                  <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-purple-500" />
                  Loading document chunks...
                </div>
              ) : chunks.length === 0 ? (
                <div className="py-12 text-center text-slate-400">No chunks found for this document.</div>
              ) : (
                chunks.map((chunk) => (
                  <div
                    key={chunk.id}
                    className={`p-3.5 rounded-xl border text-xs space-y-2 ${
                      isDark ? 'bg-slate-950 border-slate-800/80 text-slate-200' : 'bg-slate-50 border-slate-200 text-slate-800'
                    }`}
                  >
                    <div className="flex items-center justify-between text-slate-500">
                      <div className="flex items-center gap-2">
                        <span className={`font-semibold ${isDark ? 'text-slate-200' : 'text-slate-900'}`}>Chunk #{chunk.chunk_index + 1}</span>
                        <span className={`px-2 py-0.5 rounded-sm border text-[10px] ${
                          isDark ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-200'
                        }`}>
                          Page {chunk.page_number}
                        </span>
                        {chunk.section && (
                          <span className={`px-2 py-0.5 rounded-sm border text-[10px] ${
                            isDark ? 'bg-slate-900 border-slate-800 text-slate-300' : 'bg-white border-slate-200 text-slate-700'
                          }`}>
                            {chunk.section}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] text-slate-400">{chunk.text_length} chars</span>
                        {chunk.has_embedding ? (
                          <span className={`inline-flex items-center gap-1 text-[10px] border px-1.5 py-0.5 rounded-sm ${
                            isDark ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30' : 'text-emerald-700 bg-emerald-50 border-emerald-200'
                          }`}>
                            <Check className="w-3 h-3" /> 384d Vector
                          </span>
                        ) : (
                          <span className={`text-[10px] border px-1.5 py-0.5 rounded-sm ${
                            isDark ? 'text-orange-400 bg-orange-500/10 border-orange-500/30' : 'text-orange-700 bg-orange-50 border-orange-200'
                          }`}>
                            Missing Vector
                          </span>
                        )}
                      </div>
                    </div>
                    <div className={`p-2.5 rounded-lg font-mono text-[11px] leading-relaxed max-h-48 overflow-y-auto whitespace-pre-wrap border ${
                      isDark ? 'bg-slate-900/80 text-slate-300 border-slate-800' : 'bg-white text-slate-800 border-slate-200'
                    }`}>
                      {chunk.chunk_text}
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Chunks pagination */}
            <div className={`p-3 border-t flex items-center justify-between text-xs ${
              isDark ? 'border-slate-800 bg-slate-950/70 text-slate-400' : 'border-slate-200 bg-slate-50 text-slate-600'
            }`}>
              <span>
                Page {chunksPage} of {chunksTotalPages} ({chunksTotalCount} total chunks)
              </span>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  disabled={chunksPage <= 1 || chunksLoading}
                  onClick={() => openChunksModal(chunksModalDoc, chunksPage - 1)}
                  className={`p-1 rounded-md border disabled:opacity-30 cursor-pointer ${
                    isDark ? 'bg-slate-900 border-slate-800 hover:bg-slate-800' : 'bg-white border-slate-300 hover:bg-slate-100'
                  }`}
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <button
                  type="button"
                  disabled={chunksPage >= chunksTotalPages || chunksLoading}
                  onClick={() => openChunksModal(chunksModalDoc, chunksPage + 1)}
                  className={`p-1 rounded-md border disabled:opacity-30 cursor-pointer ${
                    isDark ? 'bg-slate-900 border-slate-800 hover:bg-slate-800' : 'bg-white border-slate-300 hover:bg-slate-100'
                  }`}
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 2. Edit Metadata Modal */}
      {editModalDoc && (
        <div className={`fixed inset-0 z-50 flex items-center justify-center p-4 backdrop-blur-xs ${isDark ? 'bg-black/80' : 'bg-slate-900/40'}`}>
          <div className={`w-full max-w-lg border rounded-2xl shadow-2xl p-5 space-y-4 ${
            isDark ? 'bg-slate-900 border-slate-800 text-slate-100' : 'bg-white border-slate-200 text-slate-900'
          }`}>
            <div className={`flex items-center justify-between border-b pb-3 ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
              <h3 className="text-sm font-bold flex items-center gap-2">
                <Edit3 className="w-4 h-4 text-sky-500" />
                Edit Document Metadata
              </h3>
              <button
                onClick={() => setEditModalDoc(null)}
                className={`cursor-pointer ${isDark ? 'text-slate-400 hover:text-white' : 'text-slate-400 hover:text-slate-700'}`}
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className={`block font-semibold mb-1 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>Display Title</label>
                <input
                  type="text"
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  className={`w-full rounded-xl px-3 py-2 border focus:outline-none focus:border-orange-500 focus:ring-1 focus:ring-orange-500 ${
                    isDark ? 'bg-slate-950 border-slate-800 text-slate-100' : 'bg-white border-slate-300 text-slate-900'
                  }`}
                />
              </div>

              <div>
                <label className={`block font-semibold mb-1 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>Category / SAP Module</label>
                <input
                  type="text"
                  value={editCategory}
                  onChange={(e) => setEditCategory(e.target.value)}
                  placeholder="e.g. BRIM, SOM, CC, CI, FI-CA, General"
                  className={`w-full rounded-xl px-3 py-2 border focus:outline-none focus:border-orange-500 focus:ring-1 focus:ring-orange-500 ${
                    isDark ? 'bg-slate-950 border-slate-800 text-slate-100' : 'bg-white border-slate-300 text-slate-900'
                  }`}
                />
              </div>

              <div>
                <label className={`block font-semibold mb-1 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>Description</label>
                <textarea
                  rows={3}
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  placeholder="Optional context about this handbook or guide..."
                  className={`w-full rounded-xl px-3 py-2 border focus:outline-none focus:border-orange-500 focus:ring-1 focus:ring-orange-500 ${
                    isDark ? 'bg-slate-950 border-slate-800 text-slate-100' : 'bg-white border-slate-300 text-slate-900'
                  }`}
                />
              </div>
            </div>

            <div className={`flex items-center justify-end gap-2 pt-2 border-t ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
              <button
                type="button"
                onClick={() => setEditModalDoc(null)}
                className={`px-4 py-2 rounded-xl text-xs transition cursor-pointer border ${
                  isDark ? 'text-slate-400 hover:bg-slate-800 hover:text-white border-transparent' : 'text-slate-600 hover:bg-slate-100 border-slate-200'
                }`}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSaveEdit}
                disabled={isSavingEdit || !editTitle.trim()}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-white text-xs font-semibold shadow-md shadow-orange-600/30 transition cursor-pointer disabled:opacity-50"
              >
                {isSavingEdit ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 3. Replace File Modal */}
      {replaceModalDoc && (
        <div className={`fixed inset-0 z-50 flex items-center justify-center p-4 backdrop-blur-xs ${isDark ? 'bg-black/80' : 'bg-slate-900/40'}`}>
          <div className={`w-full max-w-lg border rounded-2xl shadow-2xl p-5 space-y-4 ${
            isDark ? 'bg-slate-900 border-slate-800 text-slate-100' : 'bg-white border-slate-200 text-slate-900'
          }`}>
            <div className={`flex items-center justify-between border-b pb-3 ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
              <h3 className="text-sm font-bold flex items-center gap-2">
                <FileUp className="w-4 h-4 text-amber-500" />
                Replace File Version
              </h3>
              <button
                onClick={() => setReplaceModalDoc(null)}
                className={`cursor-pointer ${isDark ? 'text-slate-400 hover:text-white' : 'text-slate-400 hover:text-slate-700'}`}
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
              You are replacing <strong className={isDark ? 'text-slate-200' : 'text-slate-900'}>{replaceModalDoc.filename}</strong>. The old chunks will be atomically swapped with the new extraction and embedding vectors in one transaction.
            </p>

            <div className="space-y-3">
              <input
                type="file"
                accept=".pdf,.docx,.txt,.md,.markdown,.csv"
                onChange={(e) => {
                  if (e.target.files && e.target.files[0]) {
                    setReplaceFile(e.target.files[0]);
                  }
                }}
                className={`w-full text-xs file:mr-3 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-xs file:font-semibold cursor-pointer ${
                  isDark
                    ? 'text-slate-400 file:bg-slate-800 file:text-slate-200 hover:file:bg-slate-700'
                    : 'text-slate-600 file:bg-slate-100 file:text-slate-800 hover:file:bg-slate-200'
                }`}
              />
              {replaceFile && (
                <div className={`text-xs p-2.5 rounded-xl border ${
                  isDark ? 'bg-slate-950 border-slate-800 text-slate-300' : 'bg-slate-50 border-slate-200 text-slate-800'
                }`}>
                  Selected: <span className="font-semibold text-orange-500">{replaceFile.name}</span>{' '}
                  ({formatFileSize(replaceFile.size)})
                </div>
              )}
            </div>

            <div className={`flex items-center justify-end gap-2 pt-2 border-t ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
              <button
                type="button"
                onClick={() => setReplaceModalDoc(null)}
                className={`px-4 py-2 rounded-xl text-xs transition cursor-pointer border ${
                  isDark ? 'text-slate-400 hover:bg-slate-800 hover:text-white border-transparent' : 'text-slate-600 hover:bg-slate-100 border-slate-200'
                }`}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleReplaceSubmit}
                disabled={isReplacing || !replaceFile}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-amber-600 hover:bg-amber-500 text-white text-xs font-semibold shadow-md shadow-amber-600/30 transition cursor-pointer disabled:opacity-50"
              >
                {isReplacing ? 'Replacing & Indexing...' : 'Confirm & Replace'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 4. Delete Single Document Modal */}
      {deleteConfirmDoc && (
        <div className={`fixed inset-0 z-50 flex items-center justify-center p-4 backdrop-blur-xs ${isDark ? 'bg-black/80' : 'bg-slate-900/40'}`}>
          <div className={`w-full max-w-md border rounded-2xl shadow-2xl p-5 space-y-4 ${
            isDark ? 'bg-slate-900 border-slate-800 text-slate-100' : 'bg-white border-slate-200 text-slate-900'
          }`}>
            <div className="flex items-center gap-3 text-rose-500">
              <div className={`p-2 rounded-xl border ${
                isDark ? 'bg-rose-500/10 border-rose-500/20' : 'bg-rose-50 border-rose-200'
              }`}>
                <Trash2 className="w-5 h-5" />
              </div>
              <h3 className="text-sm font-bold">Delete Document</h3>
            </div>

            <p className={`text-xs ${isDark ? 'text-slate-300' : 'text-slate-600'}`}>
              Are you sure you want to permanently delete{' '}
              <strong className={isDark ? 'text-white' : 'text-slate-900'}>'{deleteConfirmDoc.filename}'</strong> and all{' '}
              <strong className="text-orange-500 font-bold">{deleteConfirmDoc.total_chunks} chunks</strong> from the knowledge base?
            </p>

            <div className={`flex items-center justify-end gap-2 pt-2 border-t ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
              <button
                type="button"
                onClick={() => setDeleteConfirmDoc(null)}
                className={`px-4 py-2 rounded-xl text-xs transition cursor-pointer border ${
                  isDark ? 'text-slate-400 hover:bg-slate-800 hover:text-white border-transparent' : 'text-slate-600 hover:bg-slate-100 border-slate-200'
                }`}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDeleteSingle}
                disabled={isDeletingSingle}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold shadow-md shadow-rose-600/30 transition cursor-pointer disabled:opacity-50"
              >
                {isDeletingSingle ? 'Deleting...' : 'Delete Permanently'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 5. Bulk Delete Modal */}
      {isBulkDeleteModalOpen && (
        <div className={`fixed inset-0 z-50 flex items-center justify-center p-4 backdrop-blur-xs ${isDark ? 'bg-black/80' : 'bg-slate-900/40'}`}>
          <div className={`w-full max-w-md border rounded-2xl shadow-2xl p-5 space-y-4 ${
            isDark ? 'bg-slate-900 border-slate-800 text-slate-100' : 'bg-white border-slate-200 text-slate-900'
          }`}>
            <div className="flex items-center gap-3 text-rose-500">
              <div className={`p-2 rounded-xl border ${
                isDark ? 'bg-rose-500/10 border-rose-500/20' : 'bg-rose-50 border-rose-200'
              }`}>
                <Trash2 className="w-5 h-5" />
              </div>
              <h3 className="text-sm font-bold">Delete Selected Documents</h3>
            </div>

            <p className={`text-xs ${isDark ? 'text-slate-300' : 'text-slate-600'}`}>
              Are you sure you want to delete{' '}
              <strong className={isDark ? 'text-white' : 'text-slate-900'}>{selectedIds.length} documents</strong> and their chunks from the system?
            </p>

            <div className={`flex items-center justify-end gap-2 pt-2 border-t ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
              <button
                type="button"
                onClick={() => setIsBulkDeleteModalOpen(false)}
                className={`px-4 py-2 rounded-xl text-xs transition cursor-pointer border ${
                  isDark ? 'text-slate-400 hover:bg-slate-800 hover:text-white border-transparent' : 'text-slate-600 hover:bg-slate-100 border-slate-200'
                }`}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleBulkDelete}
                disabled={isBulkDeleting}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold shadow-md shadow-rose-600/30 transition cursor-pointer disabled:opacity-50"
              >
                {isBulkDeleting ? 'Deleting...' : `Delete ${selectedIds.length} Files`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 6. Delete ALL Files (Strict Typing Check Modal) */}
      {isDeleteAllModalOpen && (
        <div className={`fixed inset-0 z-50 flex items-center justify-center p-4 backdrop-blur-xs ${isDark ? 'bg-black/80' : 'bg-slate-900/40'}`}>
          <div className={`w-full max-w-lg border rounded-2xl shadow-2xl p-5 space-y-4 ${
            isDark ? 'bg-slate-900 border-rose-800/80 text-slate-100' : 'bg-white border-rose-300 text-slate-900'
          }`}>
            <div className="flex items-center gap-3 text-rose-500">
              <div className={`p-2.5 rounded-xl border ${
                isDark ? 'bg-rose-500/20 border-rose-500/40' : 'bg-rose-100 border-rose-300'
              }`}>
                <AlertTriangle className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-base font-bold">Purge Entire Knowledge Base</h3>
                <p className="text-xs text-rose-500 font-semibold">Irreversible Action</p>
              </div>
            </div>

            <p className={`text-xs leading-relaxed ${isDark ? 'text-slate-300' : 'text-slate-600'}`}>
              This will completely wipe <strong className={isDark ? 'text-white' : 'text-slate-900'}>all {stats?.total_documents ?? 0} documents</strong>,{' '}
              <strong className={isDark ? 'text-white' : 'text-slate-900'}>all {stats?.total_chunks ?? 0} vector chunks</strong>, and PostgreSQL binary storage.
            </p>

            <div className="space-y-2 pt-2">
              <label className={`block text-xs font-semibold ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
                To confirm, type <span className="text-rose-500 font-mono font-bold">DELETE</span> below:
              </label>
              <input
                type="text"
                value={deleteAllConfirmation}
                onChange={(e) => setDeleteAllConfirmation(e.target.value)}
                placeholder="DELETE"
                className={`w-full rounded-xl px-3 py-2 text-xs font-mono border focus:outline-none focus:ring-1 ${
                  isDark
                    ? 'bg-slate-950 border-rose-800/60 text-rose-300 focus:border-rose-500 focus:ring-rose-500'
                    : 'bg-rose-50/50 border-rose-300 text-rose-700 focus:border-rose-600 focus:ring-rose-600'
                }`}
              />
            </div>

            <div className={`flex items-center justify-end gap-2 pt-2 border-t ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
              <button
                type="button"
                onClick={() => setIsDeleteAllModalOpen(false)}
                className={`px-4 py-2 rounded-xl text-xs transition cursor-pointer border ${
                  isDark ? 'text-slate-400 hover:bg-slate-800 hover:text-white border-transparent' : 'text-slate-600 hover:bg-slate-100 border-slate-200'
                }`}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDeleteAll}
                disabled={isDeletingAll || deleteAllConfirmation !== 'DELETE'}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold transition shadow-lg shadow-rose-600/30 cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
              >
                {isDeletingAll ? 'Purging Knowledge Base...' : 'Purge All Files'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 7. Enterprise Audit Log Modal */}
      {isAuditModalOpen && (
        <div className={`fixed inset-0 z-50 flex items-center justify-center p-4 backdrop-blur-xs ${isDark ? 'bg-black/80' : 'bg-slate-900/40'}`}>
          <div className={`w-full max-w-4xl border rounded-2xl shadow-2xl flex flex-col max-h-[85vh] overflow-hidden ${
            isDark ? 'bg-slate-900 border-slate-800 text-slate-100' : 'bg-white border-slate-200 text-slate-900'
          }`}>
            <div className={`p-4 border-b flex items-center justify-between ${
              isDark ? 'bg-slate-950/60 border-slate-800' : 'bg-slate-50 border-slate-200'
            }`}>
              <div className="flex items-center gap-2.5">
                <div className={`p-2 rounded-xl border ${
                  isDark ? 'bg-sky-500/10 text-sky-400 border-sky-500/20' : 'bg-sky-50 text-sky-600 border-sky-200'
                }`}>
                  <History className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold">Admin Audit Trail</h3>
                  <p className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                    Chronological activity log of upload, replace, metadata edit, and deletion actions.
                  </p>
                </div>
              </div>
              <button
                onClick={() => setIsAuditModalOpen(false)}
                className={`p-1 rounded-lg transition cursor-pointer ${
                  isDark ? 'text-slate-400 hover:text-white' : 'text-slate-400 hover:text-slate-700'
                }`}
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-4 flex-1 overflow-y-auto space-y-2">
              {auditLoading ? (
                <div className="py-12 text-center text-slate-400">
                  <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-sky-500" />
                  Loading audit logs...
                </div>
              ) : auditLogs.length === 0 ? (
                <div className="py-12 text-center text-slate-400">No audit records found yet.</div>
              ) : (
                auditLogs.map((log) => (
                  <div
                    key={log.id}
                    className={`p-3 rounded-xl border text-xs flex flex-col md:flex-row md:items-center justify-between gap-2 ${
                      isDark ? 'bg-slate-950 border-slate-800/80 text-slate-200' : 'bg-slate-50 border-slate-200 text-slate-800'
                    }`}
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className={`px-2 py-0.5 rounded-sm font-mono text-[10px] font-bold border ${
                          isDark ? 'bg-slate-800 border-slate-700 text-orange-400' : 'bg-orange-50 border-orange-200 text-orange-600'
                        }`}>
                          {log.action}
                        </span>
                        <span className="font-semibold">{log.target_name || log.target_id || 'System'}</span>
                        <span className="text-slate-400 text-[11px]">by {log.admin_email}</span>
                      </div>
                      {log.details && (
                        <div className="text-[10px] text-slate-500 font-mono truncate max-w-xl">
                          {log.details}
                        </div>
                      )}
                    </div>
                    <div className="text-[11px] text-slate-400 text-right shrink-0">
                      <div>{log.created_at ? new Date(log.created_at).toLocaleString() : '—'}</div>
                      {log.ip_address && <div className="text-[10px] text-slate-400">IP: {log.ip_address}</div>}
                    </div>
                  </div>
                ))
              )}
            </div>

            <div className={`p-3 border-t flex items-center justify-between text-xs ${
              isDark ? 'border-slate-800 bg-slate-950/70 text-slate-400' : 'border-slate-200 bg-slate-50 text-slate-600'
            }`}>
              <span>Page {auditPage} of {auditTotalPages}</span>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  disabled={auditPage <= 1 || auditLoading}
                  onClick={() => openAuditModal(auditPage - 1)}
                  className={`p-1 rounded-md border disabled:opacity-30 cursor-pointer ${
                    isDark ? 'bg-slate-900 border-slate-800 hover:bg-slate-800' : 'bg-white border-slate-300 hover:bg-slate-100'
                  }`}
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <button
                  type="button"
                  disabled={auditPage >= auditTotalPages || auditLoading}
                  onClick={() => openAuditModal(auditPage + 1)}
                  className={`p-1 rounded-md border disabled:opacity-30 cursor-pointer ${
                    isDark ? 'bg-slate-900 border-slate-800 hover:bg-slate-800' : 'bg-white border-slate-300 hover:bg-slate-100'
                  }`}
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
