import React, { useEffect, useState, useCallback, useRef } from 'react';
import { ArrowUp } from 'lucide-react';
import './ScrollToSearchButton.css';

export const ScrollToSearchButton: React.FC = () => {
  const [isVisible, setIsVisible] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);

  // Helper to find the scrollable history area
  const getScrollContainer = useCallback((): HTMLElement | null => {
    return (
      buttonRef.current?.closest('.app-sidebar')?.querySelector('.history-area') ||
      document.querySelector('.history-area')
    );
  }, []);

  // Monitor scroll position of the history container
  useEffect(() => {
    const container = getScrollContainer();
    if (!container) return;

    const checkScroll = () => {
      // Show only when scrolled down from the top
      setIsVisible(container.scrollTop > 20);
    };

    container.addEventListener('scroll', checkScroll, { passive: true });
    checkScroll(); // Check initially

    return () => {
      container.removeEventListener('scroll', checkScroll);
    };
  }, [getScrollContainer]);

  // Jump to search: scroll to top and focus search input
  const handleJumpToSearch = useCallback(() => {
    // 1. If sidebar is collapsed on desktop, uncollapse it
    const shell = document.querySelector('.app-shell');
    if (shell?.classList.contains('desktop-collapsed')) {
      const toggleBtn = document.querySelector('.chat-menu-toggle-btn, .app-mobile-menu') as HTMLButtonElement | null;
      toggleBtn?.click();
    }

    // 2. If mobile drawer is closed, open it
    const sidebar = document.querySelector('.app-sidebar');
    if (window.innerWidth <= 900 && !sidebar?.classList.contains('app-sidebar-open')) {
      const mobileToggle = document.querySelector('.chat-menu-toggle-btn, .app-mobile-menu') as HTMLButtonElement | null;
      mobileToggle?.click();
    }

    // 3. Scroll the Recents/history list back to the top
    const container = getScrollContainer();
    if (container) {
      const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      container.scrollTo({
        top: 0,
        behavior: prefersReducedMotion ? 'auto' : 'smooth',
      });
    }

    // 4. Focus the "Search chats and projects" input so the user can type right away
    setTimeout(() => {
      const searchInput = (
        buttonRef.current?.closest('.app-sidebar')?.querySelector('.conversation-search input') ||
        document.querySelector('.conversation-search input')
      ) as HTMLInputElement | null;

      if (searchInput) {
        searchInput.focus();
        searchInput.select();
      }
    }, 40);
  }, [getScrollContainer]);

  // Global '/' keyboard shortcut to focus search input
  useEffect(() => {
    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      if (e.key === '/' && !['INPUT', 'TEXTAREA'].includes((e.target as HTMLElement)?.tagName)) {
        e.preventDefault();
        handleJumpToSearch();
      }
    };
    window.addEventListener('keydown', handleGlobalKeyDown);
    return () => window.removeEventListener('keydown', handleGlobalKeyDown);
  }, [handleJumpToSearch]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleJumpToSearch();
    }
  };

  return (
    <div
      className={`scroll-to-search-wrap ${isVisible ? 'is-visible' : ''}`}
      aria-hidden={!isVisible}
    >
      {/* Directional arrow mark pointing directly up to the search box */}
      <button
        type="button"
        className="scroll-to-search-pointer"
        onClick={handleJumpToSearch}
        tabIndex={isVisible ? 0 : -1}
        title="Direct to search"
        aria-label="Direct to search box"
      >
        <ArrowUp size={11} className="pointer-arrow" aria-hidden="true" />
        <span>Search</span>
      </button>

      <button
        ref={buttonRef}
        type="button"
        className="scroll-to-search-btn"
        onClick={handleJumpToSearch}
        onKeyDown={handleKeyDown}
        aria-label="Go to search"
        title="Scroll to top & search (or press /)"
        tabIndex={isVisible ? 0 : -1}
      >
        <ArrowUp size={16} aria-hidden="true" />
      </button>
    </div>
  );
};
