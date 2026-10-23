import React, { useEffect, useState, useCallback } from 'react';
import { ArrowUp, ArrowDown } from 'lucide-react';
import './RightSideScrollButton.css';

interface RightSideScrollButtonProps {
  containerRef: React.RefObject<HTMLDivElement | null>;
  onScrollToBottom?: () => void;
}

export const RightSideScrollButton: React.FC<RightSideScrollButtonProps> = ({
  containerRef,
  onScrollToBottom,
}) => {
  const [canScrollUp, setCanScrollUp] = useState(false);
  const [canScrollDown, setCanScrollDown] = useState(false);

  const checkScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;

    const scrollTop = el.scrollTop;
    const scrollHeight = el.scrollHeight;
    const clientHeight = el.clientHeight;
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;

    // Show scroll-to-top when scrolled down more than 80px
    setCanScrollUp(scrollTop > 80);

    // Show scroll-to-bottom when scrolled up more than 80px from bottom (and content overflows)
    setCanScrollDown(distanceFromBottom > 80 && scrollHeight > clientHeight + 40);
  }, [containerRef]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    el.addEventListener('scroll', checkScroll, { passive: true });
    checkScroll();

    // Check on window/container resize or content change
    const observer = new ResizeObserver(() => checkScroll());
    observer.observe(el);

    return () => {
      el.removeEventListener('scroll', checkScroll);
      observer.disconnect();
    };
  }, [containerRef, checkScroll]);

  const handleScrollTop = () => {
    const el = containerRef.current;
    if (!el) return;
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    el.scrollTo({
      top: 0,
      behavior: prefersReducedMotion ? 'auto' : 'smooth',
    });
  };

  const handleScrollBottom = () => {
    if (onScrollToBottom) {
      onScrollToBottom();
      return;
    }
    const el = containerRef.current;
    if (!el) return;
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    el.scrollTo({
      top: el.scrollHeight,
      behavior: prefersReducedMotion ? 'auto' : 'smooth',
    });
  };

  if (!canScrollUp && !canScrollDown) {
    return null;
  }

  return (
    <div className="right-scroll-controls" aria-label="Page scroll controls">
      {canScrollUp && (
        <button
          type="button"
          onClick={handleScrollTop}
          className="right-scroll-btn is-visible"
          aria-label="Scroll to top of chat"
          title="Scroll to top"
        >
          <ArrowUp size={16} aria-hidden="true" />
        </button>
      )}

      {canScrollDown && (
        <button
          type="button"
          onClick={handleScrollBottom}
          className="right-scroll-btn is-visible"
          aria-label="Scroll to bottom of chat"
          title="Scroll to latest"
        >
          <ArrowDown size={16} aria-hidden="true" />
        </button>
      )}
    </div>
  );
};
