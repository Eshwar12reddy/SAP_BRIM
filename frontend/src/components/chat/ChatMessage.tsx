import React, { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  Copy,
  Check,
  RotateCcw,
  Share2,
  Pencil,
  Globe,
  BookOpen,
  Sparkles,
  History,
  ThumbsUp,
  ThumbsDown,
  Volume2,
  VolumeX,
  FileText,
  Image as ImageIcon,
  MessageSquareQuote,
  ChevronDown
} from 'lucide-react';
import type { Message } from '../../types';
import iconOnly from '../../assets/clyptusap-icon.png';
import { CitationModal } from './CitationModal';
import { VisualCard } from './VisualCard';
import { MermaidViewer } from './MermaidViewer';
import { apiSubmitMessageFeedback } from '../../services/api';

const stripAnswerCitations = (content: string): string => {
  if (!content || !content.trim()) return content;
  let answer = content;

  // Drop trailing bibliography and source sections
  const sourceSection = /(?:^|\n)\s{0,3}(?:#{1,6}\s+|\*\*)(?:sources?|references?|citations?)(?:\*\*)?\s*:?\s*(?:\n|$)/im;
  const sectionMatch = sourceSection.exec(answer);
  if (sectionMatch && sectionMatch.index >= 50) {
    answer = answer.slice(0, sectionMatch.index);
  }

  // Remove standalone reference definitions and numeric inline markers
  const cleaned = answer
    .replace(/^\s*\[\d+\]\s*:?\s*\[?https?:\/\/.*$/gim, '')
    .replace(/\[(?:\d+)(?:\s*,\s*\d+)*\]/g, '')
    .replace(/\(Source:\s*[^)]*\)/gi, '')
    .replace(/^\s*[-*_]{3,}\s*$/gm, '')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();

  return cleaned.length > 0 ? cleaned : content;
};

const repairMarkdownFences = (content: string): string => {
  if (!content || !content.trim()) return content;

  let repaired = content;

  // 1. Fix closing code fences that have trailing unverified notes or non-language text attached
  repaired = repaired.replace(
    /^(```+)[ \t]*(\(?(?:unverified|confirm in your system)[^\n]*\)?)/gim,
    '$1\n\n_$2_\n\n'
  );

  repaired = repaired.replace(
    /^(```+)[ \t]+(\([^\n]+\)|_[^\n]+_|[^\w\s\n][^\n]*)/gm,
    '$1\n\n$2\n\n'
  );

  // 2. Prevent unclosed code blocks from swallowing subsequent headings/explanations
  repaired = repaired.replace(
    /(```mermaid[\s\S]*?)(?=\n#{1,6}\s)/gi,
    (match) => {
      const fenceCount = (match.match(/```/g) || []).length;
      if (fenceCount === 1) {
        return `${match.trimEnd()}\n\`\`\`\n\n`;
      }
      return match;
    }
  );

  return repaired;
};

const CodeBlock: React.FC<{ children: React.ReactNode; language?: string }> = ({ children, language }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    let text = '';
    React.Children.forEach(children, (child: any) => {
      if (typeof child === 'string') text += child;
      else if (child?.props?.children) {
        text += typeof child.props.children === 'string'
          ? child.props.children
          : Array.isArray(child.props.children)
            ? child.props.children.join('')
            : String(child.props.children);
      }
    });

    if (text) {
      navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="relative group/code my-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-[#f8fafc] dark:bg-[#111116] overflow-hidden">
      {/* Code header bar */}
      <div className="flex items-center justify-between px-4 py-2 bg-slate-100/80 dark:bg-[#18181f] border-b border-slate-200/80 dark:border-slate-800/80 text-[11px] font-mono text-slate-500 dark:text-slate-400">
        <span className="uppercase tracking-wider font-semibold">{language || 'code'}</span>
        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1.5 px-2 py-1 rounded hover:bg-slate-200/70 dark:hover:bg-slate-700/60 text-slate-600 dark:text-slate-300 transition cursor-pointer"
          title="Copy code"
          aria-label="Copy code"
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5 text-emerald-500" />
              <span className="text-emerald-500 font-sans">Copied!</span>
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5" />
              <span className="font-sans">Copy</span>
            </>
          )}
        </button>
      </div>
      <div className="overflow-x-auto p-4 text-[13.5px] leading-relaxed">
        <pre className="font-mono text-slate-900 dark:text-slate-100 whitespace-pre">
          {children}
        </pre>
      </div>
    </div>
  );
};

interface ChatMessageProps {
  message: Message;
  isStreaming?: boolean;
  streamingStage?: string | null;
  onRetry?: () => void;
  onEdit?: () => void;
  onRegenerate?: () => void;
  onSelectFollowup?: (question: string) => void;
}

export const ChatMessage: React.FC<ChatMessageProps> = ({
  message,
  isStreaming = false,
  streamingStage = null,
  onRetry,
  onEdit,
  onRegenerate,
  onSelectFollowup,
}) => {
  const [copied, setCopied] = useState(false);
  const [isCitationModalOpen, setIsCitationModalOpen] = useState(false);
  const [feedback, setFeedback] = useState<'up' | 'down' | null>(message.feedback || null);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [selectedImage, setSelectedImage] = useState<string | null>(null);

  const isUser = message.role === 'user';
  const rawContent = isUser ? message.content : stripAnswerCitations(message.content);
  const displayContent = repairMarkdownFences(rawContent);

  useEffect(() => {
    setFeedback(message.feedback || null);
  }, [message.feedback]);

  useEffect(() => {
    return () => {
      if (typeof window !== 'undefined' && window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  const handleCopy = () => {
    if (!displayContent) return;
    navigator.clipboard.writeText(displayContent);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleShare = async () => {
    if (!displayContent) return;
    try {
      if (navigator.share) {
        await navigator.share({
          title: isUser ? 'My question' : 'Clyptus.AI SAP Assistant',
          text: displayContent,
        });
      } else {
        await navigator.clipboard.writeText(displayContent);
      }
    } catch {
      // Cancelled
    }
  };

  const handleFeedback = async (rating: 'up' | 'down') => {
    if (isUser || !message.chat_id || !message.id) return;
    const nextRating = feedback === rating ? null : rating;
    setFeedback(nextRating);
    if (nextRating) {
      try {
        await apiSubmitMessageFeedback(message.chat_id, message.id, nextRating);
      } catch (err) {
        console.error('Failed to submit feedback:', err);
      }
    }
  };

  const handleToggleSpeak = () => {
    if (typeof window === 'undefined' || !window.speechSynthesis) return;
    if (isSpeaking) {
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
      return;
    }
    window.speechSynthesis.cancel();
    const plainText = displayContent
      .replace(/```[\s\S]*?```/g, ' Code snippet omitted. ')
      .replace(/`([^`]+)`/g, '$1')
      .replace(/[*#_~]/g, '')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
      .replace(/\n+/g, ' ')
      .trim();

    if (!plainText) return;
    const utterance = new SpeechSynthesisUtterance(plainText);
    utterance.rate = 1.0;
    utterance.pitch = 1.0;
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);
    window.speechSynthesis.speak(utterance);
    setIsSpeaking(true);
  };

  const isInterrupted = message.source_type === 'interrupted' || message.source_type === 'error';
  const hasWebSources = Boolean(message.web_sources && message.web_sources.length > 0);
  const hasCitations = Boolean(message.citations && message.citations.length > 0);
  const isCombinedSource = message.source_type === 'combined' || (hasWebSources && hasCitations);
  const isWebSource = !isCombinedSource && (message.source_type === 'web' || message.source_type === 'web_search' || (hasWebSources && !hasCitations));
  const isKbSource = !isCombinedSource && (message.source_type === 'knowledge_base' || (hasCitations && !hasWebSources));
  const isConversational = message.source_type === 'conversational';
  const isRefusal = message.source_type === 'refusal';

  // ----------------------------------------------------
  // USER MESSAGE: Subtle right-aligned bubble (ChatGPT style)
  // ----------------------------------------------------
  if (isUser) {
    return (
      <div className="w-full flex justify-end my-3 sm:my-4 group">
        <div className="relative max-w-[85%] sm:max-w-[75%] rounded-3xl bg-[#f4f4f4] dark:bg-[#27272a] text-slate-900 dark:text-slate-100 px-5 py-3 text-[16px] leading-[1.7] break-words">
          {/* User attached files / images */}
          {message.attachments && message.attachments.length > 0 && (
            <div className="mb-2.5 flex flex-wrap gap-2">
              {message.attachments.map((att) => {
                const previewSrc = att.preview_url.startsWith('http') || att.preview_url.startsWith('blob:')
                  ? att.preview_url
                  : `http://localhost:8000${att.preview_url}`;
                return (
                  <div
                    key={att.id}
                    className="rounded-xl border border-black/10 dark:border-white/10 overflow-hidden bg-white/70 dark:bg-black/30 p-1.5"
                  >
                    {att.file_type === 'image' ? (
                      <img
                        src={previewSrc}
                        alt={att.filename}
                        onClick={() => setSelectedImage(previewSrc)}
                        className="h-28 w-auto max-w-xs object-cover rounded-lg cursor-pointer hover:opacity-95"
                      />
                    ) : (
                      <div className="flex items-center gap-1.5 px-2 py-1 text-xs">
                        <FileText className="w-4 h-4 text-orange-500" />
                        <span className="truncate max-w-[160px] font-medium">{att.filename}</span>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Text Content */}
          <div className="whitespace-pre-wrap">{displayContent}</div>

          {/* Hover actions: Edit & Copy */}
          <div className="absolute -bottom-6 right-2 flex items-center gap-1 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity">
            {onEdit && (
              <button
                type="button"
                onClick={onEdit}
                className="p-1 rounded text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition cursor-pointer"
                title="Edit message"
                aria-label="Edit message"
              >
                <Pencil className="w-3.5 h-3.5" />
              </button>
            )}
            <button
              type="button"
              onClick={handleCopy}
              className="p-1 rounded text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition cursor-pointer"
              title="Copy message"
              aria-label="Copy message"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
            </button>
          </div>
        </div>

        {/* Lightbox Modal */}
        {selectedImage && (
          <div
            role="dialog"
            aria-modal="true"
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-in fade-in duration-200"
            onClick={() => setSelectedImage(null)}
          >
            <div
              className="relative max-w-5xl max-h-[90vh] bg-slate-900 border border-slate-700 rounded-2xl overflow-hidden shadow-2xl p-2 flex flex-col items-center"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="w-full flex items-center justify-between px-3 py-2 border-b border-slate-800 text-slate-300">
                <span className="text-xs font-semibold tracking-wide flex items-center gap-1.5">
                  <ImageIcon className="w-3.5 h-3.5 text-blue-400" />
                  Attachment Preview
                </span>
                <button
                  type="button"
                  onClick={() => setSelectedImage(null)}
                  className="text-slate-400 hover:text-white px-2 py-1 rounded-lg hover:bg-slate-800 text-xs transition font-bold"
                >
                  ✕ Close
                </button>
              </div>
              <div className="p-2 overflow-auto flex items-center justify-center max-h-[80vh]">
                <img
                  src={selectedImage}
                  alt="Attachment preview"
                  className="max-h-[75vh] max-w-full rounded-lg object-contain shadow-md"
                />
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  // ----------------------------------------------------
  // ASSISTANT MESSAGE: Direct document flow (No outer card, no border, no shadow, no rounded background)
  // ----------------------------------------------------
  return (
    <>
      <div className="group w-full my-5 sm:my-6 text-slate-900 dark:text-slate-100">
        <div className="flex items-start gap-3 sm:gap-4">
          {/* Subtle assistant avatar */}
          <div className="shrink-0 mt-1">
            <div className="w-7 h-7 rounded-full bg-gradient-to-tr from-orange-600 via-orange-500 to-orange-400 p-0.5 flex items-center justify-center text-white shadow-xs">
              <img src={iconOnly} alt="Clyptus.AI" className="w-full h-full object-contain filter drop-shadow-xs" />
            </div>
          </div>

          {/* Main Answer Flow */}
          <div className="flex-1 min-w-0">
            {/* Streaming Thinking Indicator */}
            {isStreaming && !message.content ? (
              <div className="flex items-center gap-2.5 py-1 text-slate-600 dark:text-slate-300 text-sm select-none">
                <span className="font-medium text-orange-500 dark:text-orange-400 animate-pulse">
                  {streamingStage || 'Thinking...'}
                </span>
                <span className="inline-flex items-center gap-1">
                  <span
                    className="w-1.5 h-1.5 rounded-full bg-orange-500 animate-bounce"
                    style={{ animationDuration: '0.9s', animationDelay: '0ms' }}
                  />
                  <span
                    className="w-1.5 h-1.5 rounded-full bg-orange-500 animate-bounce"
                    style={{ animationDuration: '0.9s', animationDelay: '180ms' }}
                  />
                  <span
                    className="w-1.5 h-1.5 rounded-full bg-orange-500 animate-bounce"
                    style={{ animationDuration: '0.9s', animationDelay: '360ms' }}
                  />
                </span>
              </div>
            ) : (
              <div className="text-[16px] leading-[1.7] text-slate-900 dark:text-slate-100 space-y-3">
                {/* Assistant attachments if any */}
                {message.attachments && message.attachments.length > 0 && (
                  <div className="mb-3 flex flex-wrap gap-2.5">
                    {message.attachments.map((att) => {
                      const previewSrc = att.preview_url.startsWith('http')
                        ? att.preview_url
                        : `http://localhost:8000${att.preview_url}`;
                      return (
                        <div
                          key={att.id}
                          className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/60 p-2 shadow-2xs"
                        >
                          {att.file_type === 'image' ? (
                            <img
                              src={previewSrc}
                              alt={att.filename}
                              onClick={() => setSelectedImage(previewSrc)}
                              className="h-32 w-auto max-w-xs object-cover rounded-lg cursor-pointer hover:opacity-95 shadow-xs transition"
                            />
                          ) : (
                            <div className="flex items-center gap-2 px-2 py-1 text-xs font-medium">
                              <FileText className="w-4 h-4 text-orange-500" />
                              <span className="truncate max-w-[200px]">{att.filename}</span>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* Markdown rendering with proper typography and hierarchy */}
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    h1: ({ node, ...props }) => (
                      <h1 className="text-2xl font-bold mt-6 mb-3 text-slate-900 dark:text-slate-100 tracking-tight" {...props} />
                    ),
                    h2: ({ node, ...props }) => (
                      <h2 className="text-xl font-semibold mt-5 mb-2.5 text-slate-900 dark:text-slate-100 tracking-tight" {...props} />
                    ),
                    h3: ({ node, ...props }) => (
                      <h3 className="text-lg font-semibold mt-4 mb-2 text-slate-900 dark:text-slate-100" {...props} />
                    ),
                    h4: ({ node, ...props }) => (
                      <h4 className="text-base font-semibold mt-3 mb-1.5 text-slate-900 dark:text-slate-100" {...props} />
                    ),
                    p: ({ node, ...props }) => (
                      <p className="mb-4 last:mb-0 leading-[1.7]" {...props} />
                    ),
                    blockquote: ({ node, ...props }) => (
                      <blockquote className="border-l-4 border-slate-300 dark:border-slate-700 pl-4 my-4 italic text-slate-600 dark:text-slate-400" {...props} />
                    ),
                    a: ({ node, ...props }) => (
                      <a
                        {...props}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-orange-600 dark:text-orange-400 underline underline-offset-3 hover:text-orange-700 dark:hover:text-orange-300 font-medium transition"
                      />
                    ),
                    table: ({ node, ...props }) => (
                      <div className="overflow-x-auto my-4 rounded-xl border border-slate-200 dark:border-slate-800">
                        <table className="min-w-full divide-y divide-slate-200 dark:divide-slate-800 text-left text-sm" {...props} />
                      </div>
                    ),
                    th: ({ node, ...props }) => (
                      <th className="px-4 py-2.5 bg-slate-50 dark:bg-[#121217] font-semibold text-slate-900 dark:text-slate-100 border-b border-slate-200 dark:border-slate-800 text-xs uppercase tracking-wider" {...props} />
                    ),
                    td: ({ node, ...props }) => (
                      <td className="px-4 py-2.5 border-t border-slate-100 dark:border-slate-800/60 text-slate-700 dark:text-slate-300 leading-normal" {...props} />
                    ),
                    ol: ({ node, ...props }) => (
                      <ol className="list-decimal pl-6 my-3 space-y-1.5 leading-[1.7]" {...props} />
                    ),
                    ul: ({ node, ...props }) => (
                      <ul className="list-disc pl-6 my-3 space-y-1.5 leading-[1.7]" {...props} />
                    ),
                    pre: ({ children }: any) => {
                      return <>{children}</>;
                    },
                    code: ({ node, className, children, ...props }: any) => {
                      const isInline = !className;
                      const codeString = String(children || '').replace(/\n$/, '');
                      const match = /language-(\w+)/.exec(className || '');
                      const lang = match ? match[1] : '';

                      // Intercept Mermaid blocks
                      if (
                        lang === 'mermaid' ||
                        codeString.trim().startsWith('flowchart') ||
                        codeString.trim().startsWith('graph ') ||
                        codeString.trim().startsWith('sequenceDiagram')
                      ) {
                        const headingIndex = codeString.search(/\n#{1,6}\s/);
                        if (headingIndex !== -1) {
                          const chartPart = codeString.slice(0, headingIndex).trim();
                          const explanationPart = codeString.slice(headingIndex).trim();
                          return (
                            <div className="space-y-4 my-4">
                              <MermaidViewer chart={chartPart} isStreaming={isStreaming} />
                              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                {explanationPart}
                              </ReactMarkdown>
                            </div>
                          );
                        }
                        return <MermaidViewer chart={codeString} isStreaming={isStreaming} />;
                      }

                      return isInline ? (
                        <code className="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200 font-mono text-[13.5px] border border-slate-200/60 dark:border-slate-700/60" {...props}>
                          {children}
                        </code>
                      ) : (
                        <CodeBlock language={lang}>
                          <code className={className} {...props}>
                            {children}
                          </code>
                        </CodeBlock>
                      );
                    },
                  }}
                >
                  {displayContent}
                </ReactMarkdown>

                {/* Streaming Cursor */}
                {isStreaming && (
                  <span className="inline-block w-1.5 h-4 ml-0.5 bg-orange-500 animate-pulse align-middle rounded-xs" />
                )}

                {/* Question-driven Visual Illustrations and Diagrams */}
                {message.visuals && message.visuals.length > 0 && (
                  <div className="mt-4 space-y-3">
                    {message.visuals.map((vis, idx) => (
                      <VisualCard key={vis.id || vis.visual_id || idx} visual={vis} />
                    ))}
                  </div>
                )}

                {/* ========================================================
                    Requirement 8: Citations & Source Transparency below the answer as quiet secondary text
                   ======================================================== */}
                {!isStreaming && !isConversational && !isRefusal && (
                  <div className="mt-4 pt-2 flex items-center gap-2 flex-wrap text-xs text-slate-500 dark:text-slate-400">

                    {isCombinedSource ? (
                      <button
                        type="button"
                        onClick={() => setIsCitationModalOpen(true)}
                        className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 transition cursor-pointer"
                        title="Click to view verified web and knowledge base sources"
                      >
                        <Sparkles className="w-3.5 h-3.5 text-emerald-500" />
                        <span>Sources: Knowledge Base + Web Search</span>
                      </button>
                    ) : isWebSource ? (
                      <button
                        type="button"
                        onClick={() => setIsCitationModalOpen(true)}
                        className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 transition cursor-pointer"
                        title="Click to view verified official SAP web sources and links"
                      >
                        <Globe className="w-3.5 h-3.5 text-sky-500" />
                        <span>Sources: Web Search{message.web_sources?.length ? ` (${message.web_sources.length})` : ''}</span>
                      </button>
                    ) : isKbSource ? (
                      <button
                        type="button"
                        onClick={() => setIsCitationModalOpen(true)}
                        className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 transition cursor-pointer"
                        title="Click to view verified SAP documentation and manual citations"
                      >
                        <BookOpen className="w-3.5 h-3.5 text-purple-500" />
                        <span>Sources: Knowledge Base{message.citations?.length ? ` (${message.citations.length})` : ''}</span>
                      </button>
                    ) : null}

                    {message.previous_context_used && (
                      <span
                        className="inline-flex items-center gap-1 text-[11px] text-amber-600 dark:text-amber-400"
                        title="Context retrieved from earlier conversations"
                      >
                        <History className="w-3 h-3 text-amber-500" />
                        <span>Prior context linked</span>
                      </span>
                    )}

                    {(message.evidence_score !== undefined || message.fallback_reason) && (
                      <details className="group/details relative inline-block text-[11px]">
                        <summary className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 cursor-pointer select-none">
                          <span>Evidence: {(message.evidence_score ?? 0).toFixed(2)}</span>
                          <ChevronDown className="w-3 h-3 group-open/details:rotate-180 transition-transform" />
                        </summary>
                        <div className="absolute z-20 bottom-full mb-1 left-0 p-2.5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg shadow-lg text-[11px] text-slate-600 dark:text-slate-300 space-y-1 min-w-[200px]">
                          <div className="flex justify-between gap-4">
                            <span>Confidence:</span>
                            <span className="font-mono font-semibold text-slate-900 dark:text-white">
                              {(message.evidence_score ?? 0).toFixed(2)}
                            </span>
                          </div>
                          {message.fallback_reason && (
                            <div className="text-amber-600 dark:text-amber-400 text-[10px] mt-1 border-t border-slate-200 dark:border-slate-800 pt-1 leading-snug">
                              {message.fallback_reason}
                            </div>
                          )}
                        </div>
                      </details>
                    )}
                  </div>
                )}

                {/* Follow-up question suggestions */}
                {!isUser && !isStreaming && message.follow_up_questions && message.follow_up_questions.length > 0 && (
                  <div className="mt-4 pt-3 border-t border-slate-200/60 dark:border-slate-800/60">
                    <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-500 dark:text-slate-400 mb-2">
                      <MessageSquareQuote className="w-3.5 h-3.5 text-orange-500" />
                      <span>Suggested Follow-Ups:</span>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {message.follow_up_questions.map((fq, idx) => (
                        <button
                          key={idx}
                          type="button"
                          onClick={() => onSelectFollowup?.(fq)}
                          className="text-left text-xs px-3 py-1.5 rounded-full border border-slate-200 dark:border-slate-700 bg-slate-50 hover:bg-slate-100 dark:bg-slate-800/50 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200 transition cursor-pointer font-medium"
                        >
                          {fq}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Action Buttons: Copy, Read aloud, Thumbs up/down, Share, Regenerate */}
            {!isStreaming && message.content && (
              <div className="mt-2.5 flex items-center gap-1 text-slate-400 transition-opacity">
                {/* Copy message text */}
                <button
                  type="button"
                  onClick={handleCopy}
                  className="p-1.5 rounded-md hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition cursor-pointer"
                  title="Copy message"
                  aria-label="Copy message"
                >
                  {copied ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                </button>

                {/* Read aloud (Text-to-Speech) */}
                <button
                  type="button"
                  onClick={handleToggleSpeak}
                  className={`p-1.5 rounded-md transition cursor-pointer ${
                    isSpeaking
                      ? 'text-orange-500 bg-orange-50 dark:bg-orange-950/40'
                      : 'hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800'
                  }`}
                  title={isSpeaking ? 'Stop speaking' : 'Read answer aloud'}
                  aria-label={isSpeaking ? 'Stop speaking' : 'Read answer aloud'}
                >
                  {isSpeaking ? <VolumeX className="w-3.5 h-3.5 text-orange-500 animate-pulse" /> : <Volume2 className="w-3.5 h-3.5" />}
                </button>

                {/* Thumbs Up feedback */}
                <button
                  type="button"
                  onClick={() => handleFeedback('up')}
                  className={`p-1.5 rounded-md transition cursor-pointer ${
                    feedback === 'up'
                      ? 'text-emerald-500 font-semibold'
                      : 'hover:text-emerald-600 dark:hover:text-emerald-400 hover:bg-slate-100 dark:hover:bg-slate-800'
                  }`}
                  title="Good answer"
                  aria-label="Good answer"
                >
                  <ThumbsUp className={`w-3.5 h-3.5 ${feedback === 'up' ? 'fill-emerald-500/20' : ''}`} />
                </button>

                {/* Thumbs Down feedback */}
                <button
                  type="button"
                  onClick={() => handleFeedback('down')}
                  className={`p-1.5 rounded-md transition cursor-pointer ${
                    feedback === 'down'
                      ? 'text-rose-500 font-semibold'
                      : 'hover:text-rose-600 dark:hover:text-rose-400 hover:bg-slate-100 dark:hover:bg-slate-800'
                  }`}
                  title="Poor answer"
                  aria-label="Poor answer"
                >
                  <ThumbsDown className={`w-3.5 h-3.5 ${feedback === 'down' ? 'fill-rose-500/20' : ''}`} />
                </button>

                {/* Share message */}
                <button
                  type="button"
                  onClick={handleShare}
                  className="p-1.5 rounded-md hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition cursor-pointer"
                  title="Share message"
                  aria-label="Share message"
                >
                  <Share2 className="w-3.5 h-3.5" />
                </button>

                {/* Regenerate assistant message */}
                {onRegenerate && (
                  <button
                    type="button"
                    onClick={onRegenerate}
                    className="p-1.5 rounded-md hover:text-orange-500 dark:hover:text-orange-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition cursor-pointer"
                    title="Regenerate response"
                    aria-label="Regenerate response"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            )}

            {/* Interrupted / Error retry banner */}
            {isInterrupted && (
              <div className="mt-3 p-3 rounded-xl bg-amber-50 dark:bg-slate-900/90 border border-amber-300 dark:border-amber-500/30 text-xs text-amber-900 dark:text-slate-300 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-amber-800 dark:text-amber-300">
                  <span>Generation interrupted.</span>
                </div>
                {onRetry && (
                  <button
                    type="button"
                    onClick={onRetry}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-amber-100 dark:bg-amber-500/10 hover:bg-amber-200 dark:hover:bg-amber-500/20 text-amber-800 dark:text-amber-300 border border-amber-300 dark:border-amber-500/30 transition text-xs font-medium cursor-pointer"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                    <span>Retry</span>
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Citation Modal */}
      <CitationModal
        isOpen={isCitationModalOpen}
        onClose={() => setIsCitationModalOpen(false)}
        citations={message.citations}
        webSources={message.web_sources}
      />

      {/* Screenshot / Image Lightbox Modal */}
      {selectedImage && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-in fade-in duration-200"
          onClick={() => setSelectedImage(null)}
        >
          <div
            className="relative max-w-5xl max-h-[90vh] bg-slate-900 border border-slate-700 rounded-2xl overflow-hidden shadow-2xl p-2 flex flex-col items-center"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="w-full flex items-center justify-between px-3 py-2 border-b border-slate-800 text-slate-300">
              <span className="text-xs font-semibold tracking-wide flex items-center gap-1.5">
                <ImageIcon className="w-3.5 h-3.5 text-blue-400" />
                SAP Screen / Architecture Preview
              </span>
              <button
                type="button"
                onClick={() => setSelectedImage(null)}
                className="text-slate-400 hover:text-white px-2 py-1 rounded-lg hover:bg-slate-800 text-xs transition font-bold"
              >
                ✕ Close
              </button>
            </div>
            <div className="p-2 overflow-auto flex items-center justify-center max-h-[80vh]">
              <img
                src={selectedImage}
                alt="Enlarged SAP screenshot preview"
                className="max-h-[75vh] max-w-full rounded-lg object-contain shadow-md"
              />
            </div>
          </div>
        </div>
      )}
    </>
  );
};
