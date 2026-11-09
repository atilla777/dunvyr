import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Campaign } from './api';
import { CampaignScreen } from './CampaignScreen';
import type { ChatTransportHandlers, ChatTransportFactory } from './chatSocket';

vi.mock('./CharacterPanel', () => ({ CharacterPanel: () => null }));
vi.mock('./SceneViewer', () => ({ SceneViewer: () => null }));
vi.mock('./LocationMap', () => ({ LocationMap: () => null }));

const CURRENT_GUEST_ID = '11111111-1111-4111-8111-111111111111';

const campaign: Campaign = {
  id: '22222222-2222-4222-8222-222222222222',
  name: 'Ночная смена',
  max_seats: 6,
  organizer_id: CURRENT_GUEST_ID,
  created_at: '2026-01-01T12:00:00+00:00',
  members: [
    {
      guest_id: CURRENT_GUEST_ID,
      nickname: 'Алиса',
      role: 'organizer',
      joined_at: '2026-01-01T12:00:00+00:00',
    },
    {
      guest_id: '33333333-3333-4333-8333-333333333333',
      nickname: 'Боб',
      role: 'player',
      joined_at: '2026-01-01T12:05:00+00:00',
    },
  ],
  invitation: { active: true, secret: 'invitation-secret', path: '/join/invitation-secret' },
};

function stubClipboard(writeText: (text: string) => Promise<void>) {
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText },
    configurable: true,
  });
}

beforeEach(() => {
  // ChatPanel always asks for an empty history first; individual tests may
  // override fetch with their own scenario.
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) =>
      Promise.resolve(
        jsonResponse(
          url.endsWith('/adventure')
            ? { status: 'waiting', adventure: null }
            : url.endsWith('/adventures')
              ? { adventures: [] }
              : {
                  campaign_id: campaign.id,
                  events: [],
                  last_sequence: 0,
                  game_session_state: { revision: 0, session: null },
                  presence_state: { epoch: 'epoch', revision: 0, online_guest_ids: [] },
                  queue_state: { version: 0, queue: null },
                },
        ),
      ),
    ),
  );
  // jsdom has no real WebSocket; the panel shows the honest offline state.
  vi.stubGlobal('WebSocket', undefined);
});

afterEach(() => {
  cleanup();
  Reflect.deleteProperty(navigator, 'clipboard');
  vi.unstubAllGlobals();
});

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

describe('CampaignScreen', () => {
  it('refetches the private proposal snapshot on reconnect without remounting the chat', async () => {
    let handlers: ChatTransportHandlers | undefined;
    let version = 0;
    const proposalUrl = `/api/campaigns/${campaign.id}/proposals`;
    const fetchMock = vi.fn(async (url: string) => {
      if (url === proposalUrl) {
        return jsonResponse({
          version,
          proposals:
            version === 0
              ? []
              : [
                  {
                    id: 'p',
                    character_id: 'c',
                    availability: 'available',
                    selection: {
                      encounter_id: 'e',
                      object_id: 'o',
                      solution_id: 's',
                      encounter_name: 'Терминал',
                      solution_name: 'Проверить',
                    },
                  },
                ],
        });
      }
      if (url.includes('/chat/events'))
        return jsonResponse({
          campaign_id: campaign.id,
          events: [],
          last_sequence: 0,
          game_session_state: { revision: 0, session: null },
          presence_state: { epoch: 'epoch', revision: 0, online_guest_ids: [] },
          queue_state: { version: 0, queue: null },
        });
      if (url.endsWith('/game-session')) return jsonResponse({ revision: 0, session: null });
      if (url.endsWith('/character')) return jsonResponse(null);
      if (url.endsWith('/encounters')) return jsonResponse({ status: 'waiting', catalog: null });
      if (url.endsWith('/adventure')) return jsonResponse({ status: 'waiting', adventure: null });
      if (url.endsWith('/adventures')) return jsonResponse({ adventures: [] });
      return jsonResponse({});
    });
    vi.stubGlobal('fetch', fetchMock);
    const factory: ChatTransportFactory = (_id, next) => {
      handlers = next;
      void Promise.resolve()
        .then(() => next.onResync?.(new AbortController().signal))
        .then(() => next.onStatus('open'));
      return { sendMessage: () => true, close: () => undefined };
    };
    render(
      <CampaignScreen
        campaign={campaign}
        currentGuestId={CURRENT_GUEST_ID}
        transportFactory={factory}
      />,
    );
    await screen.findByText('Чат на связи');
    await waitFor(() =>
      expect(fetchMock.mock.calls.filter(([url]) => url === proposalUrl)).toHaveLength(2),
    );
    const draft = screen.getByLabelText('Сообщение');
    fireEvent.change(draft, { target: { value: 'черновик' } });
    draft.focus();
    act(() => handlers?.onStatus('reconnecting'));
    version = 1;
    await act(async () => {
      await handlers?.onResync?.(new AbortController().signal);
      handlers?.onStatus('open');
    });
    expect(await screen.findByText('Терминал — Проверить')).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([url]) => url === proposalUrl)).toHaveLength(3);
    expect(screen.getByLabelText('Сообщение')).toBe(draft);
    expect(draft).toHaveValue('черновик');
    expect(draft).toHaveFocus();
  });
  it('shows definitive presence only while synchronized', async () => {
    let handlers: ChatTransportHandlers | undefined;
    const factory: ChatTransportFactory = (_id, next) => {
      handlers = next;
      void Promise.resolve()
        .then(() => next.onResync?.(new AbortController().signal))
        .then(() => next.onStatus('open'));
      return { sendMessage: () => true, close: () => undefined };
    };
    render(
      <CampaignScreen
        campaign={campaign}
        currentGuestId={CURRENT_GUEST_ID}
        transportFactory={factory}
      />,
    );
    await screen.findByText('Чат на связи');
    const bob = screen.getByText('Боб').closest('li');
    expect(bob).not.toBeNull();
    expect(bob).toHaveTextContent('Не в сети');
    act(() =>
      handlers?.onPresence?.({
        epoch: 'epoch',
        revision: 1,
        online_guest_ids: [campaign.members[1].guest_id],
      }),
    );
    expect(bob).toHaveTextContent('В сети');
    act(() => handlers?.onStatus('reconnecting'));
    expect(bob).toHaveTextContent('Статус неизвестен');
    expect(bob).not.toHaveTextContent('Не в сети');
  });
  it('shows the absolute invitation link and copies it to the clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    stubClipboard(writeText);
    render(<CampaignScreen campaign={campaign} currentGuestId={CURRENT_GUEST_ID} />);

    const invitationUrl = new URL('/join/invitation-secret', window.location.origin).toString();

    expect(screen.getByRole('heading', { level: 2, name: 'Ночная смена' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: invitationUrl })).toHaveAttribute(
      'href',
      invitationUrl,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Скопировать ссылку' }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith(invitationUrl));
    expect(await screen.findByRole('status')).toHaveTextContent('Ссылка скопирована');
  });

  it('lists the organizer and marks the current guest', () => {
    render(<CampaignScreen campaign={campaign} currentGuestId={CURRENT_GUEST_ID} />);

    expect(screen.getByText('Мест занято: 2 из 6')).toBeInTheDocument();
    expect(screen.getByText('Алиса')).toBeInTheDocument();
    expect(screen.getByText('— организатор')).toBeInTheDocument();
    expect(screen.getByText('(вы)')).toBeInTheDocument();
    expect(screen.getByText('Боб')).toBeInTheDocument();
    expect(screen.getAllByText('— организатор')).toHaveLength(1);
  });

  it('does not repeat the secret when the campaign is read later', () => {
    render(
      <CampaignScreen
        campaign={{ ...campaign, invitation: { active: true, secret: null, path: null } }}
        currentGuestId={CURRENT_GUEST_ID}
      />,
    );

    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Скопировать ссылку' })).not.toBeInTheDocument();
    expect(
      screen.getByText('Ссылка-приглашение показывается только один раз при создании кампании.'),
    ).toBeInTheDocument();
  });

  it('reports a clipboard failure without hiding the link', async () => {
    stubClipboard(vi.fn().mockRejectedValue(new Error('denied')));
    render(<CampaignScreen campaign={campaign} currentGuestId={CURRENT_GUEST_ID} />);

    fireEvent.click(screen.getByRole('button', { name: 'Скопировать ссылку' }));

    expect(
      await screen.findByText('Не удалось скопировать ссылку. Выделите её вручную.'),
    ).toHaveAttribute('role', 'alert');
    expect(screen.getByRole('link')).toBeInTheDocument();
  });

  it('lets the organizer revoke the invitation link', async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) =>
      Promise.resolve(
        jsonResponse(
          url.endsWith('/adventure')
            ? { status: 'waiting', adventure: null }
            : url.endsWith('/adventures')
              ? { adventures: [] }
              : {
                  ...campaign,
                  invitation: { active: false, secret: null, path: null },
                },
        ),
      ),
    );
    vi.stubGlobal('fetch', fetchMock);
    render(<CampaignScreen campaign={campaign} currentGuestId={CURRENT_GUEST_ID} />);

    fireEvent.click(screen.getByRole('button', { name: 'Отозвать ссылку' }));

    expect(await screen.findByText('Ссылка отозвана')).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Отозвать ссылку' })).not.toBeInTheDocument();
    const revokeCall = fetchMock.mock.calls.find(([url]) =>
      String(url).endsWith('/invitation/revoke'),
    ) as [string, RequestInit];
    expect(revokeCall[0]).toBe(`/api/campaigns/${campaign.id}/invitation/revoke`);
    expect(revokeCall[1].method).toBe('POST');
    expect(revokeCall[1].credentials).toBe('same-origin');
  });

  it('reports a failed revoke and keeps the link active', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockImplementation((url: string) =>
          url.endsWith('/adventure')
            ? Promise.resolve(jsonResponse({ status: 'waiting', adventure: null }))
            : url.endsWith('/adventures')
              ? Promise.resolve(jsonResponse({ adventures: [] }))
              : Promise.reject(new Error('offline')),
        ),
    );
    render(<CampaignScreen campaign={campaign} currentGuestId={CURRENT_GUEST_ID} />);

    fireEvent.click(screen.getByRole('button', { name: 'Отозвать ссылку' }));

    expect(
      await screen.findByText('Не удалось отозвать ссылку. Попробуйте ещё раз.'),
    ).toHaveAttribute('role', 'alert');
    expect(screen.getByRole('link')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Отозвать ссылку' })).toBeEnabled();
  });

  it('updates the live roster when a member_joined event arrives', async () => {
    let handlers: ChatTransportHandlers | null = null;
    const transportFactory: ChatTransportFactory = (_campaignId, nextHandlers) => {
      handlers = nextHandlers;
      void Promise.resolve()
        .then(() => nextHandlers.onResync?.(new AbortController().signal))
        .then(() => nextHandlers.onStatus('open'))
        .catch(() => undefined);
      return { sendMessage: () => true, close: () => undefined };
    };
    render(
      <CampaignScreen
        campaign={campaign}
        currentGuestId={CURRENT_GUEST_ID}
        transportFactory={transportFactory}
      />,
    );

    await waitFor(() => expect(handlers).not.toBeNull());
    act(() => {
      handlers?.onEvent({
        type: 'member_joined',
        event_id: 'event-3',
        campaign_id: campaign.id,
        sequence: 3,
        occurred_at: '2026-01-01T12:10:00+00:00',
        member: {
          guest_id: '44444444-4444-4444-8444-444444444444',
          nickname: 'Кэрол',
          role: 'player',
          joined_at: '2026-01-01T12:10:00+00:00',
        },
      });
    });

    expect(await screen.findByText('Кэрол')).toBeInTheDocument();
    expect(screen.getByText('Мест занято: 3 из 6')).toBeInTheDocument();
    expect(await screen.findByText('Кэрол присоединился к кампании')).toBeInTheDocument();
  });

  it('places the chat before invitation and roster panels for mobile priority', () => {
    render(<CampaignScreen campaign={campaign} currentGuestId={CURRENT_GUEST_ID} />);

    const chatTitle = screen.getByRole('heading', { level: 3, name: 'Чат' });
    const membersTitle = screen.getByRole('heading', { level: 3, name: 'Участники' });
    expect(
      chatTitle.compareDocumentPosition(membersTitle) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(screen.getByLabelText('Сообщение')).toBeInTheDocument();
  });

  it('hides the invitation section from a player who is not the organizer', () => {
    render(
      <CampaignScreen
        campaign={campaign}
        currentGuestId={'33333333-3333-4333-8333-333333333333'}
      />,
    );

    expect(screen.getByText('Алиса')).toBeInTheDocument();
    expect(screen.getByText('Боб')).toBeInTheDocument();
    expect(screen.getByText('(вы)')).toBeInTheDocument();
    expect(screen.queryByText('Ссылка-приглашение')).not.toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Отозвать ссылку' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Скопировать ссылку' })).not.toBeInTheDocument();
  });
});
