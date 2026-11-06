import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChatEvent } from './chat';
import {
  CHAT_RECONNECT_ATTEMPTS,
  createChatTransport,
  type ChatConnectionStatus,
} from './chatSocket';

const CAMPAIGN_ID = '22222222-2222-4222-8222-222222222222';

function messageEvent(eventId: string, sequence: number): ChatEvent {
  return {
    type: 'message',
    event_id: eventId,
    campaign_id: CAMPAIGN_ID,
    sequence,
    occurred_at: '2026-01-01T12:00:00+00:00',
    message: {
      id: `message-${eventId}`,
      author_id: '33333333-3333-4333-8333-333333333333',
      author_nickname: 'Боб',
      client_message_id: `client-${eventId}`,
      content: `Текст ${eventId}`,
      created_at: '2026-01-01T12:00:00+00:00',
    },
  };
}

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  readyState = FakeWebSocket.CONNECTING;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  readonly sent: string[] = [];

  constructor(readonly url: string) {
    FakeWebSocket.instances.push(this);
  }

  open(): void {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }

  error(): void {
    this.onerror?.();
  }

  /** Simulates a network drop: `close` fires without the owner asking. */
  drop(): void {
    if (this.readyState === FakeWebSocket.CLOSED) {
      return;
    }
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.();
  }

  close(): void {
    this.drop();
  }

  send(data: string): void {
    this.sent.push(data);
  }

  message(payload: unknown): void {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent<string>);
  }
}

function latestSocket(): FakeWebSocket {
  const socket = FakeWebSocket.instances.at(-1);
  if (socket === undefined) {
    throw new Error('no WebSocket instance created');
  }
  return socket;
}

async function flushMicrotasks(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

beforeEach(() => {
  FakeWebSocket.instances = [];
  vi.useFakeTimers();
  vi.stubGlobal('WebSocket', FakeWebSocket as unknown as typeof WebSocket);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('createChatTransport', () => {
  it('buffers and refuses sends until the first snapshot completes', async () => {
    const statuses: ChatConnectionStatus[] = [];
    const delivered: ChatEvent[] = [];
    let resolve = () => {};
    const transport = createChatTransport(CAMPAIGN_ID, {
      onEvent: (event) => delivered.push(event),
      onStatus: (status) => statuses.push(status),
      onResync: () =>
        new Promise<void>((done) => {
          resolve = done;
        }),
    });
    latestSocket().open();
    await flushMicrotasks();
    latestSocket().message(messageEvent('gap', 1));
    expect(delivered).toEqual([]);
    expect(transport.sendMessage('x')).toBe(false);
    expect(statuses.at(-1)).toBe('connecting');
    resolve();
    await flushMicrotasks();
    expect(delivered).toHaveLength(1);
    expect(statuses.at(-1)).toBe('open');
    expect(transport.sendMessage('x')).toBe(true);
  });

  it('reconnects after a drop, resyncs first and buffers live events until the snapshot settles', async () => {
    const statuses: ChatConnectionStatus[] = [];
    const delivered: ChatEvent[] = [];
    let resolveResync: () => void = () => undefined;
    const onResync = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveResync = resolve;
        }),
    );

    createChatTransport(CAMPAIGN_ID, {
      onEvent: (event) => delivered.push(event),
      onStatus: (status) => statuses.push(status),
      onResync,
    });
    latestSocket().open();
    await flushMicrotasks();
    resolveResync();
    await flushMicrotasks();
    latestSocket().drop();

    expect(statuses.at(-1)).toBe('reconnecting');
    expect(FakeWebSocket.instances).toHaveLength(1);

    // First retry is scheduled at 500 ms; nothing happens before it.
    await vi.advanceTimersByTimeAsync(499);
    expect(FakeWebSocket.instances).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(FakeWebSocket.instances).toHaveLength(2);

    latestSocket().open();
    await flushMicrotasks();
    expect(onResync).toHaveBeenCalledTimes(2);
    expect(statuses.at(-1)).toBe('reconnecting');

    const missed = messageEvent('e2', 2);
    latestSocket().message(missed);
    expect(delivered).toEqual([]);

    resolveResync();
    await flushMicrotasks();

    expect(delivered).toEqual([missed]);
    expect(statuses.at(-1)).toBe('open');

    const live = messageEvent('e3', 3);
    latestSocket().message(live);
    expect(delivered).toEqual([missed, live]);
  });

  it('keeps retrying when the snapshot fails and reports offline after the bounded window', async () => {
    const statuses: ChatConnectionStatus[] = [];
    const onResync = vi.fn().mockRejectedValue(new Error('snapshot failed'));

    createChatTransport(CAMPAIGN_ID, {
      onEvent: vi.fn(),
      onStatus: (status) => statuses.push(status),
      onResync,
    });
    latestSocket().open();
    latestSocket().drop();

    const delays = [500, 1000, 2000, 4000, 8000];
    for (const delay of delays) {
      await vi.advanceTimersByTimeAsync(delay);
      latestSocket().open();
      await flushMicrotasks();
    }

    await flushMicrotasks();
    expect(onResync).toHaveBeenCalledTimes(CHAT_RECONNECT_ATTEMPTS);
    expect(statuses.at(-1)).toBe('closed');
  });

  it('treats a socket error as a drop and starts the reconnect window', async () => {
    const statuses: ChatConnectionStatus[] = [];

    createChatTransport(CAMPAIGN_ID, {
      onEvent: vi.fn(),
      onStatus: (status) => statuses.push(status),
      onResync: vi.fn(),
    });
    latestSocket().open();
    latestSocket().error();

    expect(statuses.at(-1)).toBe('reconnecting');
    await vi.advanceTimersByTimeAsync(500);
    expect(FakeWebSocket.instances).toHaveLength(2);
  });

  it('stops reconnecting after an explicit close', async () => {
    const statuses: ChatConnectionStatus[] = [];
    const transport = createChatTransport(CAMPAIGN_ID, {
      onEvent: vi.fn(),
      onStatus: (status) => statuses.push(status),
      onResync: vi.fn(),
    });
    latestSocket().open();

    transport.close();

    expect(statuses.at(-1)).toBe('closed');
    await vi.advanceTimersByTimeAsync(60_000);
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it('refuses to send while the socket is not open', async () => {
    const transport = createChatTransport(CAMPAIGN_ID, {
      onEvent: vi.fn(),
      onStatus: vi.fn(),
      onResync: vi.fn(),
    });

    expect(transport.sendMessage('Привет')).toBe(false);

    latestSocket().open();
    await flushMicrotasks();
    expect(transport.sendMessage('Привет')).toBe(true);
    expect(latestSocket().sent).toHaveLength(1);
  });
  it('times out hung handshakes and aborts hung snapshots within the recovery deadline', async () => {
    const signals: AbortSignal[] = [];
    const statuses: ChatConnectionStatus[] = [];
    createChatTransport(CAMPAIGN_ID, {
      onEvent: vi.fn(),
      onStatus: (status) => statuses.push(status),
      onResync: (signal) => {
        signals.push(signal);
        return new Promise<void>(() => {});
      },
    });
    await vi.advanceTimersByTimeAsync(5500);
    latestSocket().open();
    await flushMicrotasks();
    await vi.advanceTimersByTimeAsync(24500);
    expect(signals[0]?.aborted).toBe(true);
    expect(statuses.at(-1)).toBe('closed');
  });

  it('ignores old socket callbacks and a snapshot completing after cancellation', async () => {
    let resolve = () => {};
    const statuses: ChatConnectionStatus[] = [];
    const onEvent = vi.fn();
    const transport = createChatTransport(CAMPAIGN_ID, {
      onEvent,
      onStatus: (status) => statuses.push(status),
      onResync: () =>
        new Promise<void>((done) => {
          resolve = done;
        }),
    });
    const old = latestSocket();
    old.open();
    await flushMicrotasks();
    old.drop();
    await vi.advanceTimersByTimeAsync(500);
    old.message(messageEvent('stale', 1));
    old.open();
    resolve();
    await flushMicrotasks();
    expect(onEvent).not.toHaveBeenCalled();
    expect(statuses.at(-1)).not.toBe('open');
    transport.close();
  });
});
