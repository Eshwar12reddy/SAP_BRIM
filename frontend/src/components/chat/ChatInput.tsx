import React, { useState, useRef, useEffect, useCallback } from 'react';
import { ArrowUp, Mic, MicOff, Square, Paperclip, FileText, X, Loader2, UploadCloud } from 'lucide-react';
import { apiUploadChatAttachment } from '../../services/api';
import type { AttachmentItem } from '../../types';

interface ChatInputProps {
  chatId?: string | null;
  onSendMessage: (message: string, attachmentIds?: string[], attachedItems?: AttachmentItem[]) => void;
  onStop?: () => void;
  isLoading: boolean;
  draftMessage?: string | null;
  onDraftMessageApplied?: () => void;
  onEnsureChatId?: () => Promise<string>;
}

export interface AttachedFile {
  id?: string;
  name: string;
  sizeBytes: number;
  content: string;
  isUploading: boolean;
  isImage?: boolean;
  previewUrl?: string;
  file?: File;
  attachmentItem?: AttachmentItem;
}

const MAX_IMAGE_MB = 5;
const MAX_IMAGES = 3;
const ALLOWED_IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/jpg', 'image/webp'];
const ALLOWED_EXTS = ['.png', '.jpg', '.jpeg', '.webp'];

const isSupportedImage = (file: File): boolean => {
  if (ALLOWED_IMAGE_TYPES.includes(file.type.toLowerCase())) return true;
  const name = file.name.toLowerCase();
  return ALLOWED_EXTS.some((ext) => name.endsWith(ext));
};

async function downscaleImage(file: File, maxEdge = 1600): Promise<File> {
  if (!file.type.startsWith('image/')) return file;

  return new Promise((resolve) => {
    const img = new Image();
    const objectUrl = URL.createObjectURL(file);
    img.onload = () => {
      URL.revokeObjectURL(objectUrl);
      let { width, height } = img;
      if (width <= maxEdge && height <= maxEdge) {
        resolve(file);
        return;
      }
      if (width > height) {
        height = Math.round((height * maxEdge) / width);
        width = maxEdge;
      } else {
        width = Math.round((width * maxEdge) / height);
        height = maxEdge;
      }
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        resolve(file);
        return;
      }
      ctx.drawImage(img, 0, 0, width, height);
      const outType = file.type === 'image/png' ? 'image/png' : (file.type === 'image/webp' ? 'image/webp' : 'image/jpeg');
      canvas.toBlob(
        (blob) => {
          if (!blob) {
            resolve(file);
            return;
          }
          const resizedFile = new File([blob], file.name, { type: outType, lastModified: Date.now() });
          resolve(resizedFile);
        },
        outType,
        0.90
      );
    };
    img.onerror = () => {
      URL.revokeObjectURL(objectUrl);
      resolve(file);
    };
    img.src = objectUrl;
  });
}

// Extend the Window interface for SpeechRecognition browser API
declare global {
  interface Window {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    SpeechRecognition: any;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    webkitSpeechRecognition: any;
  }
}

export const ChatInput: React.FC<ChatInputProps> = ({
  chatId,
  onSendMessage,
  onStop,
  isLoading,
  draftMessage,
  onDraftMessageApplied,
  onEnsureChatId,
}) => {
  const [input, setInput] = useState('');
  const [attachments, setAttachments] = useState<AttachedFile[]>([]);
  const [isDraggingOver, setIsDraggingOver] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [voiceSupported, setVoiceSupported] = useState(false);
  const [errorToast, setErrorToast] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const recognitionRef = useRef<any>(null);
  const interimRef = useRef('');

  useEffect(() => {
    if (draftMessage == null) return;
    setInput(draftMessage);
    textareaRef.current?.focus();
    onDraftMessageApplied?.();
  }, [draftMessage, onDraftMessageApplied]);

  // Detect browser support for SpeechRecognition
  useEffect(() => {
    const SpeechRecognitionAPI = window.SpeechRecognition || window.webkitSpeechRecognition;
    setVoiceSupported(!!SpeechRecognitionAPI);
  }, []);

  // Auto-resize textarea up to 200px
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  }, [input]);

  const stopListening = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      recognitionRef.current = null;
    }
    interimRef.current = '';
    setIsListening(false);
  }, []);

  const startListening = useCallback(() => {
    setErrorToast(null);
    const SpeechRecognitionAPI = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognitionAPI) return;

    const recognition = new SpeechRecognitionAPI();
    recognition.lang = 'en-US';
    recognition.interimResults = true;
    recognition.continuous = true;
    recognition.maxAlternatives = 1;

    recognitionRef.current = recognition;

    recognition.onstart = () => {
      setIsListening(true);
    };

    recognition.onresult = (event: any) => {
      let finalTranscript = '';
      let interimTranscript = '';

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalTranscript += transcript;
        } else {
          interimTranscript += transcript;
        }
      }

      if (finalTranscript) {
        setInput((prev) => {
          const base = prev.endsWith(' ') || prev === '' ? prev : prev + ' ';
          return (base + finalTranscript).trimStart();
        });
      }
      interimRef.current = interimTranscript;
    };

    recognition.onerror = (event: any) => {
      if (event.error === 'not-allowed') {
        setErrorToast('Microphone access denied. Please allow microphone permissions.');
      } else if (event.error !== 'aborted') {
        setErrorToast('Voice recognition error. Please try again.');
      }
      stopListening();
    };

    recognition.onend = () => {
      setIsListening(false);
      recognitionRef.current = null;
      interimRef.current = '';
    };

    recognition.start();
  }, [stopListening]);

  const toggleVoice = () => {
    if (isListening) {
      stopListening();
    } else {
      startListening();
    }
  };

  const uploadSingleFile = async (fileToUpload: File, tempKey: string, activeChatId: string) => {
    try {
      const res = await apiUploadChatAttachment(activeChatId, fileToUpload);
      setAttachments((prev) =>
        prev.map((item) => {
          if (item.name === tempKey) {
            const previewUrl = res.preview_url
              ? res.preview_url.startsWith('http')
                ? res.preview_url
                : `http://localhost:8000${res.preview_url}`
              : item.previewUrl;
            return {
              ...item,
              id: res.id || res.attachment_id,
              name: res.filename,
              sizeBytes: res.size_bytes,
              content: res.extracted_text,
              isUploading: false,
              previewUrl,
              attachmentItem: {
                id: res.id || res.attachment_id,
                filename: res.filename,
                file_type: res.file_type || 'image',
                mime_type: res.mime_type || fileToUpload.type,
                preview_url: previewUrl || '',
                size_bytes: res.size_bytes,
                extracted_text: res.extracted_text,
                vision_metadata: res.vision_metadata,
              },
            };
          }
          return item;
        })
      );
    } catch (err: any) {
      setErrorToast(err.message || `Failed to process ${fileToUpload.name}.`);
      setAttachments((prev) => prev.filter((item) => item.name !== tempKey));
    }
  };

  const processIncomingFiles = async (files: File[]) => {
    if (!files || files.length === 0) return;

    // Check count limit
    if (attachments.length + files.length > MAX_IMAGES) {
      setErrorToast(`Maximum ${MAX_IMAGES} images allowed per message.`);
      return;
    }

    // Determine target chat ID
    let activeChatId = chatId;
    if (!activeChatId && onEnsureChatId) {
      try {
        activeChatId = await onEnsureChatId();
      } catch (err) {
        console.warn('Could not preemptively create chat:', err);
      }
    }

    for (const rawFile of files) {
      const isImg = isSupportedImage(rawFile);
      if (!isImg && !rawFile.type.startsWith('text/') && !/\.(pdf|txt|md|log|json|csv|xml|abap|sql)$/i.test(rawFile.name)) {
        setErrorToast(`Unsupported file format for ${rawFile.name}. Please upload PNG, JPG, or WEBP.`);
        continue;
      }

      // Check raw file size limit (before downscale fallback)
      if (rawFile.size > 20 * 1024 * 1024) {
        setErrorToast(`${rawFile.name} exceeds upload size limit.`);
        continue;
      }

      let finalFile = rawFile;
      if (isImg) {
        // Downscale image to max 1600px edge
        finalFile = await downscaleImage(rawFile, 1600);
        if (finalFile.size > MAX_IMAGE_MB * 1024 * 1024) {
          setErrorToast(`${rawFile.name} exceeds ${MAX_IMAGE_MB} MB limit.`);
          continue;
        }
      }

      const localPreviewUrl = isImg ? URL.createObjectURL(finalFile) : undefined;

      const newAttachment: AttachedFile = {
        name: finalFile.name,
        sizeBytes: finalFile.size,
        content: '',
        isUploading: Boolean(activeChatId),
        isImage: isImg,
        previewUrl: localPreviewUrl,
        file: finalFile,
      };

      setAttachments((prev) => [...prev, newAttachment]);

      if (activeChatId) {
        uploadSingleFile(finalFile, finalFile.name, activeChatId);
      }
    }
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const fileList = e.target.files;
    if (!fileList || fileList.length === 0) return;
    const filesArray = Array.from(fileList);
    e.target.value = '';
    await processIncomingFiles(filesArray);
  };

  // Clipboard paste listener to intercept screenshot pastes (Ctrl+V)
  const handlePaste = async (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const items = e.clipboardData?.items;
    if (!items) return;

    const pastedFiles: File[] = [];
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.indexOf('image') !== -1) {
        const file = items[i].getAsFile();
        if (file) {
          const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
          const ext = file.type === 'image/jpeg' ? 'jpg' : file.type === 'image/webp' ? 'webp' : 'png';
          const namedFile = new File([file], `sap_screenshot_${timestamp}.${ext}`, { type: file.type || 'image/png' });
          pastedFiles.push(namedFile);
        }
      }
    }

    if (pastedFiles.length > 0) {
      e.preventDefault();
      await processIncomingFiles(pastedFiles);
    }
  };

  // Drag and drop handlers
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!isDraggingOver) setIsDraggingOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingOver(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingOver(false);

    const droppedFiles = e.dataTransfer.files;
    if (droppedFiles && droppedFiles.length > 0) {
      await processIncomingFiles(Array.from(droppedFiles));
    }
  };

  const removeAttachment = (indexToRemove: number) => {
    setAttachments((prev) => {
      const removed = prev[indexToRemove];
      if (removed?.previewUrl && removed.previewUrl.startsWith('blob:')) {
        URL.revokeObjectURL(removed.previewUrl);
      }
      return prev.filter((_, idx) => idx !== indexToRemove);
    });
  };

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const hasAttachments = attachments.length > 0;
    const hasText = Boolean(input.trim());

    if ((!hasText && !hasAttachments) || isLoading) return;
    if (attachments.some((a) => a.isUploading)) return;
    if (isListening) stopListening();

    let targetChatId = chatId;
    if (!targetChatId && onEnsureChatId && hasAttachments) {
      try {
        targetChatId = await onEnsureChatId();
      } catch (err) {
        console.error('Failed to prepare chat:', err);
      }
    }

    // If any attachment is missing an uploaded ID and we now have a chat ID, upload it
    const finalAttachments = [...attachments];
    if (targetChatId) {
      for (let i = 0; i < finalAttachments.length; i++) {
        const att = finalAttachments[i];
        if (!att.id && att.file) {
          try {
            const res = await apiUploadChatAttachment(targetChatId, att.file);
            finalAttachments[i] = {
              ...att,
              id: res.id || res.attachment_id,
              attachmentItem: {
                id: res.id || res.attachment_id,
                filename: res.filename,
                file_type: res.file_type || 'image',
                mime_type: res.mime_type || att.file.type,
                preview_url: res.preview_url ? (res.preview_url.startsWith('http') ? res.preview_url : `http://localhost:8000${res.preview_url}`) : att.previewUrl || '',
                size_bytes: res.size_bytes,
                extracted_text: res.extracted_text,
                vision_metadata: res.vision_metadata,
              },
            };
          } catch (uploadErr) {
            console.error('Upload failed for pending file:', uploadErr);
          }
        }
      }
    }

    const attachmentIds = finalAttachments.map((a) => a.id).filter(Boolean) as string[];
    const attachedItems: AttachmentItem[] = finalAttachments.map((a) => {
      if (a.attachmentItem) return a.attachmentItem;
      return {
        id: a.id || `att-${Date.now()}`,
        filename: a.name,
        file_type: a.isImage ? 'image' : 'document',
        mime_type: a.isImage ? 'image/png' : 'application/octet-stream',
        preview_url: a.previewUrl || '',
        size_bytes: a.sizeBytes,
      };
    });

    const finalMessage = input.trim();
    onSendMessage(finalMessage, attachmentIds.length > 0 ? attachmentIds : undefined, attachedItems.length > 0 ? attachedItems : undefined);

    setInput('');
    setAttachments([]);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      if (e.nativeEvent.isComposing) return;
      e.preventDefault();
      handleSubmit();
    }
  };

  const isUploadingAny = attachments.some((a) => a.isUploading);
  const canSubmit = (Boolean(input.trim()) || attachments.length > 0) && !isUploadingAny && !isLoading;

  return (
    <div
      className="w-full max-w-3xl mx-auto px-4 pb-3 pt-1"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Upload or voice error toast */}
      {errorToast && (
        <div className="mb-2 px-3 py-1.5 rounded-xl bg-rose-950/70 border border-rose-700/50 text-xs text-rose-200 flex items-center justify-between gap-2 shadow-xs">
          <span>{errorToast}</span>
          <button
            onClick={() => setErrorToast(null)}
            className="text-rose-400 hover:text-rose-100 transition font-bold shrink-0 cursor-pointer"
          >
            ✕
          </button>
        </div>
      )}

      <form
        onSubmit={handleSubmit}
        className={`relative flex flex-col bg-white dark:bg-[#18181b] border rounded-[26px] shadow-sm transition-all duration-200 ${
          isDraggingOver
            ? 'border-orange-500/80 bg-orange-500/5 ring-2 ring-orange-500/20'
            : isListening
            ? 'border-rose-500/70 ring-2 ring-rose-500/25'
            : 'border-slate-200 dark:border-[#27272a] hover:border-slate-300 dark:hover:border-[#3f3f46] focus-within:border-slate-400 dark:focus-within:border-slate-500 focus-within:shadow-md'
        }`}
      >
        {/* Drag and drop overlay hint */}
        {isDraggingOver && (
          <div className="absolute inset-0 z-20 rounded-[26px] bg-orange-500/10 backdrop-blur-xs flex items-center justify-center pointer-events-none">
            <div className="flex items-center gap-2 text-sm font-semibold text-orange-600 dark:text-orange-400 bg-white/90 dark:bg-black/80 px-4 py-2 rounded-xl shadow-sm border border-orange-300 dark:border-orange-600">
              <UploadCloud className="w-5 h-5 animate-bounce" />
              <span>Drop SAP screenshots here (up to 3 images, max 5 MB each)</span>
            </div>
          </div>
        )}

        {/* Thumbnail Preview Row */}
        {attachments.length > 0 && (
          <div className="flex items-center gap-2 px-3 pt-2.5 pb-1 flex-wrap">
            {attachments.map((att, idx) => (
              <div
                key={idx}
                className="flex items-center gap-2 px-2.5 py-1.5 rounded-xl bg-slate-100 dark:bg-[#27272a] border border-slate-200 dark:border-[#3f3f46] text-xs shadow-2xs group"
              >
                {att.isImage && att.previewUrl ? (
                  <img
                    src={att.previewUrl}
                    alt={att.name}
                    className="w-9 h-9 rounded-lg object-cover border border-slate-300 dark:border-slate-700 shrink-0"
                  />
                ) : (
                  <FileText className="w-4 h-4 text-[#ea580c] shrink-0" />
                )}
                <div className="flex flex-col min-w-0 max-w-[140px] sm:max-w-[180px]">
                  <span className="font-medium text-slate-800 dark:text-slate-200 truncate" title={att.name}>
                    {att.name}
                  </span>
                  <span className="text-[10px] text-slate-400">
                    {(att.sizeBytes / 1024).toFixed(1)} KB {att.isImage ? '• Screenshot' : ''}
                  </span>
                </div>
                {att.isUploading ? (
                  <Loader2 className="w-3.5 h-3.5 text-orange-500 animate-spin shrink-0 ml-1" />
                ) : (
                  <button
                    type="button"
                    onClick={() => removeAttachment(idx)}
                    className="text-slate-400 hover:text-rose-500 transition cursor-pointer ml-1 p-0.5 hover:bg-slate-200 dark:hover:bg-slate-800 rounded-md"
                    title="Remove screenshot"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Input Bar Row */}
        <div className="flex items-end gap-1.5 px-3 py-2 min-h-[48px]">
          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept="image/png,image/jpeg,image/webp,image/jpg"
            onChange={handleFileChange}
            className="hidden"
          />

          {/* Left: Paperclip Button */}
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={isLoading || isUploadingAny || attachments.length >= MAX_IMAGES}
            title={
              attachments.length >= MAX_IMAGES
                ? `Maximum ${MAX_IMAGES} images reached`
                : 'Upload SAP screenshot (PNG, JPG, WEBP $\\le$ 5 MB)'
            }
            aria-label="Upload SAP screenshot"
            className="shrink-0 flex items-center justify-center w-8 h-8 rounded-full text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200 hover:bg-black/5 dark:hover:bg-white/10 transition duration-150 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer mb-0.5"
          >
            <Paperclip className="w-4 h-4" />
          </button>

          {/* Center: Textarea */}
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            placeholder={
              isListening
                ? 'Listening... speak now'
                : attachments.length > 0
                ? 'Describe the issue or send screenshot to start step-by-step troubleshooting...'
                : 'Ask anything about SAP or paste/upload error screenshot...'
            }
            rows={1}
            disabled={isLoading}
            aria-label="Message input"
            className="flex-1 bg-transparent text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 text-[16px] px-2 py-1.5 focus:outline-none resize-none max-h-[200px] min-h-[26px] leading-relaxed self-center"
          />

          {/* Right: Mic + Circular Send/Stop Button */}
          <div className="shrink-0 flex items-center gap-1.5 mb-0.5">
            {/* Listening indicator */}
            {isListening && (
              <span className="flex items-center gap-1 text-[11px] text-rose-500 font-medium animate-pulse mr-1">
                <span className="w-2 h-2 rounded-full bg-rose-500 inline-block animate-ping" />
              </span>
            )}

            {/* Mic Button */}
            {voiceSupported && (
              <button
                type="button"
                onClick={toggleVoice}
                disabled={isLoading}
                title={isListening ? 'Stop recording' : 'Voice input'}
                aria-label={isListening ? 'Stop recording' : 'Voice input'}
                className={`flex items-center justify-center w-8 h-8 rounded-full transition duration-150 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer ${
                  isListening
                    ? 'bg-rose-500 text-white shadow-xs animate-pulse'
                    : 'text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200 hover:bg-black/5 dark:hover:bg-white/10'
                }`}
              >
                {isListening ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
              </button>
            )}

            {/* Send / Stop Circular Button */}
            {isLoading ? (
              <button
                type="button"
                onClick={onStop}
                title="Stop generating"
                aria-label="Stop generating"
                className="flex items-center justify-center w-8 h-8 rounded-full bg-slate-900 dark:bg-white text-white dark:text-slate-900 shadow-xs hover:opacity-90 active:scale-95 transition cursor-pointer"
              >
                <Square className="w-3 h-3 fill-current" />
              </button>
            ) : (
              <button
                type="submit"
                disabled={!canSubmit}
                title="Send message"
                aria-label="Send message"
                className={`flex items-center justify-center w-8 h-8 rounded-full transition-all duration-150 ${
                  canSubmit
                    ? 'bg-[#ea580c] hover:bg-[#c2410c] text-white shadow-xs hover:scale-105 active:scale-95 cursor-pointer'
                    : 'bg-black/5 dark:bg-white/10 text-slate-400 dark:text-slate-500 cursor-not-allowed opacity-50'
                }`}
              >
                <ArrowUp className="w-4 h-4 stroke-[2.5]" />
              </button>
            )}
          </div>
        </div>
      </form>

      {/* Disclaimer */}
      <div className="text-center mt-2">
        <span className="text-[11px] text-slate-500 dark:text-slate-400 select-none">
          Clyptus.AI can make mistakes, so please check important answers against official SAP documentation.
        </span>
      </div>
    </div>
  );
};
