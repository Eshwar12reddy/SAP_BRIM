// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiStreamMessage, type StreamStatus } from './api';

describe('apiStreamMessage lifecycle and cancellation', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('handles abort cleanly without triggering onError (Scenario A: refresh/abort during streaming)', async () => {
    const controller = new AbortController();

    vi.spyOn(globalThis, 'fetch').mockImplementation(() => {
      // simulate abort immediately on fetch
      const err = new DOMException('The user aborted a request.', 'AbortError');
      return Promise.reject(err);
    });

    const onStatus = vi.fn();
    const onToken = vi.fn();
    const onDone = vi.fn();
    const onError = vi.fn();

    controller.abort();

    await apiStreamMessage(
      'chat-123',
      'How does SOM replicate?',
      { onStatus, onToken, onDone, onError },
      controller.signal
    );

    // onError must NOT be called for an intentional abort/refresh
    expect(onError).not.toHaveBeenCalled();
    expect(onDone).not.toHaveBeenCalled();
  });

  it('processes normal streaming stages, tokens, and done event correctly', async () => {
    const ssePayload = [
      'data: {"type": "status", "stage": "thinking", "message": "Analyzing SAP question..."}\n\n',
      'data: {"type": "token", "content": "SAP "}\n\n',
      'data: {"type": "token", "content": "BRIM"}\n\n',
      'data: {"type": "done", "answer": "SAP BRIM", "source_type": "knowledge_base"}\n\n',
    ].join('');

    const encoder = new TextEncoder();
    const mockReadableStream = new ReadableStream({
      start(streamController) {
        streamController.enqueue(encoder.encode(ssePayload));
        streamController.close();
      },
    });

    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      body: mockReadableStream,
    } as any);

    const statuses: StreamStatus[] = [];
    const tokens: string[] = [];
    let completedMeta: any = null;
    let finalAnswer = '';

    await apiStreamMessage(
      'chat-123',
      'What is BRIM?',
      {
        onStatus: (st) => statuses.push(st),
        onToken: (tk) => tokens.push(tk),
        onDone: (meta, ans) => {
          completedMeta = meta;
          finalAnswer = ans || '';
        },
      }
    );

    expect(statuses.length).toBe(1);
    expect(statuses[0].message).toBe('Analyzing SAP question...');
    expect(tokens.join('')).toBe('SAP BRIM');
    expect(completedMeta).toBeDefined();
    expect(completedMeta?.source_type).toBe('knowledge_base');
    expect(finalAnswer).toBe('SAP BRIM');
  });

  it('handles mid-stream abort cleanly during active read', async () => {
    const controller = new AbortController();
    const encoder = new TextEncoder();

    const mockReadableStream = new ReadableStream({
      start(ctrl) {
        ctrl.enqueue(encoder.encode('data: {"type": "token", "content": "Partial token"}\n\n'));
      },
      cancel() {
        // stream cancelled
      },
    });

    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      body: mockReadableStream,
    } as any);

    const tokens: string[] = [];
    const onError = vi.fn();
    const onDone = vi.fn();

    const streamPromise = apiStreamMessage(
      'chat-123',
      'Tell me about CI',
      {
        onToken: (t) => {
          tokens.push(t);
          // simulate refresh/abort after receiving first token
          controller.abort();
        },
        onError,
        onDone,
      },
      controller.signal
    );

    await streamPromise;

    expect(tokens).toEqual(['Partial token']);
    expect(onError).not.toHaveBeenCalled();
    expect(onDone).not.toHaveBeenCalled();
  });
});
