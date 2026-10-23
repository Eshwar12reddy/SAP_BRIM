import React, { useState, useEffect } from 'react';
import {
  Download,
  Copy,
  Check,
  Maximize2,
  X,
  RotateCcw,
  AlertCircle,
  Image as ImageIcon,
  Sparkles,
} from 'lucide-react';
import type { VisualItem } from '../../types';
import { apiGetVisualMeta, apiFetchVisualBlob, apiRegenerateVisual } from '../../services/api';

interface VisualCardProps {
  visual: VisualItem;
  onVisualUpdated?: (updated: VisualItem) => void;
}

export const VisualCard: React.FC<VisualCardProps> = ({ visual, onVisualUpdated }) => {
  const [currentVisual, setCurrentVisual] = useState<VisualItem>(visual);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(visual.status === 'pending');
  const [error, setError] = useState<string | null>(visual.error_message || null);
  const [isLightboxOpen, setIsLightboxOpen] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);
  const [isRegenerating, setIsRegenerating] = useState<boolean>(false);

  const visualId = currentVisual.visual_id || currentVisual.id;

  // Poll or load visual asset
  useEffect(() => {
    let isMounted = true;
    let pollTimeout: any = null;

    const loadAsset = async () => {
      if (!visualId) return;

      try {
        if (currentVisual.status === 'pending') {
          setIsLoading(true);
          const meta = await apiGetVisualMeta(visualId);
          if (!isMounted) return;

          if (meta.status === 'completed') {
            setCurrentVisual(meta);
            onVisualUpdated?.(meta);
            // Fetch blob with auth headers
            const blob = await apiFetchVisualBlob(visualId);
            if (!isMounted) return;
            const url = URL.createObjectURL(blob);
            setBlobUrl(url);
            setIsLoading(false);
          } else if (meta.status === 'failed') {
            setCurrentVisual(meta);
            setError(meta.error_message || 'Image generation failed');
            setIsLoading(false);
          } else {
            // Poll again in 1.5 seconds
            pollTimeout = setTimeout(loadAsset, 1500);
          }
        } else if (currentVisual.status === 'completed' && !blobUrl) {
          setIsLoading(true);
          const blob = await apiFetchVisualBlob(visualId);
          if (!isMounted) return;
          const url = URL.createObjectURL(blob);
          setBlobUrl(url);
          setIsLoading(false);
        }
      } catch (err: any) {
        if (isMounted) {
          logger_silent(err);
          // If 404 or still pending, retry a few times
          if (currentVisual.status === 'pending') {
            pollTimeout = setTimeout(loadAsset, 2000);
          } else {
            setError('Image temporarily unavailable');
            setIsLoading(false);
          }
        }
      }
    };

    loadAsset();

    return () => {
      isMounted = false;
      if (pollTimeout) clearTimeout(pollTimeout);
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
  }, [visualId, currentVisual.status]);

  // Close lightbox on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isLightboxOpen) {
        setIsLightboxOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isLightboxOpen]);

  const handleCopy = async () => {
    if (!blobUrl) return;
    try {
      const resp = await fetch(blobUrl);
      const blob = await resp.blob();
      if (navigator.clipboard && (window as any).ClipboardItem) {
        // Try clipboard item
        try {
          await navigator.clipboard.write([new (window as any).ClipboardItem({ [blob.type]: blob })]);
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
          return;
        } catch {
          // Fallback to text copy of caption/title
        }
      }
      await navigator.clipboard.writeText(`${currentVisual.title}\n${currentVisual.caption}`);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
      navigator.clipboard.writeText(currentVisual.title);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleDownload = async () => {
    if (!blobUrl) return;
    const isSvg = currentVisual.mime_type?.includes('svg') || !currentVisual.is_generative;
    const ext = isSvg ? 'svg' : 'png';
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = `${(currentVisual.title || 'sap-diagram').toLowerCase().replace(/\s+/g, '-')}.${ext}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const handleRegenerate = async (instruction: string = 'make it simpler') => {
    if (!visualId || isRegenerating) return;
    try {
      setIsRegenerating(true);
      setError(null);
      const revised = await apiRegenerateVisual(visualId, instruction);
      setCurrentVisual(revised);
      setIsLoading(true);
      setBlobUrl(null);
      onVisualUpdated?.(revised);
    } catch (err: any) {
      setError('Revision request failed. Please try again.');
    } finally {
      setIsRegenerating(false);
    }
  };

  return (
    <div className="my-4 rounded-xl border border-slate-200 dark:border-[#1e1e2c] bg-white dark:bg-[#0c0c14] shadow-sm overflow-hidden transition-all duration-200 hover:shadow-md">
      {/* Visual Header */}
      <div className="px-4 py-2.5 bg-slate-50 dark:bg-[#12121e] border-b border-slate-200 dark:border-[#1e1e2c] flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <div className="p-1 rounded-md bg-orange-500/10 text-orange-600 dark:text-orange-400">
            <ImageIcon className="w-3.5 h-3.5" />
          </div>
          <span className="text-xs font-semibold text-slate-800 dark:text-slate-200 truncate">
            {currentVisual.title || 'Technical Diagram'}
          </span>
          {currentVisual.is_generative && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-purple-500/10 text-purple-600 dark:text-purple-300 border border-purple-500/20">
              <Sparkles className="w-2.5 h-2.5" />
              <span>Concept</span>
            </span>
          )}
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-1 shrink-0">
          {blobUrl && (
            <>
              <button
                type="button"
                onClick={handleCopy}
                className="p-1 rounded hover:bg-slate-200 dark:hover:bg-[#1c1c28] text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 transition"
                title="Copy diagram or caption"
                aria-label="Copy diagram"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
              </button>
              <button
                type="button"
                onClick={handleDownload}
                className="p-1 rounded hover:bg-slate-200 dark:hover:bg-[#1c1c28] text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 transition"
                title="Download diagram file"
                aria-label="Download diagram"
              >
                <Download className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={() => setIsLightboxOpen(true)}
                className="p-1 rounded hover:bg-slate-200 dark:hover:bg-[#1c1c28] text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 transition"
                title="Click to enlarge"
                aria-label="Expand image"
              >
                <Maximize2 className="w-3.5 h-3.5" />
              </button>
            </>
          )}
        </div>
      </div>

      {/* Visual Content Body */}
      <div className="p-3 bg-slate-50/50 dark:bg-[#07070d] flex flex-col items-center justify-center min-h-[220px]">
        {isLoading ? (
          <div className="w-full flex flex-col items-center justify-center py-10 space-y-3">
            <div className="w-8 h-8 rounded-full border-2 border-orange-500 border-t-transparent animate-spin" />
            <div className="text-xs text-slate-500 dark:text-slate-400 font-medium animate-pulse">
              Generating technical visual illustration...
            </div>
            {/* Skeleton placeholders */}
            <div className="w-full max-w-md h-32 bg-slate-200 dark:bg-slate-800/40 rounded-lg animate-pulse" />
          </div>
        ) : error || currentVisual.status === 'failed' ? (
          <div className="w-full py-6 flex flex-col items-center justify-center text-center space-y-2">
            <AlertCircle className="w-6 h-6 text-amber-500" />
            <p className="text-xs text-slate-600 dark:text-slate-400">
              Visual illustration currently unavailable ({error || 'Generation error'})
            </p>
            <button
              type="button"
              onClick={() => handleRegenerate('retry')}
              disabled={isRegenerating}
              className="inline-flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-medium bg-orange-500/10 text-orange-600 hover:bg-orange-500/20 border border-orange-500/20 transition cursor-pointer"
            >
              <RotateCcw className="w-3 h-3" />
              <span>Retry generation</span>
            </button>
          </div>
        ) : blobUrl ? (
          <div className="w-full flex justify-center cursor-zoom-in group/img" onClick={() => setIsLightboxOpen(true)}>
            <img
              src={blobUrl}
              alt={currentVisual.caption || currentVisual.title}
              className="max-h-[460px] w-auto max-w-full rounded-md object-contain border border-slate-200/60 dark:border-slate-800 shadow-xs transition-transform duration-200 group-hover/img:scale-[1.01]"
              loading="lazy"
            />
          </div>
        ) : null}
      </div>

      {/* Caption & Disclaimer Footer */}
      <div className="px-4 py-2.5 bg-slate-50/80 dark:bg-[#0f0f18] border-t border-slate-200 dark:border-[#1e1e2c] flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2">
        <p className="text-[11px] text-slate-600 dark:text-slate-400 leading-normal">
          {currentVisual.caption || 'AI-generated architectural visual illustration.'}
        </p>

        <div className="flex items-center gap-2 shrink-0">
          <span className="text-[10px] font-mono text-slate-400 dark:text-slate-500 bg-slate-200/50 dark:bg-slate-800/60 px-1.5 py-0.5 rounded">
            AI illustration • Not an SAP screenshot
          </span>

          {blobUrl && (
            <button
              type="button"
              onClick={() => handleRegenerate('make it simpler')}
              disabled={isRegenerating}
              className="text-[10px] text-orange-600 dark:text-orange-400 hover:underline inline-flex items-center gap-1 cursor-pointer"
              title="Simplify visual components"
            >
              <RotateCcw className="w-2.5 h-2.5" />
              <span>Simplify</span>
            </button>
          )}
        </div>
      </div>

      {/* Lightbox Modal */}
      {isLightboxOpen && blobUrl && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-sm p-4 animate-in fade-in duration-200"
          onClick={() => setIsLightboxOpen(false)}
          role="dialog"
          aria-modal="true"
        >
          <div
            className="relative max-w-5xl max-h-[92vh] w-full bg-white dark:bg-[#0c0c14] rounded-2xl shadow-2xl border border-slate-200 dark:border-[#1e1e2c] flex flex-col overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="px-5 py-3 border-b border-slate-200 dark:border-[#1e1e2c] flex items-center justify-between">
              <div className="min-w-0">
                <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 truncate">
                  {currentVisual.title}
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 truncate">
                  {currentVisual.caption}
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <button
                  type="button"
                  onClick={handleDownload}
                  className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 transition"
                  title="Download image"
                >
                  <Download className="w-4 h-4" />
                </button>
                <button
                  type="button"
                  onClick={() => setIsLightboxOpen(false)}
                  className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 transition"
                  title="Close (Esc)"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Modal Image View */}
            <div className="p-6 overflow-auto flex items-center justify-center bg-slate-100/50 dark:bg-black/40">
              <img
                src={blobUrl}
                alt={currentVisual.caption || currentVisual.title}
                className="max-h-[75vh] w-auto max-w-full rounded-lg shadow-sm object-contain"
              />
            </div>

            {/* Modal Footer */}
            <div className="px-5 py-2.5 bg-slate-50 dark:bg-[#12121e] border-t border-slate-200 dark:border-[#1e1e2c] flex items-center justify-between text-xs text-slate-500">
              <span>Press Esc or click outside to dismiss</span>
              <span className="font-mono text-[11px] text-amber-600 dark:text-amber-400">
                AI-generated illustration — not an SAP screenshot
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

function logger_silent(..._args: any[]) {
  // Silent logging helper
}
