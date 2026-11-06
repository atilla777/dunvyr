import { createIdempotencyKey } from './api';
import { isChatEvent, type ChatEvent } from './chat';

export type ChatConnectionStatus = 'connecting' | 'open' | 'reconnecting' | 'closed' | 'error';

export interface ChatTransportHandlers {
  onEvent: (event: ChatEvent) => void;
  onStatus: (status: ChatConnectionStatus) => void;
  onServerError?: (code: string) => void;
  /**
   * Called after a lost connection is re-established, before live delivery
   * resumes. The transport buffers incoming events until the promise settles,
   * so the client can fetch the missed snapshot (cursor `after`) first.
   */
  onResync?: (signal: AbortSignal) => Promise<void> | void;
}

export interface ChatTransport {
  sendMessage: (content: string) => boolean;
  close: () => void;
}

export type ChatTransportFactory = (
  campaignId: string,
  handlers: ChatTransportHandlers,
) => ChatTransport;

/**
 * Bounded reconnect window: five attempts with exponential backoff
 * 500 / 1000 / 2000 / 4000 / 8000 ms. Each attempt has 5 seconds and
 * the entire recovery window has 30 seconds. After that the transport
 * reports an honest `closed` (offline) state instead of pretending to reconnect.
 */
export const CHAT_RECONNECT_ATTEMPTS = 5;
export const CHAT_RECONNECT_BASE_DELAY_MS = 500;
export const CHAT_RECONNECT_MAX_DELAY_MS = 8000;
export const CHAT_ATTEMPT_TIMEOUT_MS = 5000;
export const CHAT_RECOVERY_TIMEOUT_MS = 30000;

function reconnectDelay(attempt: number): number {
  return Math.min(CHAT_RECONNECT_BASE_DELAY_MS * 2 ** (attempt - 1), CHAT_RECONNECT_MAX_DELAY_MS);
}

function chatSocketUrl(campaignId: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/api/campaigns/${encodeURIComponent(campaignId)}/chat`;
}

function isServerError(payload: unknown): payload is { type: 'error'; code: string } {
  return (
    typeof payload === 'object' &&
    payload !== null &&
    'type' in payload &&
    payload.type === 'error' &&
    'code' in payload &&
    typeof payload.code === 'string'
  );
}

/**
 * Real same-origin WebSocket transport with a bounded reconnect loop.
 *
 * Detection: `onclose` (after an error or an abrupt network drop) starts the
 * retry window; a deliberate `close()` from the owner never reconnects.
 * Recovery: a re-opened socket is not reported as `open` until the injected
 * `onResync` (REST snapshot with the last seen sequence) has finished, and
 * events received meanwhile are buffered and delivered afterwards.
 */
export const createChatTransport: ChatTransportFactory = (campaignId, handlers) => {
  if (typeof WebSocket === 'undefined') {
    handlers.onStatus('error');
    return { sendMessage: () => false, close: () => undefined };
  }

  let socket: WebSocket | null = null;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;
  let attemptTimer: ReturnType<typeof setTimeout> | null = null;
  let deadlineTimer: ReturnType<typeof setTimeout> | null = null;
  let controller: AbortController | null = null;
  let attempts = 0;
  let everOpened = false;
  let ready = false;
  let stopped = false;
  let buffered: ChatEvent[] = [];

  function clearTimers(): void {
    if (retryTimer !== null) clearTimeout(retryTimer);
    if (attemptTimer !== null) clearTimeout(attemptTimer);
    if (deadlineTimer !== null) clearTimeout(deadlineTimer);
    retryTimer = attemptTimer = deadlineTimer = null;
  }

  function discard(): void {
    if (attemptTimer !== null) clearTimeout(attemptTimer);
    attemptTimer = null;
    controller?.abort();
    controller = null;
    const old = socket;
    socket = null;
    ready = false;
    buffered = [];
    old?.close();
  }

  function stop(): void {
    if (stopped) return;
    stopped = true;
    clearTimers();
    discard();
    handlers.onStatus('closed');
  }

  function startWindow(): void {
    if (deadlineTimer === null) deadlineTimer = setTimeout(stop, CHAT_RECOVERY_TIMEOUT_MS);
  }

  function retry(): void {
    if (stopped || retryTimer !== null) return;
    discard();
    startWindow();
    if (attempts >= CHAT_RECONNECT_ATTEMPTS) {
      stop();
      return;
    }
    attempts += 1;
    handlers.onStatus(everOpened ? 'reconnecting' : 'connecting');
    retryTimer = setTimeout(() => {
      retryTimer = null;
      connect();
    }, reconnectDelay(attempts));
  }

  function connect(): void {
    if (stopped) return;
    startWindow();
    const next = new WebSocket(chatSocketUrl(campaignId));
    socket = next;
    const current = new AbortController();
    controller = current;
    const active = () => !stopped && socket === next && !current.signal.aborted;
    attemptTimer = setTimeout(() => {
      if (active()) retry();
    }, CHAT_ATTEMPT_TIMEOUT_MS);

    next.onopen = () => {
      if (!active()) return;
      everOpened = true;
      void Promise.resolve()
        .then(() => {
          if (active()) return handlers.onResync?.(current.signal);
        })
        .then(() => {
          if (!active()) return;
          if (attemptTimer !== null) clearTimeout(attemptTimer);
          if (deadlineTimer !== null) clearTimeout(deadlineTimer);
          attemptTimer = deadlineTimer = null;
          attempts = 0;
          ready = true;
          const queued = buffered;
          buffered = [];
          for (const event of queued) {
            if (!active()) return;
            handlers.onEvent(event);
          }
          if (active()) handlers.onStatus('open');
        })
        .catch(() => {
          if (active()) retry();
        });
    };
    next.onerror = () => {
      if (active()) retry();
    };
    next.onclose = () => {
      if (active()) retry();
    };
    next.onmessage = (message: MessageEvent<string>) => {
      if (!active()) return;
      let payload: unknown;
      try {
        payload = JSON.parse(message.data);
      } catch {
        return;
      }
      if (isChatEvent(payload)) {
        if (ready) handlers.onEvent(payload);
        else buffered.push(payload);
      } else if (isServerError(payload)) {
        handlers.onServerError?.(payload.code);
      }
    };
  }

  handlers.onStatus('connecting');
  connect();

  return {
    sendMessage(content: string): boolean {
      if (!ready || socket === null || socket.readyState !== WebSocket.OPEN) return false;
      socket.send(
        JSON.stringify({
          type: 'message',
          client_message_id: createIdempotencyKey(),
          content,
        }),
      );
      return true;
    },
    close: stop,
  };
};
