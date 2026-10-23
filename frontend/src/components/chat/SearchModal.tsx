import React, { useState, useEffect, useRef, useMemo } from 'react';
import { Search, MessageSquare, Folder, ArrowRight, CornerDownLeft, X, Sparkles } from 'lucide-react';
import type { Chat, Project } from '../../types';

interface SearchModalProps {
  isOpen: boolean;
  onClose: () => void;
  chats: Chat[];
  projects?: Project[];
  onSelectChat: (chatId: string) => void;
  onSelectProject?: (projectId: string) => void;
}

export const SearchModal: React.FC<SearchModalProps> = ({
  isOpen,
  onClose,
  chats,
  projects = [],
  onSelectChat,
  onSelectProject,
}) => {
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const resultsContainerRef = useRef<HTMLDivElement>(null);

  // Reset query and auto-focus when modal opens
  useEffect(() => {
    if (isOpen) {
      setQuery('');
      setSelectedIndex(0);
      setTimeout(() => {
        inputRef.current?.focus();
      }, 50);
    }
  }, [isOpen]);

  const normalizedQuery = query.trim().toLowerCase();

  // Filter chats & projects
  const filteredChats = useMemo(() => {
    if (!normalizedQuery) {
      // Show latest 8 chats when query is empty
      return chats.slice(0, 8);
    }
    return chats.filter(c => c.title.toLowerCase().includes(normalizedQuery));
  }, [chats, normalizedQuery]);

  const filteredProjects = useMemo(() => {
    if (!normalizedQuery) return [];
    return projects.filter(
      p => p.name.toLowerCase().includes(normalizedQuery) || (p.description && p.description.toLowerCase().includes(normalizedQuery))
    );
  }, [projects, normalizedQuery]);

  interface SearchItem {
    type: 'chat' | 'project';
    id: string;
    title: string;
    subtitle?: string;
    date?: string;
  }

  const items: SearchItem[] = useMemo(() => {
    const list: SearchItem[] = [];
    filteredChats.forEach(c => {
      list.push({
        type: 'chat',
        id: c.id,
        title: c.title,
        date: c.updated_at || c.created_at,
      });
    });
    filteredProjects.forEach(p => {
      list.push({
        type: 'project',
        id: p.id,
        title: p.name,
        subtitle: p.description,
      });
    });
    return list;
  }, [filteredChats, filteredProjects]);

  // Keep selected index within bounds
  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  // Handle keyboard navigation (Arrow Up, Down, Enter, Esc)
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (items.length > 0) {
          setSelectedIndex(prev => (prev + 1) % items.length);
        }
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (items.length > 0) {
          setSelectedIndex(prev => (prev - 1 + items.length) % items.length);
        }
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (items.length > 0 && items[selectedIndex]) {
          const item = items[selectedIndex];
          if (item.type === 'chat') {
            onSelectChat(item.id);
          } else if (onSelectProject) {
            onSelectProject(item.id);
          }
          onClose();
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, items, selectedIndex, onClose, onSelectChat, onSelectProject]);

  // Scroll active item into view
  useEffect(() => {
    const container = resultsContainerRef.current;
    if (!container) return;
    const activeEl = container.querySelector(`[data-index="${selectedIndex}"]`) as HTMLElement;
    if (activeEl) {
      activeEl.scrollIntoView({ block: 'nearest' });
    }
  }, [selectedIndex]);

  if (!isOpen) return null;

  const formatDate = (iso?: string) => {
    if (!iso) return '';
    const date = new Date(iso);
    const now = new Date();
    const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));
    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-14 sm:pt-20 px-3 bg-black/50 backdrop-blur-xs transition-opacity animate-in fade-in duration-150"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Search conversations"
    >
      <div
        className="w-full max-w-3xl bg-white dark:bg-[#18181b] rounded-2xl shadow-2xl border border-black/[0.08] dark:border-white/[0.1] overflow-hidden flex flex-col max-h-[75vh] animate-in zoom-in-95 duration-150"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Top search input row */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-black/[0.06] dark:border-white/[0.08]">
          <Search className="w-5 h-5 text-slate-400 dark:text-slate-500 shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search chats and projects..."
            className="flex-1 bg-transparent border-0 outline-none text-base text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500"
            aria-label="Search input"
          />
          <div className="flex items-center gap-1.5">
            {query && (
              <button
                type="button"
                onClick={() => {
                  setQuery('');
                  inputRef.current?.focus();
                }}
                className="p-1.5 rounded-md text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-black/5 dark:hover:bg-white/10 transition"
                aria-label="Clear search"
                title="Clear"
              >
                <X className="w-4 h-4" />
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200 bg-slate-100 hover:bg-slate-200 dark:bg-white/5 dark:hover:bg-white/10 rounded-lg transition"
              aria-label="Close"
              title="Close"
            >
              <X className="w-3.5 h-3.5" />
              <span>to close</span>
            </button>
          </div>
        </div>

        {/* Results / History List */}
        <div
          ref={resultsContainerRef}
          className="flex-1 overflow-y-auto px-2 py-2 space-y-0.5 divide-y-0"
        >
          {items.length === 0 ? (
            <div className="py-12 px-4 text-center">
              <p className="text-sm text-slate-500 dark:text-slate-400">
                {normalizedQuery ? `No chats found matching "${query}"` : 'No recent conversations yet.'}
              </p>
              {normalizedQuery && (
                <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                  Try searching with different keywords like SOM, CC, BIT, or invoices.
                </p>
              )}
            </div>
          ) : (
            <>
              <div className="px-3 pt-1.5 pb-1 text-[11px] font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider">
                {normalizedQuery ? `Matching Results (${items.length})` : 'Recent Conversations'}
              </div>
              {items.map((item, idx) => {
                const isSelected = idx === selectedIndex;
                const isChat = item.type === 'chat';

                return (
                  <div
                    key={`${item.type}-${item.id}`}
                    data-index={idx}
                    onClick={() => {
                      if (isChat) {
                        onSelectChat(item.id);
                      } else if (onSelectProject) {
                        onSelectProject(item.id);
                      }
                      onClose();
                    }}
                    onMouseEnter={() => setSelectedIndex(idx)}
                    className={`group flex items-center justify-between gap-3 px-3 py-2.5 rounded-xl cursor-pointer transition duration-150 ${
                      isSelected
                        ? 'bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-white'
                        : 'text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800/50'
                    }`}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div
                        className={`p-2 rounded-lg shrink-0 transition ${
                          isSelected
                            ? 'bg-[#ea580c] text-white shadow-xs'
                            : 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 group-hover:text-slate-700 dark:group-hover:text-slate-200'
                        }`}
                      >
                        {isChat ? <MessageSquare className="w-4 h-4" /> : <Folder className="w-4 h-4" />}
                      </div>
                      <div className="min-w-0 flex flex-col">
                        <span className="text-sm font-medium truncate">
                          {item.title}
                        </span>
                        {item.subtitle && (
                          <span className="text-[11px] text-slate-400 truncate">
                            {item.subtitle}
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      {item.date && (
                        <span className="text-xs text-slate-400 dark:text-slate-500">
                          {formatDate(item.date)}
                        </span>
                      )}
                      {isSelected ? (
                        <CornerDownLeft className="w-3.5 h-3.5 text-slate-400 dark:text-slate-300" />
                      ) : (
                        <ArrowRight className="w-3.5 h-3.5 text-transparent group-hover:text-slate-400 transition" />
                      )}
                    </div>
                  </div>
                );
              })}
            </>
          )}
        </div>

        {/* Footer with keyboard hints */}
        <div className="px-4 py-2.5 bg-slate-50 dark:bg-[#121215] border-t border-black/[0.05] dark:border-white/[0.06] flex items-center justify-between text-[11px] text-slate-400 dark:text-slate-500">
          <div className="flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-[#ea580c]" />
            <span>Search SAP conversations &amp; workspaces</span>
          </div>
          <div className="hidden sm:flex items-center gap-3">
            <span className="flex items-center gap-1">
              <kbd className="font-mono px-1 py-0.5 rounded bg-slate-200 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-300 dark:border-slate-700">↑</kbd>
              <kbd className="font-mono px-1 py-0.5 rounded bg-slate-200 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-300 dark:border-slate-700">↓</kbd>
              <span>Navigate</span>
            </span>
            <span className="flex items-center gap-1">
              <kbd className="font-mono px-1 py-0.5 rounded bg-slate-200 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-300 dark:border-slate-700">↵</kbd>
              <span>Open</span>
            </span>
            <span className="flex items-center gap-1">
              <kbd className="font-mono px-1 py-0.5 rounded bg-slate-200 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-300 dark:border-slate-700">✕</kbd>
              <span>to close</span>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
