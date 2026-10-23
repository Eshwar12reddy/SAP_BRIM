import React, { useState, useMemo } from 'react';
import {
  Maximize2,
  Minimize2,
  Copy,
  Check,
  Download,
  ZoomIn,
  ZoomOut,
  Code,
  Eye,
  AlertTriangle,
  Monitor,
} from 'lucide-react';

interface SapGuiSvgViewerProps {
  rawContent: string;
  title?: string;
  isStreaming?: boolean;
}

/**
 * Strips potentially dangerous tags/attributes from raw SVG string.
 */
function sanitizeSvg(svgStr: string): string {
  if (!svgStr) return '';
  return svgStr
    .replace(/<script[\s\S]*?>[\s\S]*?<\/script>/gi, '')
    .replace(/\son\w+="[^"]*"/gi, '')
    .replace(/\son\w+='[^']*'/gi, '')
    .replace(/\s(href|xlink:href)=["']javascript:[^"']*["']/gi, '');
}

/**
 * Generates an SVG string from JSON if the assistant emitted a JSON contract.
 */
function jsonToSapGuiSvg(jsonStr: string): string | null {
  try {
    const data = JSON.parse(jsonStr);
    const stepNum = data.step ?? 1;
    const tcode = data.tcode || 'FKKBIX_BIT_DISPLAY';
    const screen = data.screen || data.screen_name || 'Display Billable Items';
    const isVerification = Boolean(data.is_verification || String(stepNum).toLowerCase() === 'verification');
    const fields = Array.isArray(data.fields) ? data.fields : [];
    const highlight = (data.highlight_field || '').toLowerCase();
    const callouts = Array.isArray(data.callouts) ? data.callouts : [];

    const width = 680;
    const height = 340;
    const titleBar = isVerification ? `Verification · ${tcode} · ${screen}` : `Step ${stepNum} · ${tcode} · ${screen}`;
    const ringColor = isVerification ? '#10B981' : '#EF4444';

    let fieldsSvg = '';
    const formX = 24;
    const formY = 120;
    const rowH = 28;
    const labelW = 170;
    const inputW = 250;

    fields.slice(0, 5).forEach((f: any, idx: number) => {
      const label = Array.isArray(f) ? f[0] : f.label || `Field ${idx + 1}`;
      const val = Array.isArray(f) ? f[1] : f.value || 'Sample (Example)';
      const curY = formY + idx * rowH;
      const isTarget = highlight && (label.toLowerCase().includes(highlight) || String(val).toLowerCase().includes(highlight));

      fieldsSvg += `
        <text x="${formX}" y="${curY + 16}" fill="#94A3B8" font-family="system-ui, sans-serif" font-size="11">${label}</text>
        <rect x="${formX + labelW}" y="${curY}" width="${inputW}" height="22" rx="3" fill="#0F172A" stroke="${isTarget ? ringColor : '#334155'}" stroke-width="${isTarget ? 2.5 : 1}"/>
        <text x="${formX + labelW + 8}" y="${curY + 15}" fill="#F8FAFC" font-family="monospace" font-size="10.5">${val}</text>
      `;

      if (isTarget) {
        fieldsSvg += `
          <rect x="${formX + labelW - 4}" y="${curY - 4}" width="${inputW + 8}" height="30" rx="5" fill="none" stroke="${ringColor}" stroke-width="2" stroke-dasharray="4,2"/>
        `;
      }
    });

    let calloutSvg = '';
    const calloutX = formX + labelW + inputW + 30;
    const calloutY = formY;
    calloutSvg += `<text x="${calloutX}" y="${calloutY + 10}" fill="#F59E0B" font-family="system-ui, sans-serif" font-size="11" font-weight="700">ACTION CALLOUTS:</text>`;

    callouts.slice(0, 3).forEach((c: any, cIdx: number) => {
      const cNum = Array.isArray(c) ? c[0] : c.number || cIdx + 1;
      const cText = Array.isArray(c) ? c[1] : c.text || 'Inspect field';
      const shortText = String(cText).split(' ').slice(0, 8).join(' ');
      const cRowY = calloutY + 24 + cIdx * 36;
      calloutSvg += `
        <circle cx="${calloutX + 10}" cy="${cRowY + 8}" r="9" fill="#F59E0B"/>
        <text x="${calloutX + 10}" y="${cRowY + 12}" fill="#0B0F19" font-family="system-ui, sans-serif" font-size="10.5" font-weight="900" text-anchor="middle">${cNum}</text>
        <text x="${calloutX + 26}" y="${cRowY + 12}" fill="#F8FAFC" font-family="system-ui, sans-serif" font-size="10.5" font-weight="500">${shortText}</text>
      `;
    });

    return `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="100%" height="100%">
        <rect width="${width}" height="${height}" rx="10" fill="#0B0F19" stroke="#283553" stroke-width="1.5"/>
        <rect width="${width}" height="32" rx="10" fill="#1E293B"/>
        <rect y="22" width="${width}" height="10" fill="#1E293B"/>
        <circle cx="20" cy="16" r="4.5" fill="#EF4444"/>
        <circle cx="34" cy="16" r="4.5" fill="#F59E0B"/>
        <circle cx="48" cy="16" r="4.5" fill="#10B981"/>
        <text x="68" y="21" fill="#F8FAFC" font-family="system-ui, sans-serif" font-size="11.5" font-weight="700">${titleBar}</text>
        <rect y="32" width="${width}" height="28" fill="#151D30" stroke="#283553" stroke-width="1"/>
        <text x="20" y="50" fill="#94A3B8" font-family="system-ui, sans-serif" font-size="10.5">Menu   Edit   Goto   Extras   Environment   System   Help</text>
        <rect x="${width - 190}" y="36" width="140" height="20" rx="3" fill="#0F172A" stroke="#334155" stroke-width="1"/>
        <text x="${width - 182}" y="50" fill="#F8FAFC" font-family="monospace" font-size="10.5">/n${tcode}</text>
        <rect x="${width - 44}" y="36" width="24" height="20" rx="3" fill="#0A6ED1"/>
        <text x="${width - 32}" y="50" fill="#FFFFFF" font-family="system-ui, sans-serif" font-size="11" font-weight="bold" text-anchor="middle">✓</text>
        <text x="20" y="82" fill="#64748B" font-family="system-ui, sans-serif" font-size="10" font-weight="600">PROGRAM: SAPL${tcode.slice(0, 8)} · SCREEN: 1000</text>
        <text x="20" y="100" fill="#F8FAFC" font-family="system-ui, sans-serif" font-size="14" font-weight="700">${screen}</text>
        <line x1="20" y1="108" x2="${width - 20}" y2="108" stroke="#283553" stroke-width="1"/>
        ${fieldsSvg}
        ${calloutSvg}
        <rect y="${height - 32}" width="${width}" height="32" rx="10" fill="#1E293B"/>
        <rect y="${height - 32}" width="${width}" height="10" fill="#1E293B"/>
        <text x="20" y="${height - 14}" fill="#94A3B8" font-family="system-ui, sans-serif" font-size="10">System: S4H · Client: 100 · User: CONSULTANT · Mode: READ-ONLY DIAGNOSTIC</text>
        <text x="${width - 20}" y="${height - 14}" fill="#64748B" font-family="system-ui, sans-serif" font-size="9.5" text-anchor="end">Illustrative mockup · Not an actual system screenshot</text>
      </svg>
    `;
  } catch {
    return null;
  }
}

export const SapGuiSvgViewer: React.FC<SapGuiSvgViewerProps> = ({
  rawContent,
  title,
  isStreaming = false,
}) => {
  const [viewMode, setViewMode] = useState<'image' | 'code'>('image');
  const [zoomLevel, setZoomLevel] = useState<number>(1);
  const [isLightboxOpen, setIsLightboxOpen] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);

  // Extract clean SVG content
  const cleanSvg = useMemo(() => {
    const trimmed = (rawContent || '').trim();
    if (!trimmed) return '';

    // If JSON format
    if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
      const generated = jsonToSapGuiSvg(trimmed);
      if (generated) return sanitizeSvg(generated);
    }

    // If SVG XML format
    const svgMatch = trimmed.match(/<svg[\s\S]*?<\/svg>/i);
    if (svgMatch) {
      return sanitizeSvg(svgMatch[0]);
    }

    // If string begins with <svg but is not closed yet (streaming)
    if (trimmed.startsWith('<svg') && !trimmed.includes('</svg>')) {
      return '';
    }

    return '';
  }, [rawContent]);

  // Extract title bar text from SVG if available
  const detectedTitle = useMemo(() => {
    if (title) return title;
    if (!cleanSvg) return 'SAP GUI Mockup';
    const match = cleanSvg.match(/(Step\s*\d+\s*·\s*[^<]+|Verification\s*·\s*[^<]+|SAP BRIM[^<]+)/i);
    if (match) {
      return match[1].replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').trim();
    }
    return 'SAP GUI Screen Mockup';
  }, [title, cleanSvg]);

  const handleCopy = () => {
    if (!cleanSvg && !rawContent) return;
    navigator.clipboard.writeText(cleanSvg || rawContent);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    if (!cleanSvg) return;
    const blob = new Blob([cleanSvg], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${detectedTitle.replace(/[^a-zA-Z0-9_-]/g, '_')}.svg`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Streaming placeholder
  if (isStreaming && !cleanSvg) {
    return (
      <div className="my-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/60 p-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-orange-500/10 dark:bg-orange-400/10 flex items-center justify-center text-orange-500">
            <Monitor className="w-4 h-4 animate-pulse" />
          </div>
          <div>
            <div className="text-sm font-semibold text-slate-800 dark:text-slate-200">
              Generating SAP GUI Mockup...
            </div>
            <div className="text-xs text-slate-500 dark:text-slate-400">
              Preparing visual step diagram and transaction screen
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Failed render fallback
  if (!cleanSvg) {
    return (
      <div className="my-4 rounded-xl border border-amber-300 dark:border-amber-700/60 bg-amber-50/60 dark:bg-amber-950/20 p-4">
        <div className="flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <h4 className="text-sm font-semibold text-amber-900 dark:text-amber-200">
              SAP GUI Visual Mockup Unavailable
            </h4>
            <p className="text-xs text-amber-700 dark:text-amber-400 mt-0.5">
              The visual mockup could not be rendered as an SVG image. You can inspect the raw specification below:
            </p>
            <div className="mt-2.5">
              <button
                type="button"
                onClick={() => setViewMode(viewMode === 'code' ? 'image' : 'code')}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-md bg-amber-200/80 dark:bg-amber-800/50 text-amber-900 dark:text-amber-100 hover:bg-amber-300 transition"
              >
                <Code className="w-3.5 h-3.5" />
                {viewMode === 'code' ? 'Hide raw specification' : 'View raw specification'}
              </button>
            </div>
            {viewMode === 'code' && (
              <pre className="mt-2.5 p-3 rounded-lg bg-slate-900 text-slate-200 text-xs font-mono overflow-x-auto max-h-60">
                {rawContent}
              </pre>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="my-5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0f172a] shadow-xs overflow-hidden transition-all duration-200">
      {/* Header Bar */}
      <div className="flex items-center justify-between px-3.5 py-2.5 bg-slate-50 dark:bg-[#151d30] border-b border-slate-200 dark:border-slate-800">
        <div className="flex items-center gap-2 min-w-0 pr-2">
          <Monitor className="w-4 h-4 text-orange-600 dark:text-orange-400 shrink-0" />
          <span className="text-xs font-semibold text-slate-800 dark:text-slate-200 truncate">
            {detectedTitle}
          </span>
          <span className="hidden sm:inline-block px-1.5 py-0.5 text-[10px] font-medium rounded bg-slate-200 dark:bg-slate-800 text-slate-600 dark:text-slate-400">
            SAP GUI Visual
          </span>
        </div>

        {/* Toolbar Controls */}
        <div className="flex items-center gap-1 shrink-0">
          <button
            type="button"
            title={viewMode === 'image' ? 'View SVG Source' : 'View Visual Screen'}
            onClick={() => setViewMode(viewMode === 'image' ? 'code' : 'image')}
            className="p-1.5 rounded-lg text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-200/60 dark:hover:bg-slate-800 transition"
          >
            {viewMode === 'image' ? <Code className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
          </button>

          {viewMode === 'image' && (
            <>
              <button
                type="button"
                title="Zoom Out"
                disabled={zoomLevel <= 0.75}
                onClick={() => setZoomLevel((prev) => Math.max(0.75, prev - 0.25))}
                className="p-1.5 rounded-lg text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-200/60 dark:hover:bg-slate-800 disabled:opacity-30 transition"
              >
                <ZoomOut className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                title="Reset Zoom"
                onClick={() => setZoomLevel(1)}
                className="p-1.5 rounded-lg text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-200/60 dark:hover:bg-slate-800 transition text-[11px] font-mono"
              >
                {Math.round(zoomLevel * 100)}%
              </button>
              <button
                type="button"
                title="Zoom In"
                disabled={zoomLevel >= 2.0}
                onClick={() => setZoomLevel((prev) => Math.min(2.0, prev + 0.25))}
                className="p-1.5 rounded-lg text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-200/60 dark:hover:bg-slate-800 disabled:opacity-30 transition"
              >
                <ZoomIn className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                title="Open Fullscreen Lightbox"
                onClick={() => setIsLightboxOpen(true)}
                className="p-1.5 rounded-lg text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-200/60 dark:hover:bg-slate-800 transition"
              >
                <Maximize2 className="w-3.5 h-3.5" />
              </button>
            </>
          )}

          <button
            type="button"
            title="Download SVG"
            onClick={handleDownload}
            className="p-1.5 rounded-lg text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-200/60 dark:hover:bg-slate-800 transition"
          >
            <Download className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            title={copied ? 'Copied!' : 'Copy SVG'}
            onClick={handleCopy}
            className="p-1.5 rounded-lg text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-200/60 dark:hover:bg-slate-800 transition"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* Main View Area */}
      {viewMode === 'image' ? (
        <div className="relative overflow-auto p-3 sm:p-5 flex items-center justify-center bg-slate-950/90 min-h-[180px]">
          <div
            style={{
              transform: `scale(${zoomLevel})`,
              transformOrigin: 'top center',
              transition: 'transform 0.15s ease-out',
              maxWidth: '100%',
              width: '100%',
            }}
            className="flex items-center justify-center"
            dangerouslySetInnerHTML={{ __html: cleanSvg }}
          />
        </div>
      ) : (
        <pre className="p-4 bg-slate-950 text-slate-200 text-xs font-mono overflow-x-auto max-h-96">
          {cleanSvg}
        </pre>
      )}

      {/* Lightbox Modal */}
      {isLightboxOpen && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 bg-black/85 backdrop-blur-xs flex flex-col p-4 sm:p-8 animate-in fade-in duration-150"
          onClick={() => setIsLightboxOpen(false)}
        >
          <div className="flex items-center justify-between pb-3 text-white">
            <div className="flex items-center gap-2">
              <Monitor className="w-5 h-5 text-orange-400" />
              <span className="font-semibold text-sm sm:text-base">{detectedTitle}</span>
            </div>
            <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
              <button
                type="button"
                onClick={handleDownload}
                className="px-3 py-1.5 rounded-lg bg-slate-800 text-white hover:bg-slate-700 text-xs flex items-center gap-1.5"
              >
                <Download className="w-3.5 h-3.5" /> Download
              </button>
              <button
                type="button"
                onClick={() => setIsLightboxOpen(false)}
                className="p-1.5 rounded-lg bg-slate-800 text-white hover:bg-slate-700"
              >
                <Minimize2 className="w-4 h-4" />
              </button>
            </div>
          </div>
          <div
            className="flex-1 overflow-auto flex items-center justify-center p-2"
            onClick={(e) => e.stopPropagation()}
          >
            <div
              className="w-full max-w-4xl max-h-full"
              dangerouslySetInnerHTML={{ __html: cleanSvg }}
            />
          </div>
        </div>
      )}
    </div>
  );
};
