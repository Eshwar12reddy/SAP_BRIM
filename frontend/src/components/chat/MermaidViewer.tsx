import { sanitizeMermaid } from './sanitizeMermaid';
import React, { useEffect, useRef, useState, useId } from 'react';
import mermaid from 'mermaid';
import { apiRepairMermaid } from '../../services/api';
import {
  Code,
  Eye,
  Copy,
  Check,
  Download,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Sparkles,
} from 'lucide-react';

interface MermaidViewerProps {
  chart: string;
  title?: string;
  isStreaming?: boolean;
}

// Module-level caches
// svgRenderCache: key = `${theme}::${sanitizedChart}` -> SVG string
const svgRenderCache = new Map<string, string>();
// repairedChartCache: key = originalBrokenChart -> repairedCleanChart
const repairedChartCache = new Map<string, string>();

function getCacheKey(chartSource: string, isDark: boolean): string {
  return `${isDark ? 'dark' : 'light'}::${chartSource}`;
}

const MermaidViewerComponent: React.FC<MermaidViewerProps> = ({
  chart,
  title = 'SAP Architecture Diagram',
  isStreaming = false
}) => {
  const trimmedChart = chart.trim();
  const [currentChart, setCurrentChart] = useState(trimmedChart);
  const [editableChart, setEditableChart] = useState(trimmedChart);
  const [viewMode, setViewMode] = useState<'diagram' | 'source'>('diagram');

  // Synchronously initialize from cache if available to prevent flash or redundant renders
  const [svgContent, setSvgContent] = useState<string>(() => {
    if (typeof document === 'undefined') return '';
    const isDark = document.documentElement.classList.contains('dark');
    const sanitized = sanitizeMermaid(trimmedChart);
    const key = getCacheKey(sanitized, isDark);
    return svgRenderCache.get(key) || '';
  });

  const [renderFailed, setRenderFailed] = useState(false);
  const [_renderError, setRenderError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [zoomLevel, setZoomLevel] = useState(1);
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const [isInteracting, setIsInteracting] = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const uniqueId = useId().replace(/:/g, '_');
  const renderCounter = useRef(0);
  const dragStartRef = useRef<{ startX: number; startY: number; initialX: number; initialY: number } | null>(null);

  useEffect(() => {
    const trimmed = chart.trim();
    if (trimmed !== currentChart) {
      setCurrentChart(trimmed);
      setEditableChart(trimmed);
      setZoomLevel(1);
      setPanOffset({ x: 0, y: 0 });
      setRenderFailed(false);
      setRenderError(null);
    }
  }, [chart]);

  useEffect(() => {
    // If still streaming partial tokens, do not attempt to render incomplete syntax
    if (isStreaming || !currentChart.trim()) return;

    const isDark = document.documentElement.classList.contains('dark');

    // Configure mermaid with strict security level to block arbitrary HTML
    mermaid.initialize({
      startOnLoad: false,
      theme: isDark ? 'dark' : 'default',
      securityLevel: 'strict',
      suppressErrorRendering: true,
      fontFamily: 'Inter, system-ui, sans-serif',
      themeVariables: {
        darkMode: isDark,
        background: isDark ? '#0f172a' : '#f8fafc',
        primaryColor: isDark ? '#1e293b' : '#e0f2fe',
        primaryTextColor: isDark ? '#f8fafc' : '#0f172a',
        primaryBorderColor: isDark ? '#3b82f6' : '#0284c7',
        lineColor: isDark ? '#60a5fa' : '#0369a1',
        secondaryColor: isDark ? '#1e1e38' : '#eef2ff',
        tertiaryColor: isDark ? '#131e32' : '#f0fdf4',
      },
    });

    let isMounted = true;

    const renderDiagram = async () => {
      // 1. Initial sanitization
      let clean = sanitizeMermaid(currentChart.trim());

      // Check if we previously repaired this diagram
      if (repairedChartCache.has(currentChart.trim())) {
        clean = repairedChartCache.get(currentChart.trim())!;
      }

      const cacheKey = getCacheKey(clean, isDark);

      // If already in SVG cache, apply immediately
      if (svgRenderCache.has(cacheKey)) {
        const cachedSvg = svgRenderCache.get(cacheKey)!;
        if (isMounted) {
          setSvgContent(cachedSvg);
          setRenderFailed(false);
          setRenderError(null);
        }
        return;
      }

      // 2. Validate with await mermaid.parse(clean, { suppressErrors: false }) before rendering
      let isValid = false;
      let lastError = '';

      try {
        await mermaid.parse(clean, { suppressErrors: false });
        isValid = true;
      } catch (parseErr: any) {
        lastError = parseErr?.message || String(parseErr);
      }

      // 3. If parse fails: send broken source plus exact parser error back to LLM.
      // Retry up to 2 times, re-sanitizing and re-validating each time.
      if (!isValid) {
        for (let attempt = 1; attempt <= 2 && !isValid; attempt++) {
          try {
            console.warn(`Mermaid validation failed (attempt ${attempt}/2). Requesting auto-repair...`, lastError);
            const repairedRaw = await apiRepairMermaid(clean, lastError);
            const sanitizedRepaired = sanitizeMermaid(repairedRaw);
            await mermaid.parse(sanitizedRepaired, { suppressErrors: false });
            // Succeeded!
            clean = sanitizedRepaired;
            isValid = true;
            repairedChartCache.set(currentChart.trim(), clean);
            break;
          } catch (repairErr: any) {
            lastError = repairErr?.message || String(repairErr);
            console.warn(`Mermaid auto-repair attempt ${attempt} failed:`, lastError);
          }
        }
      }

      // 4. Safe fallback: If all retries fail, do NOT show a red error box.
      // Show diagram source in a code block with a Copy button and "Diagram could not be rendered",
      // and log error to console/server.
      if (!isValid) {
        console.error('Diagram could not be rendered after retries. Mermaid parse error:', lastError);
        if (isMounted) {
          setRenderFailed(true);
          setRenderError(lastError);
        }
        return;
      }

      // 5. Wrap rendering in try/catch and use unique ID per render call so repeated renders don't clash
      const renderId = `svg_${uniqueId}_${++renderCounter.current}_${Date.now()}`;
      try {
        const { svg } = await mermaid.render(renderId, clean);
        document.getElementById(`d${renderId}`)?.remove();
        svgRenderCache.set(cacheKey, svg);
        if (isMounted) {
          setSvgContent(svg);
          setRenderFailed(false);
          setRenderError(null);
        }
      } catch (err: any) {
        document.getElementById(`d${renderId}`)?.remove();
        document.getElementById(renderId)?.remove();
        console.error('Mermaid render error:', err);
        if (isMounted) {
          setRenderFailed(true);
          setRenderError(err?.message || 'Diagram could not be rendered');
        }
      }
    };

    renderDiagram();

    return () => {
      isMounted = false;
    };
  }, [currentChart, isStreaming]);

  const handleCopyCode = () => {
    navigator.clipboard.writeText(currentChart);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleApplyChanges = () => {
    setCurrentChart(editableChart);
    setViewMode('diagram');
  };

  const handleExportSvg = () => {
    if (!svgContent) return;
    const blob = new Blob([svgContent], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `sap-architecture-${Date.now()}.svg`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleExportPng = () => {
    if (!svgContent) return;
    const svgBlob = new Blob([svgContent], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(svgBlob);
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = img.width * 2 || 1600;
      canvas.height = img.height * 2 || 1200;
      const ctx = canvas.getContext('2d');
      if (ctx) {
        ctx.fillStyle = document.documentElement.classList.contains('dark') ? '#0b0f19' : '#ffffff';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        const pngUrl = canvas.toDataURL('image/png');
        const downloadLink = document.createElement('a');
        downloadLink.href = pngUrl;
        downloadLink.download = `sap-architecture-${Date.now()}.png`;
        document.body.appendChild(downloadLink);
        downloadLink.click();
        document.body.removeChild(downloadLink);
      }
      URL.revokeObjectURL(url);
    };
    img.src = url;
  };

  const handleZoomIn = () => {
    setZoomLevel((z) => Math.min(2.5, Math.round((z + 0.15) * 100) / 100));
  };

  const handleZoomOut = () => {
    setZoomLevel((z) => {
      const next = Math.max(0.5, Math.round((z - 0.15) * 100) / 100);
      if (next === 1) {
        setPanOffset({ x: 0, y: 0 });
      }
      return next;
    });
  };

  const handleResetZoom = () => {
    setZoomLevel(1);
    setPanOffset({ x: 0, y: 0 });
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    if (zoomLevel <= 1 || e.button !== 0) return;
    setIsInteracting(true);
    dragStartRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      initialX: panOffset.x,
      initialY: panOffset.y,
    };
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!dragStartRef.current) return;
    const dx = e.clientX - dragStartRef.current.startX;
    const dy = e.clientY - dragStartRef.current.startY;
    setPanOffset({
      x: dragStartRef.current.initialX + dx,
      y: dragStartRef.current.initialY + dy,
    });
  };

  const handleMouseUp = () => {
    if (dragStartRef.current) {
      dragStartRef.current = null;
      setIsInteracting(false);
    }
  };

  const hasTransform = zoomLevel !== 1 || panOffset.x !== 0 || panOffset.y !== 0;

  // If streaming is active and no SVG yet, show clean streaming indicator
  if (isStreaming && !svgContent) {
    return (
      <div className="my-4 rounded-xl border border-blue-500/20 bg-slate-50/80 dark:bg-[#0b0f19]/90 p-5 flex items-center justify-center gap-3 text-xs text-slate-500 dark:text-slate-400 shadow-md">
        <Sparkles className="w-4 h-4 text-blue-500 animate-spin" />
        <span className="font-medium animate-pulse">Streaming SAP architecture diagram...</span>
      </div>
    );
  }

  return (
    <div className="my-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-[#111116] overflow-clip transition-all">
      {/* Header bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-2 border-b border-slate-200 dark:border-slate-800 bg-slate-100/70 dark:bg-[#18181f] rounded-t-xl">
        <div className="flex items-center gap-2">
          <div className="p-1 rounded-md bg-blue-500/10 text-blue-600 dark:text-blue-400">
            <Sparkles className="w-4 h-4" />
          </div>
          <span className="text-xs font-semibold tracking-wide text-slate-800 dark:text-slate-200">
            {title}
          </span>
          <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-600 dark:text-blue-400 font-medium">
            Mermaid
          </span>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-1.5 text-xs">
          {/* Zoom controls (only in diagram mode) */}
          {viewMode === 'diagram' && !renderFailed && (
            <div className="flex items-center gap-1 mr-2 px-1.5 py-0.5 rounded bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
              <button
                type="button"
                onClick={handleZoomOut}
                className="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 transition-colors"
                title="Zoom Out"
              >
                <ZoomOut className="w-3.5 h-3.5" />
              </button>
              <span className="text-[10px] font-mono font-medium text-slate-500 dark:text-slate-400 px-1">
                {Math.round(zoomLevel * 100)}%
              </span>
              <button
                type="button"
                onClick={handleZoomIn}
                className="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 transition-colors"
                title="Zoom In"
              >
                <ZoomIn className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={handleResetZoom}
                className="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-500 dark:text-slate-400 transition-colors"
                title="Reset Zoom"
              >
                <RotateCcw className="w-3 h-3" />
              </button>
            </div>
          )}

          {/* Diagram / Source toggle */}
          <button
            type="button"
            onClick={() => setViewMode(viewMode === 'diagram' ? 'source' : 'diagram')}
            className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-750 transition-colors font-medium shadow-2xs"
          >
            {viewMode === 'diagram' ? (
              <>
                <Code className="w-3.5 h-3.5 text-blue-500" />
                <span>Source</span>
              </>
            ) : (
              <>
                <Eye className="w-3.5 h-3.5 text-blue-500" />
                <span>Diagram</span>
              </>
            )}
          </button>

          {/* Copy Mermaid */}
          <button
            type="button"
            onClick={handleCopyCode}
            className="flex items-center gap-1 px-2 py-1 rounded-md bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-750 transition-colors font-medium shadow-2xs"
            title="Copy Mermaid Code"
          >
            {copied ? (
              <>
                <Check className="w-3.5 h-3.5 text-emerald-500" />
                <span className="text-emerald-500">Copied</span>
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5 text-slate-500" />
                <span>Copy</span>
              </>
            )}
          </button>

          {/* Export Buttons */}
          <button
            type="button"
            onClick={handleExportSvg}
            className="flex items-center gap-1 px-2 py-1 rounded-md bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-750 transition-colors font-medium shadow-2xs"
            title="Export as SVG"
          >
            <Download className="w-3.5 h-3.5 text-slate-500" />
            <span>SVG</span>
          </button>
          <button
            type="button"
            onClick={handleExportPng}
            className="flex items-center gap-1 px-2 py-1 rounded-md bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-750 transition-colors font-medium shadow-2xs"
            title="Export as PNG"
          >
            <Download className="w-3.5 h-3.5 text-slate-500" />
            <span>PNG</span>
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      {viewMode === 'diagram' ? (
        <div className="relative min-h-[220px] p-4 flex flex-col items-center justify-center bg-white/40 dark:bg-slate-950/40 rounded-b-xl">
          {renderFailed ? (
            <div className="w-full max-w-2xl p-4 rounded-xl bg-slate-100/90 dark:bg-[#15171e] border border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-300 text-xs shadow-2xs">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2 font-medium text-slate-700 dark:text-slate-300">
                  <Code className="w-4 h-4 text-slate-500" />
                  <span className="font-semibold text-slate-800 dark:text-slate-200">Diagram could not be rendered</span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={handleCopyCode}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-750 text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-700 font-medium transition-colors shadow-2xs cursor-pointer"
                    title="Copy Diagram Source"
                  >
                    {copied ? (
                      <>
                        <Check className="w-3.5 h-3.5 text-emerald-500" />
                        <span className="text-emerald-500">Copied</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3.5 h-3.5 text-slate-500" />
                        <span>Copy</span>
                      </>
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={() => setViewMode('source')}
                    className="px-2.5 py-1 rounded-md bg-slate-200 hover:bg-slate-300 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 font-medium text-xs transition-colors cursor-pointer"
                  >
                    Edit Source
                  </button>
                </div>
              </div>
              <div className="p-3 rounded-lg bg-slate-950 text-slate-300 font-mono text-[11px] overflow-x-auto max-h-56 border border-slate-800 leading-relaxed">
                <pre>{currentChart}</pre>
              </div>
            </div>
          ) : svgContent ? (
            /* Single scroll container for horizontal diagram overflow; vertical wheel events propagate to chat scroller */
            <div className="w-full overflow-x-auto overflow-y-hidden" style={{ height: 'auto' }}>
              <div
                ref={containerRef}
                className="w-full min-w-full flex justify-center origin-top select-none"
                style={{
                  transform: hasTransform
                    ? `translate3d(${panOffset.x}px, ${panOffset.y}px, 0) scale(${zoomLevel})`
                    : 'none',
                  transformOrigin: 'top center',
                  transition: isInteracting ? 'none' : 'transform 150ms ease-out',
                  willChange: isInteracting ? 'transform' : undefined,
                  cursor: zoomLevel > 1 ? (isInteracting ? 'grabbing' : 'grab') : 'default',
                }}
                onMouseDown={handleMouseDown}
                onMouseMove={handleMouseMove}
                onMouseUp={handleMouseUp}
                onMouseLeave={handleMouseUp}
                dangerouslySetInnerHTML={{ __html: svgContent }}
              />
            </div>
          ) : (
            <div className="flex items-center gap-2 text-xs text-slate-400 animate-pulse">
              <Sparkles className="w-4 h-4 text-blue-500 animate-spin" />
              <span>Rendering SAP architecture diagram...</span>
            </div>
          )}
        </div>
      ) : (
        /* Source Editor Mode */
        <div className="p-4 bg-slate-900 font-mono text-xs text-slate-200 rounded-b-xl">
          <div className="mb-2 flex items-center justify-between text-slate-400 text-[11px]">
            <span>Edit Mermaid chart source:</span>
            <button
              type="button"
              onClick={handleApplyChanges}
              className="px-3 py-1 rounded bg-blue-600 hover:bg-blue-500 text-white font-semibold transition-colors cursor-pointer"
            >
              Update Diagram
            </button>
          </div>
          <textarea
            value={editableChart}
            onChange={(e) => setEditableChart(e.target.value)}
            rows={12}
            className="w-full p-3 rounded-lg bg-slate-950 border border-slate-800 text-slate-200 font-mono text-xs focus:outline-hidden focus:border-blue-500 leading-relaxed resize-y"
            spellCheck={false}
          />
        </div>
      )}
    </div>
  );
};

// React.memo keyed by chart source, isStreaming, and title so parent updates never re-render or re-inject SVG
export const MermaidViewer = React.memo(
  MermaidViewerComponent,
  (prevProps, nextProps) => {
    return (
      prevProps.chart.trim() === nextProps.chart.trim() &&
      prevProps.isStreaming === nextProps.isStreaming &&
      prevProps.title === nextProps.title
    );
  }
);
