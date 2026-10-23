import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
  FolderPlus,
  MessageSquarePlus,
  Pin,
  PinOff,
  Search,
  ChevronDown,
  CircleHelp,
  PanelLeft,
  SquarePen,
  Share,
} from 'lucide-react';
import { BrandLogo } from '../components/navbar/BrandLogo';
import { ProjectModal } from '../components/projects/ProjectModal';
import { AssistantGuideModal } from '../components/ui/AssistantGuideModal';
import { AccountMenu } from '../components/sidebar/AccountMenu';
import { ScrollToSearchButton } from '../components/sidebar/ScrollToSearchButton';
import { SearchModal } from '../components/chat/SearchModal';
import { useAuth } from '../context/AuthContext';
import { apiGetChats, apiCreateChat, apiDeleteChat, apiUpdateChat, apiSetChatPinned, apiGetProjects, apiCreateProject, apiUpdateProject } from '../services/api';
import { SidebarChatItem } from '../components/sidebar/SidebarChatItem';
import type { Chat, Project } from '../types';

function dateGroup(chat: Chat): string {
  const date = new Date(chat.updated_at || chat.created_at);
  const today = new Date();
  if (date.toDateString() === today.toDateString()) return 'Today';
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (date.toDateString() === yesterday.toDateString()) return 'Yesterday';
  const previousWeek = new Date(today);
  previousWeek.setDate(today.getDate() - 7);
  if (date >= previousWeek) return 'Previous 7 days';
  const previousMonth = new Date(today);
  previousMonth.setDate(today.getDate() - 30);
  if (date >= previousMonth) return 'Previous 30 days';
  return 'Earlier';
}

const DEFAULT_SIDEBAR_WIDTH = 260;
const MIN_SIDEBAR_WIDTH = 200;
const MAX_SIDEBAR_WIDTH = 480;

export const AppLayout: React.FC = () => {
  const query = '';
  const [sidebarWidth, setSidebarWidth] = useState<number>(() => {
    if (typeof window === 'undefined') return DEFAULT_SIDEBAR_WIDTH;
    const saved = localStorage.getItem('clyptus_sidebar_width');
    const num = saved ? parseInt(saved, 10) : DEFAULT_SIDEBAR_WIDTH;
    return isNaN(num) ? DEFAULT_SIDEBAR_WIDTH : Math.min(Math.max(num, MIN_SIDEBAR_WIDTH), MAX_SIDEBAR_WIDTH);
  });
  const [isResizing, setIsResizing] = useState(false);

  const [menuOpen, setMenuOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [recentsOpen, setRecentsOpen] = useState(true);
  const [projectsOpen, setProjectsOpen] = useState(true);
  const [pinnedOpen, setPinnedOpen] = useState(true);
  const [desktopCollapsed, setDesktopCollapsed] = useState(false);
  const [isMobileScreen, setIsMobileScreen] = useState(
    typeof window !== 'undefined' ? window.innerWidth <= 900 : false
  );
  const [searchModalOpen, setSearchModalOpen] = useState(false);
  const [projectModalOpen, setProjectModalOpen] = useState(false);
  const [helpModalOpen, setHelpModalOpen] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const userRowRef = useRef<HTMLButtonElement>(null);

  const [chats, setChats] = useState<Chat[]>([]);
  const [chatsLoading, setChatsLoading] = useState(true);
  const [projects, setProjects] = useState<Project[]>([]);

  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  // Track window resize to adapt toggle button visibility like ChatGPT
  useEffect(() => {
    const handleResize = () => {
      setIsMobileScreen(window.innerWidth <= 900);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // ChatGPT-style sidebar drag resize listeners
  const startResizing = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
  }, []);

  useEffect(() => {
    if (!isResizing) return;

    const handleMouseMove = (e: MouseEvent) => {
      let newWidth = e.clientX;
      if (newWidth < 140) {
        setDesktopCollapsed(true);
        setIsResizing(false);
        return;
      }
      if (desktopCollapsed) {
        setDesktopCollapsed(false);
      }
      newWidth = Math.min(Math.max(newWidth, MIN_SIDEBAR_WIDTH), MAX_SIDEBAR_WIDTH);
      setSidebarWidth(newWidth);
    };

    const handleMouseUp = () => {
      setIsResizing(false);
      localStorage.setItem('clyptus_sidebar_width', String(sidebarWidth));
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [isResizing, sidebarWidth, desktopCollapsed]);

  const handleResetSidebarWidth = () => {
    setSidebarWidth(DEFAULT_SIDEBAR_WIDTH);
    localStorage.setItem('clyptus_sidebar_width', String(DEFAULT_SIDEBAR_WIDTH));
  };

  const handleOpenSearch = () => {
    setSearchModalOpen(true);
  };

  // Global ChatGPT-style keyboard shortcuts:
  // Ctrl+Shift+S (or Cmd+Shift+S): Toggle sidebar
  // Ctrl+Shift+O (or Cmd+Shift+O): New chat
  // Ctrl+K (or Cmd+K): Search
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === 's') {
        e.preventDefault();
        toggleSidebar();
      }
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === 'o') {
        e.preventDefault();
        handleNewChat();
      }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        handleOpenSearch();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [desktopCollapsed, sidebarOpen]);

  const isConversation = location.pathname === '/app' || location.pathname.includes('/chat/');

  // Refresh chats list
  const refreshChats = async () => {
    try {
      const data = await apiGetChats();
      setChats(data);
    } catch {
      // Keep the sidebar usable when chat history cannot be loaded.
      setChats([]);
    } finally {
      setChatsLoading(false);
    }
  };

  useEffect(() => {
    refreshChats();
  }, [location.pathname]);

  useEffect(() => {
    apiGetProjects().then(setProjects).catch(() => setProjects([]));
  }, [location.pathname]);

  useEffect(() => {
    const applyTheme = () => {
      const pref = localStorage.getItem('clyptus-appearance');
      const media = window.matchMedia('(prefers-color-scheme: dark)');
      const isDark = pref === 'dark' || (!pref && true) || (pref === 'system' && media.matches);
      document.documentElement.classList.toggle('dark', isDark);
    };
    applyTheme();
    window.addEventListener('storage', applyTheme);
    window.addEventListener('theme-change', applyTheme);
    return () => {
      window.removeEventListener('storage', applyTheme);
      window.removeEventListener('theme-change', applyTheme);
    };
  }, []);

  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname, location.search]);

  const normalizedQuery = query.trim().toLowerCase();

  const enrichedChats = chats;

  const filteredChats = useMemo(() => {
    return enrichedChats.filter(chat => !normalizedQuery || chat.title.toLowerCase().includes(normalizedQuery));
  }, [enrichedChats, normalizedQuery]);

  const filteredProjects = useMemo(() => {
    return projects.filter(project => !normalizedQuery || project.name.toLowerCase().includes(normalizedQuery));
  }, [projects, normalizedQuery]);

  const groupedChats = useMemo(() => {
    return ['Today', 'Yesterday', 'Previous 7 days', 'Previous 30 days', 'Earlier']
      .map(group => ({
        group,
        chats: filteredChats.filter(chat => !chat.isPinned && dateGroup(chat) === group),
      }))
      .filter(group => group.chats.length > 0);
  }, [filteredChats]);

  const pinnedChats = useMemo(() => {
    return enrichedChats.filter(chat => chat.isPinned && (!normalizedQuery || chat.title.toLowerCase().includes(normalizedQuery)));
  }, [enrichedChats, normalizedQuery]);

  const pinnedProjects = useMemo(() => {
    return projects.filter(project => project.isPinned && (!normalizedQuery || project.name.toLowerCase().includes(normalizedQuery)));
  }, [projects, normalizedQuery]);

  const handleLogout = () => {
    logout();
    navigate('/login', { replace: true });
  };

  const handleNewChat = async () => {
    try {
      const newChat = await apiCreateChat('New SAP Chat');
      setChats(prev => [newChat, ...prev]);
      navigate(`/app/chat/${newChat.id}`);
    } catch {
      navigate('/app');
    }
  };

  const handleDeleteChat = async (chatId: string) => {
    if (!window.confirm('Delete this chat?')) return;
    try {
      await apiDeleteChat(chatId);
      setChats(prev => prev.filter(c => c.id !== chatId));
      if (location.pathname.includes(chatId)) {
        navigate('/app');
      }
    } catch (err) {
      console.error('Failed to delete chat:', err);
      setActionError('Could not delete chat.');
    }
  };

  const handleRenameChat = async (chatId: string, title: string) => {
    try {
      const updated = await apiUpdateChat(chatId, title);
      setChats(prev => prev.map(chat => chat.id === chatId ? { ...chat, ...updated } : chat));
      setActionError(null);
    } catch {
      setActionError('Could not rename chat.');
    }
  };

  const handleCreateProject = async (values: { name: string; description?: string }) => {
    try {
      setActionError(null);
      const project = await apiCreateProject(values.name, values.description);
      setProjects(prev => [project, ...prev]);
      setProjectModalOpen(false);
      navigate(`/app/projects/${project.id}`);
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : 'Could not create project.');
    }
  };

  const toggleChatPin = async (chatId: string, isPinned: boolean) => {
    try {
      const updated = await apiSetChatPinned(chatId, !isPinned);
      setChats(prev => prev.map(chat => chat.id === chatId ? { ...chat, isPinned: updated.isPinned } : chat));
      setActionError(null);
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : 'Could not update chat pin.');
    }
  };

  const toggleProjectPin = async (projectId: string, currentPin: boolean) => {
    try {
      const updated = await apiUpdateProject(projectId, { isPinned: !currentPin });
      setProjects(prev => prev.map(project => project.id === projectId ? updated : project));
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : 'Could not update pin.');
    }
  };

  const toggleSidebar = () => {
    if (window.innerWidth <= 900) {
      setSidebarOpen(prev => !prev);
    } else {
      setDesktopCollapsed(prev => !prev);
    }
  };

  const userInitial = user?.name ? user.name.charAt(0).toUpperCase() : 'C';

  return (
    <div
      className={`app-shell ${desktopCollapsed ? 'desktop-collapsed' : ''} ${isConversation ? 'app-shell-chat' : ''} ${isResizing ? 'is-resizing-sidebar' : ''}`}
      style={{
        gridTemplateColumns: isMobileScreen
          ? '1fr'
          : desktopCollapsed
          ? '0px minmax(0, 1fr)'
          : `${sidebarWidth}px minmax(0, 1fr)`,
        transition: isResizing ? 'none' : undefined,
      }}
    >
      {sidebarOpen && (
        <button
          className="sidebar-backdrop"
          type="button"
          aria-label="Close sidebar"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`app-sidebar ${sidebarOpen ? 'app-sidebar-open' : ''}`}
        aria-label="Workspace sidebar"
        style={{
          width: isMobileScreen ? undefined : (desktopCollapsed ? 0 : `${sidebarWidth}px`),
          transition: isResizing ? 'none' : undefined,
        }}
      >
        <div className="app-brand-row">
          <BrandLogo light={false} />
          <div className="flex items-center gap-1 ml-auto">
            <button
              className="chat-toggle-icon-btn text-stone-600 hover:text-stone-900 hover:bg-black/5"
              type="button"
              aria-label="Search"
              title="Search (Ctrl+K)"
              onClick={handleOpenSearch}
            >
              <Search size={18} />
            </button>
            <button
              className="chat-toggle-icon-btn text-stone-600 hover:text-stone-900 hover:bg-black/5"
              type="button"
              aria-label="Close sidebar"
              title="Close sidebar (Ctrl+Shift+S)"
              onClick={toggleSidebar}
            >
              <PanelLeft size={18} />
            </button>
          </div>
        </div>

        <button className="new-chat-button" type="button" onClick={handleNewChat}>
          <MessageSquarePlus size={17} />
          New chat
        </button>


        {actionError && <p className="sidebar-error" role="alert">{actionError}</p>}

        {/* History area */}
        <div className="history-area">
          <div className="history-caption">
            <button className="history-toggle" type="button" aria-expanded={recentsOpen} onClick={() => setRecentsOpen(open => !open)}>
              <ChevronDown size={13} className={recentsOpen ? '' : 'is-collapsed'} />
              <span>RECENTS</span>
            </button>
            {chatsLoading && <span>LOADING</span>}
          </div>

          {recentsOpen && groupedChats.map(({ group, chats: items }) => (
            <div className="sidebar-group" key={group}>
              <span className="conversation-group">{group}</span>
              {items.map(chat => <SidebarChatItem key={chat.id} chat={chat} isPinned={false} onRename={handleRenameChat} onDelete={handleDeleteChat} onTogglePin={toggleChatPin} />)}
            </div>
          ))}

          {recentsOpen && !chatsLoading && groupedChats.length === 0 && (
            <p className="sidebar-empty">
              {normalizedQuery ? 'No matching chats.' : 'Your conversations will appear here.'}
            </p>
          )}

          <ScrollToSearchButton />

          {/* Projects */}
          <div className="sidebar-section-heading">
            <button className="section-toggle" type="button" aria-expanded={projectsOpen} onClick={() => setProjectsOpen(open => !open)}>
              <ChevronDown size={13} className={projectsOpen ? '' : 'is-collapsed'} />
              <span>PROJECTS</span>
            </button>
          </div>

          {projectsOpen && <>
          {filteredProjects.map((project) => (
            <div className="sidebar-item-row" key={project.id}>
              <NavLink
                className={({ isActive }) => `conversation-link project-link ${isActive ? 'active' : ''}`}
                to={`/app/projects/${project.id}`}
                title={project.name}
              >
                {project.name}
              </NavLink>
              <button
                className={`sidebar-pin ${project.isPinned ? 'is-pinned' : ''}`}
                type="button"
                aria-label={`${project.isPinned ? 'Unpin' : 'Pin'} project ${project.name}`}
                title={project.isPinned ? 'Unpin project' : 'Pin project'}
                onClick={() => void toggleProjectPin(project.id, project.isPinned)}
              >
                {project.isPinned ? <PinOff size={13} /> : <Pin size={13} />}
              </button>
            </div>
          ))}

          {filteredProjects.length === 0 && (
            <p className="sidebar-empty">
              {normalizedQuery ? 'No matching projects.' : 'No projects yet.'}
            </p>
          )}

          <button
            className="sidebar-new-project"
            type="button"
            onClick={() => setProjectModalOpen(true)}
          >
            <FolderPlus size={14} />
            New project
          </button>
          </>}

          {/* Pinned section */}
          <div className="sidebar-section-heading pinned-heading">
            <button className="section-toggle" type="button" aria-expanded={pinnedOpen} onClick={() => setPinnedOpen(open => !open)}>
              <ChevronDown size={13} className={pinnedOpen ? '' : 'is-collapsed'} />
              <span>PINNED</span>
            </button>
          </div>

          {pinnedOpen && <>
          {pinnedChats.length === 0 && pinnedProjects.length === 0 && (
            <p className="sidebar-empty">Pinned items appear here.</p>
          )}

          {pinnedChats.map(chat => <SidebarChatItem key={`pinned-chat-${chat.id}`} chat={chat} isPinned={true} onRename={handleRenameChat} onDelete={handleDeleteChat} onTogglePin={toggleChatPin} />)}

          {pinnedProjects.map((project) => (
            <NavLink className="pinned-link" key={`pinned-proj-${project.id}`} to={`/app/projects/${project.id}`}>
              <Pin size={12} />
              <span>{project.name}</span>
              <small>Project</small>
            </NavLink>
          ))}
          </>}
        </div>

        {/* Bottom user card */}
        <div className="sidebar-bottom">
          <button
            className="workspace-help"
            type="button"
            onClick={() => setHelpModalOpen(true)}
            title="SAP + BRIM Assistant Guide"
          >
            <CircleHelp size={16} />
            <span>SAP + BRIM assistant</span>
            <span className="help-arrow">↗</span>
          </button>

          <button
            ref={userRowRef}
            className="account-button"
            type="button"
            onClick={() => setMenuOpen(!menuOpen)}
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            aria-controls="account-dropdown-menu"
            id="account-dropdown-trigger"
          >
            <span className="account-avatar">
              {user?.avatar ? <img src={user.avatar} alt="" /> : userInitial}
            </span>
            <span className="account-details">
              <strong>{user?.name || 'SAP Consultant'}</strong>
              <small>{user?.email || 'Enterprise User'}</small>
            </span>
            <ChevronDown
              size={15}
              className={`account-chevron ${menuOpen ? 'rotate-180' : ''}`}
            />
          </button>

          <AccountMenu
            isOpen={menuOpen}
            onClose={() => setMenuOpen(false)}
            triggerRef={userRowRef}
            onOpenHelp={() => {
              setMenuOpen(false);
              setHelpModalOpen(true);
            }}
            onLogout={handleLogout}
          />
        </div>

        {/* ChatGPT-style Drag / Adjusting Bar on the right edge of sidebar */}
        {!desktopCollapsed && !isMobileScreen && (
          <div
            className={`sidebar-drag-handle ${isResizing ? 'is-dragging' : ''}`}
            onMouseDown={startResizing}
            onDoubleClick={handleResetSidebarWidth}
            title="Drag to resize sidebar • Double-click to reset"
            role="separator"
            aria-orientation="vertical"
            aria-valuenow={sidebarWidth}
            aria-valuemin={MIN_SIDEBAR_WIDTH}
            aria-valuemax={MAX_SIDEBAR_WIDTH}
          >
            <div className="sidebar-drag-line" />
          </div>
        )}
      </aside>

      {/* Main Container */}
      <main className={`app-main ${isConversation ? 'app-main-chat' : ''}`}>
        {isConversation ? (
          <header className="app-topbar-minimal">
            <div className="flex items-center gap-1">
              {/* ChatGPT exact toggle group: shown when sidebar is collapsed/hidden */}
              {(desktopCollapsed || isMobileScreen) && (
                <>
                  <button
                    className="chat-toggle-icon-btn"
                    type="button"
                    aria-label="Open sidebar"
                    title="Open sidebar (Ctrl+Shift+S)"
                    onClick={toggleSidebar}
                  >
                    <PanelLeft size={18} />
                  </button>
                  <button
                    className="chat-toggle-icon-btn"
                    type="button"
                    aria-label="Search"
                    title="Search (Ctrl+K)"
                    onClick={handleOpenSearch}
                  >
                    <Search size={18} />
                  </button>
                  <button
                    className="chat-toggle-icon-btn"
                    type="button"
                    aria-label="New chat"
                    title="New chat (Ctrl+Shift+O)"
                    onClick={handleNewChat}
                  >
                    <SquarePen size={18} />
                  </button>
                </>
              )}
            </div>

            <div className="ml-auto flex items-center gap-2">
              <button
                className="chat-toggle-icon-btn"
                type="button"
                onClick={() => window.dispatchEvent(new CustomEvent('export-current-chat'))}
                title="Export conversation"
                aria-label="Export conversation"
              >
                <Share size={17} />
              </button>
            </div>
          </header>
        ) : (
          <header className="app-topbar">
            <div className="app-topbar-left">
              {(desktopCollapsed || isMobileScreen) && (
                <button
                  className="chat-toggle-icon-btn mr-1.5"
                  type="button"
                  aria-label="Open sidebar"
                  title="Open sidebar (Ctrl+Shift+S)"
                  onClick={toggleSidebar}
                >
                  <PanelLeft size={18} />
                </button>
              )}
              <div className="app-breadcrumb">
                <strong>
                  {location.pathname.split('/').pop()?.replace(/^\w/, (c) => c.toUpperCase()) || 'Workspace'}
                </strong>
              </div>
            </div>
            <div className="app-top-actions">
              <button className="top-new-chat" type="button" onClick={handleNewChat}>
                <MessageSquarePlus size={14} />
                New chat
              </button>
              <span className="backend-status">
                <i />
                Live connected
              </span>
              <span className="top-avatar">
                {user?.avatar ? <img src={user.avatar} alt="" /> : userInitial}
              </span>
            </div>
          </header>
        )}

        {/* Content Route */}
        <Outlet />
      </main>

      {projectModalOpen && (
        <ProjectModal
          error={actionError}
          onClose={() => {
            setProjectModalOpen(false);
            setActionError(null);
          }}
          onSave={handleCreateProject}
        />
      )}

      <AssistantGuideModal
        isOpen={helpModalOpen}
        onClose={() => setHelpModalOpen(false)}
      />

      <SearchModal
        isOpen={searchModalOpen}
        onClose={() => setSearchModalOpen(false)}
        chats={chats}
        projects={projects}
        onSelectChat={(chatId) => navigate(`/app/chat/${chatId}`)}
        onSelectProject={(projectId) => navigate(`/app/projects/${projectId}`)}
      />
    </div>
  );
};
