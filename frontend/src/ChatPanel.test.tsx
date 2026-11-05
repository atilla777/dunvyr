import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ChatPanel } from './ChatPanel';
import type { ChatEvent, ChatHistory, ChatMember } from './chat';
import type { ChatConnectionStatus, ChatTransport, ChatTransportHandlers } from './chatSocket';

const CAMPAIGN_ID = '22222222-2222-4222-8222-222222222222';
const CURRENT_GUEST_ID = '11111111-1111-4111-8111-111111111111';
const OTHER_GUEST_ID = '33333333-3333-4333-8333-333333333333';

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

function history(events: ChatEvent[] = []): ChatHistory {
  return {
    campaign_id: CAMPAIGN_ID,
    events,
    last_sequence: events.at(-1)?.sequence ?? 0,
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
    handlers.onStatus(initialStatus);
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
    const event: ChatEvent = {
      type: 'member_joined',
      event_id: 'e1',
      campaign_id: CAMPAIGN_ID,
      sequence: 1,
      occurred_at: '2026-01-01T12:05:00+00:00',
      member,
    };
    act(() => {
      transports[0]?.handlers.onEvent(event);
      transports[0]?.handlers.onEvent(event);
    });

    expect(await screen.findByText('Боб присоединился к кампании')).toBeInTheDocument();
    expect(onMemberJoined).toHaveBeenCalledTimes(1);
    expect(onMemberJoined).toHaveBeenCalledWith(member);
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
      await screen.findByText('Соединение с чатом потеряно. Обновите страницу.'),
    ).toBeInTheDocument();
    expect(factory).toHaveBeenCalledTimes(1);

    fireEvent.change(screen.getByLabelText('Сообщение'), { target: { value: 'Привет' } });
    fireEvent.click(screen.getByRole('button', { name: 'Отправить' }));

    expect(transports[0]?.sent).toEqual([]);
    expect(
      await screen.findByText('Чат не подключён. Сообщение не отправлено; обновите страницу.'),
    ).toBeInTheDocument();
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
});
