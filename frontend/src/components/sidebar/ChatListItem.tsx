import React, { useState, useRef, useEffect } from 'react';
import {
  MessageSquare,
  MoreVertical,
  Edit2,
  Trash2,
  Check,
  X,
  Share2,
  Pin,
  PinOff,
  Archive,
  Download
} from 'lucide-react';
import type { Chat } from '../../types';
import { apiExportChat } from '../../services/api';

interface ChatListItemProps {
  chat: Chat;
  isActive: boolean;
  isPinned?: boolean;
  isArchived?: boolean;
  onSelect: (id: string) => void;
  onRename: (id: string, newTitle: string) => void;
  onDelete: (id: string) => void;
  onShare: (chat: Chat) => void;
  onTogglePin: (id: string) => void;
  onToggleArchive: (id: string) => void;
}

export const ChatListItem: React.FC<ChatListItemProps> = ({
  chat,
  isActive,
  isPinned = false,
  isArchived = false,
  onSelect,
  onRename,
  onDelete,
  onShare,
  onTogglePin,
  onToggleArchive,
}) => {
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(chat.title);
  const [showMenu, setShowMenu] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setShowMenu(false);
      }
    };
    if (showMenu) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showMenu]);

  const handleSaveRename = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (editTitle.trim() && editTitle.trim() !== chat.title) {
      onRename(chat.id, editTitle.trim());
    }
    setIsEditing(false);
    setShowMenu(false);
  };

  const handleCancelRename = () => {
    setEditTitle(chat.title);
    setIsEditing(false);
    setShowMenu(false);
  };

  if (isEditing) {
    return (
      <form onSubmit={handleSaveRename} className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-slate-800 border border-sap-500/50">
        <input
          type="text"
          value={editTitle}
          onChange={(e) => setEditTitle(e.target.value)}
          autoFocus
          className="flex-1 bg-transparent text-xs text-white focus:outline-none"
        />
        <button type="submit" className="p-1 hover:text-emerald-400 text-slate-300">
          <Check className="w-3.5 h-3.5" />
        </button>
        <button type="button" onClick={handleCancelRename} className="p-1 hover:text-rose-400 text-slate-400">
          <X className="w-3.5 h-3.5" />
        </button>
      </form>
    );
  }

  return (
    <div
      onClick={() => onSelect(chat.id)}
      className={`group relative flex items-center justify-between px-3 py-2 rounded-xl text-xs font-medium cursor-pointer transition ${
        isActive
          ? 'bg-slate-800 text-white border border-slate-700/80 shadow-sm'
          : 'text-slate-400 hover:text-slate-200 hover:bg-slate-850'
      }`}
    >
      <div className="flex items-center gap-2 min-w-0 flex-1">
        <MessageSquare className={`w-3.5 h-3.5 shrink-0 ${isActive ? 'text-sap-400' : 'text-slate-500'}`} />
        <span className="truncate flex-1">{chat.title}</span>
        {isPinned && (
          <span title="Pinned chat" className="shrink-0 flex items-center">
            <Pin className="w-3 h-3 text-sap-400 transform -rotate-45" />
          </span>
        )}
      </div>

      <div className="relative shrink-0 flex items-center ml-1">
        <button
          onClick={(e) => {
            e.stopPropagation();
            setShowMenu(!showMenu);
          }}
          className={`p-1 rounded opacity-0 group-hover:opacity-100 transition hover:bg-slate-700 ${showMenu ? 'opacity-100 bg-slate-700' : ''}`}
          title="Chat options"
        >
          <MoreVertical className="w-3.5 h-3.5 text-slate-400" />
        </button>

        {showMenu && (
          <div
            ref={menuRef}
            onClick={(e) => e.stopPropagation()}
            className="absolute right-0 top-full mt-1 w-36 bg-slate-900 border border-slate-700/90 rounded-xl shadow-2xl z-30 py-1 overflow-hidden backdrop-blur-md"
          >
            {/* Share */}
            <button
              onClick={() => {
                setShowMenu(false);
                onShare(chat);
              }}
              className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-slate-200 hover:bg-slate-800 hover:text-white transition"
            >
              <Share2 className="w-3.5 h-3.5 text-slate-400" />
              <span>Share</span>
            </button>

            {/* Rename */}
            <button
              onClick={() => {
                setShowMenu(false);
                setIsEditing(true);
              }}
              className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-slate-200 hover:bg-slate-800 hover:text-white transition"
            >
              <Edit2 className="w-3.5 h-3.5 text-slate-400" />
              <span>Rename</span>
            </button>

            {/* Pin chat / Unpin chat */}
            <button
              onClick={() => {
                setShowMenu(false);
                onTogglePin(chat.id);
              }}
              className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-slate-200 hover:bg-slate-800 hover:text-white transition"
            >
              {isPinned ? (
                <>
                  <PinOff className="w-3.5 h-3.5 text-sap-400" />
                  <span>Unpin chat</span>
                </>
              ) : (
                <>
                  <Pin className="w-3.5 h-3.5 text-slate-400" />
                  <span>Pin chat</span>
                </>
              )}
            </button>

            {/* Archive / Unarchive */}
            <button
              onClick={() => {
                setShowMenu(false);
                onToggleArchive(chat.id);
              }}
              className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-slate-200 hover:bg-slate-800 hover:text-white transition"
            >
              <Archive className="w-3.5 h-3.5 text-slate-400" />
              <span>{isArchived ? 'Unarchive' : 'Archive'}</span>
            </button>

            {/* Export */}
            <button
              onClick={async () => {
                setShowMenu(false);
                try {
                  const { blob, filename } = await apiExportChat(chat.id, 'markdown');
                  const url = window.URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = filename;
                  document.body.appendChild(a);
                  a.click();
                  window.URL.revokeObjectURL(url);
                  document.body.removeChild(a);
                } catch (err) {
                  console.error('Export error:', err);
                }
              }}
              className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-slate-200 hover:bg-slate-800 hover:text-white transition"
            >
              <Download className="w-3.5 h-3.5 text-slate-400" />
              <span>Export (.md)</span>
            </button>

            {/* Delete */}
            <button
              onClick={() => {
                setShowMenu(false);
                if (window.confirm('Delete this SAP chat history?')) {
                  onDelete(chat.id);
                }
              }}
              className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-rose-400 hover:bg-rose-950/40 hover:text-rose-300 transition"
            >
              <Trash2 className="w-3.5 h-3.5 text-rose-400" />
              <span>Delete</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
