import React, { useEffect, useRef, useState } from 'react';
import { Check, MoreHorizontal, Pin, PinOff, Trash2, X, Pencil } from 'lucide-react';
import { NavLink } from 'react-router-dom';
import type { Chat } from '../../types';

interface Props {
  chat: Chat;
  isPinned: boolean;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
  onTogglePin: (id: string, pinned: boolean) => void;
}

export const SidebarChatItem: React.FC<Props> = ({ chat, isPinned, onRename, onDelete, onTogglePin }) => {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(chat.title);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const close = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setMenuOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [menuOpen]);

  const save = (event: React.FormEvent) => {
    event.preventDefault();
    if (title.trim()) onRename(chat.id, title.trim());
    setEditing(false);
  };

  if (editing) return (
    <form className="sidebar-item-row" onSubmit={save}>
      <input autoFocus value={title} onChange={event => setTitle(event.target.value)} aria-label="Chat title" />
      <button type="submit" className="sidebar-pin" title="Save name"><Check size={14} /></button>
      <button type="button" className="sidebar-pin" title="Cancel rename" onClick={() => { setTitle(chat.title); setEditing(false); }}><X size={14} /></button>
    </form>
  );

  return (
    <div className="sidebar-item-row" ref={menuRef}>
      <NavLink className={({ isActive }) => `conversation-link ${isActive ? 'active' : ''}`} to={`/app/chat/${chat.id}`} title={chat.title}>
        {chat.title}
      </NavLink>
      <button className={`sidebar-pin ${isPinned ? 'is-pinned' : ''}`} type="button" aria-label={`${isPinned ? 'Unpin' : 'Pin'} chat ${chat.title}`} title={isPinned ? 'Unpin chat' : 'Pin chat'} onClick={() => onTogglePin(chat.id, isPinned)}>
        {isPinned ? <PinOff size={13} /> : <Pin size={13} />}
      </button>
      <button className={`sidebar-pin chat-menu-trigger ${menuOpen ? 'is-pinned' : ''}`} type="button" aria-label={`Chat options for ${chat.title}`} title="Chat options" onClick={() => setMenuOpen(value => !value)}>
        <MoreHorizontal size={15} />
      </button>
      {menuOpen && <div className="sidebar-chat-menu">
        <button type="button" onClick={() => { setMenuOpen(false); setTitle(chat.title); setEditing(true); }}><Pencil size={14} /> Rename</button>
        <button type="button" onClick={() => { setMenuOpen(false); onTogglePin(chat.id, isPinned); }}>{isPinned ? <PinOff size={14} /> : <Pin size={14} />}{isPinned ? 'Unpin' : 'Pin'}</button>
        <button className="danger" type="button" onClick={() => { setMenuOpen(false); onDelete(chat.id); }}><Trash2 size={14} /> Delete</button>
      </div>}
    </div>
  );
};
