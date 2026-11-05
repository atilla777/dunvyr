import { createIdempotencyKey } from './api';
import { isChatEvent, type ChatEvent } from './chat';

export type ChatConnectionStatus = 'connecting' | 'open' | 'closed' | 'error';

export interface ChatTransportHandlers {
  onEvent: (event: ChatEvent) => void;
  onStatus: (status: ChatConnectionStatus) => void;
  onServerError?: (code: string) => void;
}

export interface ChatTransport {
  sendMessage: (content: string) => boolean;
  close: () => void;
}

export type ChatTransportFactory = (
  campaignId: string,
  handlers: ChatTransportHandlers,
) => ChatTransport;

function chatSocketUrl(campaignId: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/api/campaigns/${encodeURIComponent(campaignId)}/chat`;
}

/**
 * Real same-origin WebSocket transport. There is deliberately no reconnect
 * loop in this slice: a closed socket is surfaced as an honest offline state.
 */
export const createChatTransport: ChatTransportFactory = (campaignId, handlers) => {
  if (typeof WebSocket === 'undefined') {
    handlers.onStatus('error');
    return { sendMessage: () => false, close: () => undefined };
  }

  handlers.onStatus('connecting');
  const socket = new WebSocket(chatSocketUrl(campaignId));

  socket.onopen = () => handlers.onStatus('open');
  socket.onerror = () => handlers.onStatus('error');
  socket.onclose = () => handlers.onStatus('closed');
  socket.onmessage = (message: MessageEvent<string>) => {
    let payload: unknown;
    try {
      payload = JSON.parse(message.data);
    } catch {
      return;
    }
    if (isChatEvent(payload)) {
      handlers.onEvent(payload);
      return;
    }
    if (
      typeof payload === 'object' &&
      payload !== null &&
      'type' in payload &&
      payload.type === 'error' &&
      'code' in payload &&
      typeof payload.code === 'string'
    ) {
      handlers.onServerError?.(payload.code);
    }
  };

  return {
    sendMessage(content: string): boolean {
      if (socket.readyState !== WebSocket.OPEN) {
        return false;
      }
      socket.send(
        JSON.stringify({
          type: 'message',
          client_message_id: createIdempotencyKey(),
          content,
        }),
      );
      return true;
    },
    close(): void {
      socket.close();
    },
  };
};
