import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ChatPanel } from './ChatPanel';
import type { ChatEvent, ChatHistory, ChatMember } from './chat';
import type { ChatConnectionStatus, ChatTransport, ChatTransportHandlers } from './chatSocket';

const CAMPAIGN_ID = '22222222-2222-4222-8222-222222222222';
const CURRENT_GUEST_ID = '11111111-1111-4111-8111-111111111111';
const OTHER_GUEST_ID = '33333333-3333-4333-8333-333333333333';
const CAROL_GUEST_ID = '44444444-4444-4444-8444-444444444444';

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

function messageEvent(
  eventId: string,
  sequence: number,
  authorId: string,
  nickname: string,
  content: string,
): ChatEvent {
  return {
    type: 'message',
    event_id: eventId,
    campaign_id: CAMPAIGN_ID,
    sequence,
    occurred_at: '2026-01-01T12:00:00+00:00',
    message: {
      id: `message-${eventId}`,
      author_id: authorId,
      author_nickname: nickname,
      client_message_id: `client-${eventId}`,
      content,
      created_at: '2026-01-01T12:00:00+00:00',
    },
  };
}

function memberJoinedEvent(eventId: string, sequence: number, member: ChatMember): ChatEvent {
  return {
    type: 'member_joined',
    event_id: eventId,
    campaign_id: CAMPAIGN_ID,
    sequence,
    occurred_at: member.joined_at,
    member,
  };
}

function history(events: ChatEvent[] = []): ChatHistory {
  return {
    campaign_id: CAMPAIGN_ID,
    events,
    last_sequence: events.at(-1)?.sequence ?? 0,
    game_session_state: { revision: 0, session: null },
    queue_state: { version: 0, queue: null },
    presence_state: { epoch: 'epoch', revision: 0, online_guest_ids: [] },
  };
}

interface FakeTransport {
  handlers: ChatTransportHandlers;
  sent: string[];
  sendResult: boolean;
  close: () => void;
}

function fakeFactory(initialStatus: ChatConnectionStatus = 'open') {
  const transports: FakeTransport[] = [];
  const factory = vi.fn((_campaignId: string, handlers: ChatTransportHandlers) => {
    const record: FakeTransport = {
      handlers,
      sent: [],
      sendResult: initialStatus === 'open',
      close: vi.fn(),
    };
    const transport: ChatTransport = {
      sendMessage: (content: string) => {
        if (record.sendResult) {
          record.sent.push(content);
        }
        return record.sendResult;
      },
      close: record.close,
    };
    transports.push(record);
    if (initialStatus === 'open') {
      void Promise.resolve()
        .then(() => handlers.onResync?.(new AbortController().signal))
        .then(() => handlers.onStatus('open'))
        .catch(() => undefined);
    } else handlers.onStatus(initialStatus);
    return transport;
  });
  return { factory, transports };
}

function stubHistory(events: ChatEvent[] = []) {
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse(history(events)));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('ChatPanel', () => {
  it('accepts only higher same-epoch live presence and replaces epoch on resync', async () => {
    const a = { epoch: 'a', revision: 4, online_guest_ids: [CURRENT_GUEST_ID] };
    const b = { epoch: 'b', revision: 0, online_guest_ids: [] };
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(jsonResponse({ ...history(), presence_state: a }))
        .mockResolvedValueOnce(jsonResponse({ ...history(), presence_state: b })),
    );
    const onPresenceState = vi.fn();
    const { factory, transports } = fakeFactory();
    render(
      <ChatPanel
        campaignId={CAMPAIGN_ID}
        currentGuestId={CURRENT_GUEST_ID}
        transportFactory={factory}
        onPresenceState={onPresenceState}
      />,
    );
    await screen.findByText('Чат на связи');
    expect(onPresenceState).toHaveBeenLastCalledWith(a);
    const handlers = transports[0].handlers;
    act(() => {
      handlers.onPresence?.({ ...a, revision: 3, online_guest_ids: [] });
      handlers.onPresence?.({ ...a, revision: 4, online_guest_ids: [] });
      handlers.onPresence?.({ ...b, revision: 20 });
    });
    expect(onPresenceState).toHaveBeenCalledTimes(1);
    const newer = { ...a, revision: 6, online_guest_ids: [] };
    act(() => {
      handlers.onPresence?.(newer);
      handlers.onPresence?.({ ...a, revision: 5 });
    });
    expect(onPresenceState).toHaveBeenLastCalledWith(newer);
    await act(async () => {
      await handlers.onResync?.(new AbortController().signal);
    });
    expect(onPresenceState).toHaveBeenLastCalledWith(b);
    act(() => handlers.onPresence?.({ ...a, revision: 100 }));
    expect(onPresenceState).toHaveBeenCalledTimes(3);
  });
  it('delivers session state from empty snapshots and live events on reconnect without losing a draft', async () => {
    const initial = { revision: 0, session: null };
    const running = {
      revision: 1,
      session: { id: 'session', status: 'running' as const, started_at: 'now', ended_at: null },
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ ...history(), game_session_state: initial }))
      .mockResolvedValueOnce(jsonResponse({ ...history(), game_session_state: running }));
    vi.stubGlobal('fetch', fetchMock);
    const onSessionState = vi.fn();
    const { factory, transports } = fakeFactory();
    render(
      <ChatPanel
        campaignId={CAMPAIGN_ID}
        currentGuestId={CURRENT_GUEST_ID}
        transportFactory={factory}
        onSessionState={onSessionState}
      />,
    );
    await screen.findByText('Чат на связи');
    expect(onSessionState).toHaveBeenCalledWith(initial);
    fireEvent.change(screen.getByLabelText('Сообщение'), { target: { value: 'черновик' } });
    await act(async () => {
      await transports[0].handlers.onResync?.(new AbortController().signal);
    });
    expect(onSessionState).toHaveBeenCalledWith(running);
    act(() =>
      transports[0].handlers.onEvent({
        type: 'game_session_changed',
        event_id: 'session-event',
        campaign_id: CAMPAIGN_ID,
        sequence: 3,
        occurred_at: 'now',
        game_session_state: running,
      }),
    );
    expect(onSessionState).toHaveBeenCalledTimes(3);
    expect(screen.getByLabelText('Сообщение')).toHaveValue('черновик');
  });
  it('delivers queue snapshots and live changes across resync without losing the draft', async () => {
    const initial = { version: 0, queue: null };
    const newer = { version: 2, queue: null };
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(jsonResponse({ ...history(), queue_state: initial }))
        .mockResolvedValueOnce(jsonResponse({ ...history(), queue_state: newer })),
    );
    const onQueueState = vi.fn();
    const { factory, transports } = fakeFactory();
    render(
      <ChatPanel
        campaignId={CAMPAIGN_ID}
        currentGuestId={CURRENT_GUEST_ID}
        transportFactory={factory}
        onQueueState={onQueueState}
      />,
    );
    await screen.findByText('Чат на связи');
    fireEvent.change(screen.getByLabelText('Сообщение'), { target: { value: 'черновик' } });
    await act(async () => {
      await transports[0].handlers.onResync?.(new AbortController().signal);
    });
    act(() =>
      transports[0].handlers.onEvent({
        type: 'queue_changed',
        event_id: 'queue',
        campaign_id: CAMPAIGN_ID,
        sequence: 3,
        occurred_at: 'now',
        queue_state: initial,
      }),
    );
    expect(onQueueState.mock.calls.map(([state]) => state)).toEqual([initial, newer, initial]);
    expect(screen.getByLabelText('Сообщение')).toHaveValue('черновик');
  });
  it('loads history and distinguishes own messages from other members', async () => {
    stubHistory([
      messageEvent('e1', 1, CURRENT_GUEST_ID, 'Алиса', 'Моё сообщение'),
      messageEvent('e2', 2, OTHER_GUEST_ID, 'Боб', 'Ответ Боба'),
    ]);
    const { factory } = fakeFactory();

    render(
      <ChatPanel
        campaignId={CAMPAIGN_ID}
        currentGuestId={CURRENT_GUEST_ID}
        transportFactory={factory}
      />,
    );

    expect(await screen.findByText('Моё сообщение')).toBeInTheDocument();
    expect(screen.getByText('Ответ Боба')).toBeInTheDocument();
    expect(screen.getByText('Вы')).toBeInTheDocument();
    expect(screen.getByText('Боб')).toBeInTheDocument();
    expect(screen.getByText('Моё сообщение').closest('li')).toHaveClass('chat__message--own');
    expect(screen.getByText('Ответ Боба').closest('li')).not.toHaveClass('chat__message--own');
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(`/api/campaigns/${CAMPAIGN_ID}/chat/events`, {
      credentials: 'same-origin',
      signal: expect.any(AbortSignal),
    });
  });

  it('sends the draft through the transport and clears the input', async () => {
    stubHistory();
    const { factory, transports } = fakeFactory();
    render(
      <ChatPanel
        campaignId={CAMPAIGN_ID}
        currentGuestId={CURRENT_GUEST_ID}
        transportFactory={factory}
      />,
    );

    fireEvent.change(await screen.findByLabelText('Сообщение'), {
      target: { value: '  Привет всем  ' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Отправить' }));

    expect(transports[0]?.sent).toEqual(['Привет всем']);
    expect(screen.getByLabelText('Сообщение')).toHaveValue('');
  });

  it('appends live events once and deduplicates by event ID', async () => {
    stubHistory();
    const { factory, transports } = fakeFactory();
    render(
      <ChatPanel
        campaignId={CAMPAIGN_ID}
        currentGuestId={CURRENT_GUEST_ID}
        transportFactory={factory}
      />,
    );

    const event = messageEvent('e1', 1, OTHER_GUEST_ID, 'Боб', 'Живое сообщение');
    act(() => {
      transports[0]?.handlers.onEvent(event);
      transports[0]?.handlers.onEvent(event);
    });

    expect(await screen.findByText('Живое сообщение')).toBeInTheDocument();
    expect(screen.getAllByText('Живое сообщение')).toHaveLength(1);
  });

  it('shows membership events and reports the new member once', async () => {
    stubHistory();
    const { factory, transports } = fakeFactory();
    const onMemberJoined = vi.fn();
    render(
      <ChatPanel
        campaignId={CAMPAIGN_ID}
        currentGuestId={CURRENT_GUEST_ID}
        onMemberJoined={onMemberJoined}
        transportFactory={factory}
      />,
    );

    const member: ChatMember = {
      guest_id: OTHER_GUEST_ID,
      nickname: 'Боб',
      role: 'player',
      joined_at: '2026-01-01T12:05:00+00:00',
    };
    const event = memberJoinedEvent('e1', 1, member);
    act(() => {
      transports[0]?.handlers.onEvent(event);
      transports[0]?.handlers.onEvent(event);
    });

    expect(await screen.findByText('Боб присоединился к кампании')).toBeInTheDocument();
    expect(onMemberJoined).toHaveBeenCalledTimes(1);
    expect(onMemberJoined).toHaveBeenCalledWith(member);
  });

  it('shows honest loading, stale and offline connection states', async () => {
    stubHistory();
    const { factory, transports } = fakeFactory('connecting');
    render(
      <ChatPanel
        campaignId={CAMPAIGN_ID}
        currentGuestId={CURRENT_GUEST_ID}
        transportFactory={factory}
      />,
    );

    expect(await screen.findByText('Подключаемся к чату…')).toBeInTheDocument();

    act(() => transports[0]?.handlers.onStatus('reconnecting'));
    expect(screen.getByText('Соединение с чатом потеряно. Восстанавливаем…')).toBeInTheDocument();

    act(() => transports[0]?.handlers.onStatus('closed'));
    expect(
      screen.getByText('Соединение с чатом потеряно. Восстановить не удалось. Обновите страницу.'),
    ).toBeInTheDocument();
  });

  it('reports an honest offline state without opening a second connection', async () => {
    stubHistory();
    const { factory, transports } = fakeFactory('closed');
    render(
      <ChatPanel
        campaignId={CAMPAIGN_ID}
        currentGuestId={CURRENT_GUEST_ID}
        transportFactory={factory}
      />,
    );

    expect(
      await screen.findByText(
        'Соединение с чатом потеряно. Восстановить не удалось. Обновите страницу.',
      ),
    ).toBeInTheDocument();
    expect(factory).toHaveBeenCalledTimes(1);

    fireEvent.change(screen.getByLabelText('Сообщение'), { target: { value: 'Привет' } });
    fireEvent.click(screen.getByRole('button', { name: 'Отправить' }));

    expect(transports[0]?.sent).toEqual([]);
    expect(
      await screen.findByText('Чат не подключён. Сообщение не отправлено.'),
    ).toBeInTheDocument();
  });

  it('recovers missed events after reconnect with the sequence cursor without duplicates', async () => {
    const e1 = messageEvent('e1', 1, OTHER_GUEST_ID, 'Боб', 'Первое');
    const e2 = messageEvent('e2', 2, OTHER_GUEST_ID, 'Боб', 'Второе');
    const e3 = messageEvent('e3', 3, OTHER_GUEST_ID, 'Боб', 'Третье');
    const carol: ChatMember = {
      guest_id: CAROL_GUEST_ID,
      nickname: 'Кэрол',
      role: 'player',
      joined_at: '2026-01-01T12:10:00+00:00',
    };
    const e4 = memberJoinedEvent('e4', 4, carol);
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(history([e1, e2])))
      .mockResolvedValueOnce(jsonResponse(history([e2, e3, e4])))
      .mockResolvedValueOnce(jsonResponse(history([e3, e4])));
    vi.stubGlobal('fetch', fetchMock);
    const { factory, transports } = fakeFactory();
    const onMemberJoined = vi.fn();

    render(
      <ChatPanel
        campaignId={CAMPAIGN_ID}
        currentGuestId={CURRENT_GUEST_ID}
        onMemberJoined={onMemberJoined}
        transportFactory={factory}
      />,
    );

    expect(await screen.findByText('Первое')).toBeInTheDocument();
    expect(screen.getByText('Второе')).toBeInTheDocument();

    const handlers = transports[0]?.handlers;
    act(() => {
      handlers?.onStatus('reconnecting');
      handlers?.onEvent(e3);
    });
    expect(screen.getByText('Соединение с чатом потеряно. Восстанавливаем…')).toBeInTheDocument();

    // First reconnect snapshot: the server replays e2/e3 (already seen) plus e4.
    await act(async () => {
      await handlers?.onResync?.(new AbortController().signal);
      handlers?.onStatus('open');
    });

    expect(fetchMock).toHaveBeenLastCalledWith(
      `/api/campaigns/${CAMPAIGN_ID}/chat/events?after=2`,
      { credentials: 'same-origin', signal: expect.any(AbortSignal) },
    );
    expect(screen.getAllByText('Второе')).toHaveLength(1);
    expect(screen.getAllByText('Третье')).toHaveLength(1);
    expect(screen.getAllByText('Кэрол присоединился к кампании')).toHaveLength(1);
    expect(onMemberJoined).toHaveBeenCalledTimes(1);
    expect(onMemberJoined).toHaveBeenCalledWith(carol);
    expect(screen.getByText('Чат на связи')).toBeInTheDocument();

    // A repeated snapshot for the same cursor must not duplicate the stream.
    await act(async () => {
      await handlers?.onResync?.(new AbortController().signal);
    });

    expect(fetchMock).toHaveBeenLastCalledWith(
      `/api/campaigns/${CAMPAIGN_ID}/chat/events?after=4`,
      { credentials: 'same-origin', signal: expect.any(AbortSignal) },
    );
    expect(screen.getAllByText('Третье')).toHaveLength(1);
    expect(screen.getAllByText('Кэрол присоединился к кампании')).toHaveLength(1);
    expect(onMemberJoined).toHaveBeenCalledTimes(1);

    const renderedOrder = screen.getAllByRole('listitem').map((item) => item.textContent ?? '');
    expect(renderedOrder).toHaveLength(4);
    expect(renderedOrder[0]).toContain('Первое');
    expect(renderedOrder[1]).toContain('Второе');
    expect(renderedOrder[2]).toContain('Третье');
    expect(renderedOrder[3]).toContain('Кэрол присоединился к кампании');
  });

  it('reports a failed history load without hiding the composer', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
    const { factory } = fakeFactory();
    render(
      <ChatPanel
        campaignId={CAMPAIGN_ID}
        currentGuestId={CURRENT_GUEST_ID}
        transportFactory={factory}
      />,
    );

    expect(
      await screen.findByText('Не удалось загрузить историю чата. Попробуйте обновить страницу.'),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('Сообщение')).toBeInTheDocument();
  });
  it('uses snapshot events not live sequence or response watermark as cursor', async () => {
    const e5 = messageEvent('e5', 5, OTHER_GUEST_ID, 'Боб', 'Пять');
    const e6 = messageEvent('e6', 6, OTHER_GUEST_ID, 'Боб', 'Шесть');
    const e7 = messageEvent('e7', 7, OTHER_GUEST_ID, 'Боб', 'Семь');
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ ...history([e5]), last_sequence: 7 }))
      .mockResolvedValueOnce(jsonResponse(history([e6, e7])));
    vi.stubGlobal('fetch', fetchMock);
    const { factory, transports } = fakeFactory();
    render(
      <ChatPanel
        campaignId={CAMPAIGN_ID}
        currentGuestId={CURRENT_GUEST_ID}
        transportFactory={factory}
      />,
    );
    await screen.findByText('Пять');
    act(() => transports[0]?.handlers.onEvent(e7));
    await act(async () => {
      await transports[0]?.handlers.onResync?.(new AbortController().signal);
    });
    expect(fetchMock.mock.calls[1]?.[0]).toContain('?after=5');
    expect(screen.getAllByText('Семь')).toHaveLength(1);
    expect(screen.getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      expect.stringContaining('Пять'),
      expect.stringContaining('Шесть'),
      expect.stringContaining('Семь'),
    ]);
  });

  it('uses after zero after an empty initial snapshot and ignores aborted completion', async () => {
    let finish: (value: Response) => void = () => {};
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(history()))
      .mockImplementationOnce(
        () =>
          new Promise<Response>((resolve) => {
            finish = resolve;
          }),
      )
      .mockResolvedValueOnce(jsonResponse(history()));
    vi.stubGlobal('fetch', fetchMock);
    const { factory, transports } = fakeFactory();
    render(
      <ChatPanel
        campaignId={CAMPAIGN_ID}
        currentGuestId={CURRENT_GUEST_ID}
        transportFactory={factory}
      />,
    );
    await screen.findByText('Сообщений пока нет. Напишите первым.');
    const controller = new AbortController();
    let pending: Promise<void> | void;
    act(() => {
      pending = transports[0]?.handlers.onResync?.(controller.signal);
    });
    controller.abort();
    await act(async () => {
      finish(jsonResponse(history([messageEvent('late', 8, OTHER_GUEST_ID, 'Боб', 'Поздно')])));
      await pending;
    });
    expect(screen.queryByText('Поздно')).not.toBeInTheDocument();
    await act(async () => {
      await transports[0]?.handlers.onResync?.(new AbortController().signal);
    });
    expect(fetchMock.mock.calls[1]?.[0]).toContain('?after=0');
    expect(fetchMock.mock.calls[2]?.[0]).toContain('?after=0');
  });

  it('notifies about members in the initial snapshot exactly once', async () => {
    const member: ChatMember = {
      guest_id: OTHER_GUEST_ID,
      nickname: 'Боб',
      role: 'player',
      joined_at: '2026-01-01T12:05:00+00:00',
    };
    const event = memberJoinedEvent('join', 1, member);
    stubHistory([event]);
    const onMemberJoined = vi.fn();
    const { factory, transports } = fakeFactory();
    render(
      <ChatPanel
        campaignId={CAMPAIGN_ID}
        currentGuestId={CURRENT_GUEST_ID}
        onMemberJoined={onMemberJoined}
        transportFactory={factory}
      />,
    );
    await screen.findByText('Боб присоединился к кампании');
    act(() => transports[0]?.handlers.onEvent(event));
    expect(onMemberJoined).toHaveBeenCalledTimes(1);
  });
});
