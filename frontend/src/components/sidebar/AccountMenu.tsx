import React, { useEffect, useRef, useState, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { User, Settings, LifeBuoy, ChevronRight, LogOut } from 'lucide-react';
import './AccountMenu.css';

export interface AccountMenuProps {
  isOpen: boolean;
  onClose: () => void;
  triggerRef: React.RefObject<HTMLElement | null>;
  onOpenHelp: () => void;
  onLogout: () => void;
}

interface MenuItemDef {
  id: string;
  label: string;
  icon: React.ReactNode;
  rightIcon?: React.ReactNode;
  action: () => void;
  className?: string;
}

export const AccountMenu: React.FC<AccountMenuProps> = ({
  isOpen,
  onClose,
  triggerRef,
  onOpenHelp,
  onLogout,
}) => {
  const navigate = useNavigate();
  const menuRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const [focusedIndex, setFocusedIndex] = useState<number>(0);

  const [coords, setCoords] = useState<{
    bottom: number;
    left: number;
    width: number;
  }>({ bottom: 0, left: 0, width: 220 });

  // Compute position relative to the trigger button
  const updatePosition = useCallback(() => {
    if (!triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    const margin = 8;
    const screenWidth = window.innerWidth;
    const screenHeight = window.innerHeight;

    // Trigger width or at least 220px (e.g. if collapsed sidebar)
    const targetWidth = Math.max(rect.width, 220);
    const clampedWidth = Math.min(targetWidth, screenWidth - margin * 2);

    // Open upward from trigger
    const bottom = Math.max(margin, screenHeight - rect.top + 6);

    // Align horizontally with trigger, clamped within screen
    let left = rect.left;
    if (left + clampedWidth > screenWidth - margin) {
      left = screenWidth - clampedWidth - margin;
    }
    if (left < margin) {
      left = margin;
    }

    setCoords({ bottom, left, width: clampedWidth });
  }, [triggerRef]);

  // Update position when open and on resize/scroll
  useEffect(() => {
    if (!isOpen) return;

    updatePosition();

    const handleResize = () => updatePosition();
    const handleScroll = () => updatePosition();

    window.addEventListener('resize', handleResize);
    window.addEventListener('scroll', handleScroll, true);

    return () => {
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('scroll', handleScroll, true);
    };
  }, [isOpen, updatePosition]);

  // Close on outside click
  useEffect(() => {
    if (!isOpen) return;

    const handlePointerDown = (event: MouseEvent | TouchEvent) => {
      const target = event.target as Node;
      if (
        menuRef.current &&
        !menuRef.current.contains(target) &&
        triggerRef.current &&
        !triggerRef.current.contains(target)
      ) {
        onClose();
      }
    };

    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('touchstart', handlePointerDown);

    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('touchstart', handlePointerDown);
    };
  }, [isOpen, onClose, triggerRef]);

  // Define menu items in specified order
  const menuItems: MenuItemDef[] = [
    {
      id: 'profile',
      label: 'Profile',
      icon: <User className="account-menu-icon" />,
      action: () => {
        onClose();
        navigate('/app/profile');
      },
    },
    {
      id: 'settings',
      label: 'Settings',
      icon: <Settings className="account-menu-icon" />,
      action: () => {
        onClose();
        navigate('/app/settings');
      },
    },
    // Divider is rendered separately between Settings and Help
    {
      id: 'help',
      label: 'Help',
      icon: <LifeBuoy className="account-menu-icon" />,
      rightIcon: <ChevronRight className="account-menu-right-icon" />,
      action: () => {
        onClose();
        onOpenHelp();
      },
    },
    {
      id: 'logout',
      label: 'Log out',
      icon: <LogOut className="account-menu-icon" />,
      className: 'account-menu-logout',
      action: () => {
        onClose();
        onLogout();
      },
    },
  ];

  // Focus management when menu opens
  useEffect(() => {
    if (isOpen) {
      setFocusedIndex(0);
      // Ensure element is mounted and focused
      const timer = requestAnimationFrame(() => {
        itemRefs.current[0]?.focus();
      });
      return () => cancelAnimationFrame(timer);
    }
  }, [isOpen]);

  // Keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    const count = menuItems.length;

    switch (e.key) {
      case 'ArrowDown': {
        e.preventDefault();
        const next = (focusedIndex + 1) % count;
        setFocusedIndex(next);
        itemRefs.current[next]?.focus();
        break;
      }
      case 'ArrowUp': {
        e.preventDefault();
        const prev = (focusedIndex - 1 + count) % count;
        setFocusedIndex(prev);
        itemRefs.current[prev]?.focus();
        break;
      }
      case 'Home': {
        e.preventDefault();
        setFocusedIndex(0);
        itemRefs.current[0]?.focus();
        break;
      }
      case 'End': {
        e.preventDefault();
        setFocusedIndex(count - 1);
        itemRefs.current[count - 1]?.focus();
        break;
      }
      case 'Escape': {
        e.preventDefault();
        onClose();
        triggerRef.current?.focus();
        break;
      }
      case 'Tab': {
        // Tab closes menu and allows natural focus traversal
        onClose();
        break;
      }
      case 'Enter':
      case ' ': {
        e.preventDefault();
        menuItems[focusedIndex]?.action();
        break;
      }
      default:
        break;
    }
  };

  if (!isOpen) return null;

  return createPortal(
    <div
      ref={menuRef}
      id="account-dropdown-menu"
      role="menu"
      aria-labelledby="account-dropdown-trigger"
      className="account-menu-panel"
      style={{
        bottom: `${coords.bottom}px`,
        left: `${coords.left}px`,
        width: `${coords.width}px`,
      }}
      tabIndex={-1}
      onKeyDown={handleKeyDown}
    >
      {/* 1. Profile */}
      <button
        ref={(el) => { itemRefs.current[0] = el; }}
        type="button"
        role="menuitem"
        id="account-menuitem-profile"
        tabIndex={focusedIndex === 0 ? 0 : -1}
        className={`account-menu-item ${focusedIndex === 0 ? 'is-focused' : ''}`}
        onClick={menuItems[0].action}
        onMouseEnter={() => setFocusedIndex(0)}
      >
        {menuItems[0].icon}
        <span>{menuItems[0].label}</span>
      </button>

      {/* 2. Settings */}
      <button
        ref={(el) => { itemRefs.current[1] = el; }}
        type="button"
        role="menuitem"
        id="account-menuitem-settings"
        tabIndex={focusedIndex === 1 ? 0 : -1}
        className={`account-menu-item ${focusedIndex === 1 ? 'is-focused' : ''}`}
        onClick={menuItems[1].action}
        onMouseEnter={() => setFocusedIndex(1)}
      >
        {menuItems[1].icon}
        <span>{menuItems[1].label}</span>
      </button>

      {/* 3. Thin horizontal divider */}
      <div role="separator" className="account-menu-divider" />

      {/* 4. Help */}
      <button
        ref={(el) => { itemRefs.current[2] = el; }}
        type="button"
        role="menuitem"
        id="account-menuitem-help"
        tabIndex={focusedIndex === 2 ? 0 : -1}
        className={`account-menu-item ${focusedIndex === 2 ? 'is-focused' : ''}`}
        onClick={menuItems[2].action}
        onMouseEnter={() => setFocusedIndex(2)}
      >
        {menuItems[2].icon}
        <span>{menuItems[2].label}</span>
        {menuItems[2].rightIcon}
      </button>

      {/* 5. Log out */}
      <button
        ref={(el) => { itemRefs.current[3] = el; }}
        type="button"
        role="menuitem"
        id="account-menuitem-logout"
        tabIndex={focusedIndex === 3 ? 0 : -1}
        className={`account-menu-item ${menuItems[3].className || ''} ${focusedIndex === 3 ? 'is-focused' : ''}`}
        onClick={menuItems[3].action}
        onMouseEnter={() => setFocusedIndex(3)}
      >
        {menuItems[3].icon}
        <span>{menuItems[3].label}</span>
      </button>
    </div>,
    document.body
  );
};
