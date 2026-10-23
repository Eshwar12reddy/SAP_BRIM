import React, { useState, useEffect, useRef } from 'react';
import { Lock } from 'lucide-react';
import { useParams, useNavigate } from 'react-router-dom';
import type { Message } from '../types';
import { ChatMessage } from '../components/chat/ChatMessage';
import { ChatInput } from '../components/chat/ChatInput';
import { WelcomeScreen } from '../components/chat/WelcomeScreen';
import { AuthLimitModal } from '../components/chat/AuthLimitModal';
import { RightSideScrollButton } from '../components/chat/RightSideScrollButton';
import { useAuth } from '../context/AuthContext';

import {
  apiCreateChat,
  apiGetMessages,
  apiStreamMessage,
  apiSavePartialMessage,
  type StreamMetadata,
  type StreamStatus,
} from '../services/api';

const GUEST_QUERY_LIMIT = 2;
const GUEST_COUNT_KEY = 'clyptus_trial_query_count';

const SUGGESTION_CHIPS = [
  {
    label: 'SOM Provider Contracts',
    prompt: 'How does provider contract replication work between SAP SOM and CC?',
  },
  {
    label: 'CI Billable Items (BIT)',
    prompt: 'Explain Billable Items (BIT) creation, billing, and invoicing in CI.',
  },
  {
    label: 'FI-CA Account Balance',
    prompt: 'How do I analyze contract account balances and clearing in FPL9?',
  },
];

export const ChatPage: React.FC = () => {
  const { conversationId } = useParams<{ conversationId?: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [messages, setMessages] = useState<Message[]>([]);
  const [editDraft, setEditDraft] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [streamingContent, setStreamingContent] = useState<string | null>(null);
  const [streamingStage, setStreamingStage] = useState<string | null>(null);
  const [streamingMeta, setStreamingMeta] = useState<StreamMetadata | null>(null);
  const [isUserScrolledUp, setIsUserScrolledUp] = useState(false);
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [trialCount, setTrialCount] = useState<number>(() => {
    try {
      return parseInt(localStorage.getItem(GUEST_COUNT_KEY) || '0', 10);
    } catch {
      return 0;
    }
  });

  const isTrialUser = !user || user.isGuest || user.email === 'consultant@clyptus.ai' || user.email === 'consultant@clyptusap.ai';

  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const lastUserPromptRef = useRef<string>('');
  const justCreatedChatIdRef = useRef<string | null>(null);
  const currentStreamingChatIdRef = useRef<string | null>(null);
  const currentChatIdRef = useRef<string | null>(conversationId || null);

  const isAutoScrollingRef = useRef(false);

  const scrollToBottom = (instant = false) => {
    if (!messagesContainerRef.current) return;
    if (instant) {
      if (!isAutoScrollingRef.current) {
        isAutoScrollingRef.current = true;
        requestAnimationFrame(() => {
          if (messagesContainerRef.current) {
            messagesContainerRef.current.scrollTop = messagesContainerRef.current.scrollHeight;
          }
          isAutoScrollingRef.current = false;
        });
      }
    } else {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  };

  // Auto-scroll smoothly without jitter on content updates unless user has scrolled up
  useEffect(() => {
    if (!isUserScrolledUp) {
      scrollToBottom(!!streamingContent);
    }
  }, [messages, streamingContent, streamingStage, isUserScrolledUp]);

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const target = e.currentTarget;
    const distanceFromBottom = target.scrollHeight - target.scrollTop - target.clientHeight;
    // If more than 90px from bottom, pause auto-scroll
    setIsUserScrolledUp(distanceFromBottom > 90);
  };

  // Load messages when conversationId changes
  useEffect(() => {
    currentChatIdRef.current = conversationId || null;
    let isCancelled = false;

    if (conversationId && (justCreatedChatIdRef.current === conversationId || currentStreamingChatIdRef.current === conversationId)) {
      // Don't reset state if this navigation was triggered by creating a chat for the current stream
      justCreatedChatIdRef.current = null;
      return;
    }

    if (isLoading && abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsLoading(false);
    }
    setStreamingContent(null);
    setStreamingStage(null);
    setStreamingMeta(null);
    setIsUserScrolledUp(false);

    if (conversationId) {
      apiGetMessages(conversationId)
        .then((msgs) => {
          if (isCancelled || currentChatIdRef.current !== conversationId) return;
          console.log('[ChatPage] Loaded messages for chat:', conversationId, msgs.length);
          setMessages(msgs);
        })
        .catch((err) => {
          if (isCancelled || currentChatIdRef.current !== conversationId) return;
          console.error('Failed to load messages for chat:', conversationId, err);
          setMessages([]);
        });
    } else {
      setMessages([]);
    }

    return () => {
      isCancelled = true;
    };
  }, [conversationId]);

  // Clean up any ongoing stream if ChatPage unmounts
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
    };
  }, []);

  const handleStopGeneration = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    currentStreamingChatIdRef.current = null;
    setIsLoading(false);

    // Preserve partially generated text in chat history and database
    if (streamingContent !== null) {
      const stoppedContent = streamingContent.trim() ? streamingContent : 'Generation stopped.';
      const stoppedAssistantMsg: Message = {
        id: streamingMeta?.message_id || `stopped-${Date.now()}`,
        chat_id: conversationId || '',
        role: 'assistant',
        content: stoppedContent,
        source_type: 'interrupted',
        grounding_score: streamingMeta?.grounding_score,
        created_at: new Date().toISOString(),
        citations: streamingMeta?.citations || [],
        web_sources: streamingMeta?.web_sources || [],
      };

      setMessages((prev) => [...prev, stoppedAssistantMsg]);

      if (conversationId && stoppedContent.trim()) {
        apiSavePartialMessage(conversationId, stoppedContent).catch(() => {});
      }
    }

    setStreamingContent(null);
    setStreamingStage(null);
    setStreamingMeta(null);
  };

  const handleSendMessage = async (content: string, attachmentIds?: string[], attachedItems?: any[]) => {
    // Check trial limit for free preview users
    if (isTrialUser && trialCount >= GUEST_QUERY_LIMIT) {
      setShowAuthModal(true);
      return;
    }

    if (isTrialUser) {
      const nextCount = trialCount + 1;
      setTrialCount(nextCount);
      localStorage.setItem(GUEST_COUNT_KEY, String(nextCount));
    }

    lastUserPromptRef.current = content;
    let targetChatId = conversationId;

    // If no active chat in route, create one and navigate
    if (!targetChatId) {
      try {
        const title = content.trim().length > 0
          ? (content.length > 35 ? content.slice(0, 35) + '...' : content)
          : (attachedItems && attachedItems.length > 0 ? `Screenshot: ${attachedItems[0].filename}` : 'SAP Troubleshooting');
        const newChat = await apiCreateChat(title);
        targetChatId = newChat.id;
        justCreatedChatIdRef.current = newChat.id;
        navigate(`/app/chat/${newChat.id}`, { replace: true });
      } catch (err) {
        console.error('Could not create initial chat:', err);
        return;
      }
    }

    // Optimistically add user message to UI
    const tempUserMsg: Message = {
      id: `user-${Date.now()}`,
      chat_id: targetChatId,
      role: 'user',
      content,
      created_at: new Date().toISOString(),
      citations: [],
      web_sources: [],
      attachments: attachedItems || [],
    };

    setMessages((prev) => [...prev, tempUserMsg]);
    setIsLoading(true);
    setStreamingContent('');
    setStreamingStage('Thinking...');
    setStreamingMeta(null);
    setIsUserScrolledUp(false);
    currentStreamingChatIdRef.current = targetChatId;

    const controller = new AbortController();
    abortControllerRef.current = controller;

    let accumulatedText = '';
    let streamMetaRef: StreamMetadata = {};

    await apiStreamMessage(
      targetChatId,
      content,
      {
        onStatus: (status: StreamStatus) => {
          if (currentChatIdRef.current !== targetChatId) return;
          setStreamingStage(status.message);
        },
        onMetadata: (meta: StreamMetadata) => {
          if (currentChatIdRef.current !== targetChatId) return;
          streamMetaRef = { ...streamMetaRef, ...meta };
          setStreamingMeta(streamMetaRef);
        },
        onToken: (token: string) => {
          if (currentChatIdRef.current !== targetChatId) return;
          accumulatedText += token;
          setStreamingContent(accumulatedText);
        },
        onDone: (doneMeta: StreamMetadata, finalText?: string) => {
          if (currentChatIdRef.current !== targetChatId) {
            abortControllerRef.current = null;
            currentStreamingChatIdRef.current = null;
            return;
          }
          setIsLoading(false);
          abortControllerRef.current = null;
          currentStreamingChatIdRef.current = null;
          const effectiveMeta = { ...streamMetaRef, ...doneMeta };

          // Determine the final resolved text without ever discarding an existing answer
          const isInsufficientBoilerplate = (text?: string) =>
            text ? text.includes("I couldn't verify a reliable answer") : false;

          let resolvedContent = '';
          if (finalText && finalText.trim().length > 0 && !isInsufficientBoilerplate(finalText)) {
            resolvedContent = finalText;
          } else if (accumulatedText && accumulatedText.trim().length > 0) {
            resolvedContent = accumulatedText;
          } else {
            resolvedContent = finalText || accumulatedText || '';
          }

          console.log('[ChatPage] onDone resolvedContent length:', resolvedContent.length, 'chat:', targetChatId, 'msgId:', effectiveMeta.message_id);

          const finalAssistantMsg: Message = {
            id: effectiveMeta.message_id || `msg-${Date.now()}`,
            chat_id: targetChatId!,
            role: 'assistant',
            content: resolvedContent,
            source_type: effectiveMeta.source_type || 'knowledge_base',
            selected_source: effectiveMeta.selected_source,
            grounding_score: effectiveMeta.grounding_score,
            kb_grounding_score: effectiveMeta.kb_grounding_score,
            web_grounding_score: effectiveMeta.web_grounding_score,
            grounding_status: effectiveMeta.grounding_status,
            grounding_method: effectiveMeta.grounding_method,
            grounding_summary: effectiveMeta.grounding_summary,
            grounding_claims: effectiveMeta.grounding_claims,
            verification_status: effectiveMeta.verification_status,
            internal_evidence_confidence: effectiveMeta.internal_evidence_confidence,
            kb_relevance_score: effectiveMeta.kb_relevance_score,
            kb_threshold: effectiveMeta.kb_threshold,
            fallback_reason: effectiveMeta.fallback_reason,
            web_search_used: effectiveMeta.web_search_used,
            selected_evidence_quality: effectiveMeta.selected_evidence_quality,
            kb_score: effectiveMeta.kb_score,
            web_score: effectiveMeta.web_score,
            winning_score: effectiveMeta.winning_score,
            is_in_rag_pipeline: effectiveMeta.is_in_rag_pipeline,
            external_search_used: effectiveMeta.external_search_used,
            follow_up_questions: effectiveMeta.follow_up_questions || [],
            created_at: new Date().toISOString(),
            citations: effectiveMeta.citations || [],
            web_sources: effectiveMeta.web_sources || [],
          };

          setMessages((prev) => {
            const hasMsg = prev.some((m) => m.id === finalAssistantMsg.id);
            const next = hasMsg
              ? prev.map((m) => (m.id === finalAssistantMsg.id ? finalAssistantMsg : m))
              : [...prev, finalAssistantMsg];
            console.log('[ChatPage] setMessages onDone, total messages:', next.length);
            return next;
          });

          setStreamingContent(null);
          setStreamingStage(null);
          setStreamingMeta(null);
        },
        onError: (err: any) => {
          if (currentChatIdRef.current !== targetChatId) {
            abortControllerRef.current = null;
            currentStreamingChatIdRef.current = null;
            return;
          }
          console.error('[ChatPage] Stream error:', err);
          setIsLoading(false);
          abortControllerRef.current = null;
          currentStreamingChatIdRef.current = null;

          // If content was already streamed, keep the generated text instead of replacing it with an error banner
          const resolvedContent = accumulatedText.trim()
            ? accumulatedText
            : 'Generation interrupted. Please try again.';

          const errorMsg: Message = {
            id: `err-${Date.now()}`,
            chat_id: targetChatId!,
            role: 'assistant',
            content: resolvedContent,
            source_type: accumulatedText.trim() ? (streamMetaRef.source_type || 'knowledge_base') : 'error',
            grounding_score: streamMetaRef.grounding_score,
            created_at: new Date().toISOString(),
            citations: streamMetaRef.citations || [],
            web_sources: streamMetaRef.web_sources || [],
          };

          setMessages((prev) => {
            const next = [...prev, errorMsg];
            console.log('[ChatPage] setMessages onError, total messages:', next.length);
            return next;
          });
          setStreamingContent(null);
          setStreamingStage(null);
          setStreamingMeta(null);
        },
      },
      controller.signal,
      attachmentIds
    );
  };

  // Export conversation transcript when 'export-current-chat' event is triggered from topbar
  useEffect(() => {
    const handleExport = () => {
      if (messages.length === 0) {
        alert('No messages in this chat to export.');
        return;
      }
      const title = conversationId ? `SAP-Chat-${conversationId.slice(0, 8)}` : 'SAP-BRIM-Chat';
      const text = messages
        .map(
          (m) =>
            `### ${m.role === 'user' ? 'User' : 'SAP BRIM Assistant'} (${new Date(m.created_at).toLocaleString()}):\n\n${m.content}\n\n---\n`
        )
        .join('\n');
      const blob = new Blob([`# ${title}\n\n${text}`], { type: 'text/markdown;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${title}.md`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    };

    window.addEventListener('export-current-chat', handleExport);
    return () => window.removeEventListener('export-current-chat', handleExport);
  }, [messages, conversationId]);


  const isChatting = messages.length > 0 || streamingContent !== null || isLoading;

  return (
    <div className={`chat-landing-root ${isChatting ? 'chatting' : ''}`}>
      {/* 1. .top: flex: 1 1 0; min-height: 0; overflow-y: auto. Contains inner wrapper with margin-top: auto */}
      <div
        ref={messagesContainerRef}
        onScroll={handleScroll}
        className="chat-landing-top"
      >
        <div className="chat-landing-top-inner">
          {/* Collapsible greeting heading (grid-template-rows: 1fr -> 0fr) */}
          <div className="chat-landing-greeting-grid">
            <div className="chat-landing-greeting-content">
              <WelcomeScreen />
            </div>
          </div>

          {/* Messages list */}
          <div className="chat-landing-messages max-w-3xl w-full mx-auto px-4 sm:px-6 pb-6" aria-live="polite">
            {messages.map((msg, idx) => {
              const isLast = idx === messages.length - 1;
              return (
                <ChatMessage
                  key={msg.id}
                  message={msg}
                  onEdit={msg.role === 'user' ? () => setEditDraft(msg.content) : undefined}
                  onRetry={
                    isLast && (msg.source_type === 'error' || msg.source_type === 'interrupted')
                      ? () => {
                          const prevUser = [...messages.slice(0, idx)].reverse().find((m) => m.role === 'user');
                          const query = (prevUser && prevUser.content) || lastUserPromptRef.current;
                          if (query) handleSendMessage(query);
                        }
                      : undefined
                  }
                  onRegenerate={
                    isLast && msg.role === 'assistant' && !isLoading
                      ? () => {
                          const prevUser = [...messages.slice(0, idx)].reverse().find((m) => m.role === 'user');
                          const query = prevUser ? prevUser.content : lastUserPromptRef.current;
                          if (query) handleSendMessage(query);
                        }
                      : undefined
                  }
                />
              );
            })}

            {/* In-flight streaming response with ChatGPT thinking animation & streaming cursor */}
            {streamingContent !== null && (
              <ChatMessage
                message={{
                  id: 'streaming-assistant',
                  chat_id: conversationId || '',
                  role: 'assistant',
                  content: streamingContent,
                  source_type: streamingMeta?.source_type,
                  grounding_score: streamingMeta?.grounding_score,
                  kb_grounding_score: streamingMeta?.kb_grounding_score,
                  web_grounding_score: streamingMeta?.web_grounding_score,
                  grounding_status: streamingMeta?.grounding_status,
                  created_at: new Date().toISOString(),
                  citations: streamingMeta?.citations || [],
                  web_sources: streamingMeta?.web_sources || [],
                }}
                isStreaming={true}
                streamingStage={streamingStage}
              />
            )}

            {/* Typing indicator while waiting for response */}
            {isLoading && streamingContent === '' && (
              <div className="flex items-center gap-2 px-4 py-3 max-w-3xl mx-auto text-slate-500 text-sm">
                <span className="w-2 h-2 rounded-full bg-slate-400 dark:bg-slate-600 animate-bounce" />
                <span className="w-2 h-2 rounded-full bg-slate-400 dark:bg-slate-600 animate-bounce [animation-delay:0.2s]" />
                <span className="w-2 h-2 rounded-full bg-slate-400 dark:bg-slate-600 animate-bounce [animation-delay:0.4s]" />
                <span className="text-xs text-slate-400 ml-1">{streamingStage || 'Thinking...'}</span>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        </div>
      </div>

      {/* Trial Preview Status Pill */}
      {isTrialUser && (
        <div className="shrink-0 w-full max-w-3xl mx-auto px-4 pt-1 flex items-center justify-center">
          {trialCount < GUEST_QUERY_LIMIT ? (
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-orange-50 dark:bg-[#0c0c12] border border-orange-200 dark:border-orange-500/25 text-[11px] text-orange-800 dark:text-orange-300 shadow-sm">
              <span className="w-1.5 h-1.5 rounded-full bg-orange-500 animate-pulse" />
              <span>Free Preview: <strong>{trialCount} of {GUEST_QUERY_LIMIT}</strong> questions used</span>
              <button
                type="button"
                onClick={() => navigate('/login?mode=register')}
                className="text-orange-600 dark:text-white hover:text-orange-700 dark:hover:text-orange-200 underline font-semibold ml-1 cursor-pointer"
              >
                Sign up for unlimited
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setShowAuthModal(true)}
              className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-orange-950/60 border border-orange-500/40 text-[11px] text-orange-200 hover:bg-orange-900/50 transition cursor-pointer shadow-md shadow-orange-500/10"
            >
              <Lock size={12} className="text-orange-400" />
              <span>Preview limit reached (2/2) · <strong>Sign in or Sign up to continue</strong></span>
            </button>
          )}
        </div>
      )}

      {/* 2. .dock: flex: none. Contains the input form */}
      <div className="chat-landing-dock">
        <ChatInput
          chatId={conversationId}
          onSendMessage={handleSendMessage}
          onStop={handleStopGeneration}
          isLoading={isLoading}
          draftMessage={editDraft}
          onDraftMessageApplied={() => setEditDraft(null)}
          onEnsureChatId={async () => {
            if (conversationId) return conversationId;
            const newChat = await apiCreateChat('SAP Screenshot Troubleshooting');
            justCreatedChatIdRef.current = newChat.id;
            navigate(`/app/chat/${newChat.id}`, { replace: true });
            return newChat.id;
          }}
        />
      </div>

      {/* 3. .below: flex: 1 1 0; min-height: 0; overflow: hidden. Holds suggestion chips. Inert when chatting */}
      <div
        className="chat-landing-below"
        inert={isChatting ? true : undefined}
      >
        <div className="chat-landing-chips">
          {SUGGESTION_CHIPS.map((chip, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => handleSendMessage(chip.prompt)}
              className="chat-landing-chip"
            >
              {chip.label}
            </button>
          ))}
        </div>
      </div>


      {/* Right Side Scroll Controls */}
      <RightSideScrollButton
        containerRef={messagesContainerRef}
        onScrollToBottom={() => {
          setIsUserScrolledUp(false);
          scrollToBottom(false);
        }}
      />

      <AuthLimitModal
        isOpen={showAuthModal}
        onClose={() => setShowAuthModal(false)}
        questionCount={trialCount}
      />
    </div>
  );
};

