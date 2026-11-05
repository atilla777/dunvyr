import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { JoinScreen } from './JoinScreen';

const campaign = {
  id: '22222222-2222-4222-8222-222222222222',
  name: 'Ночная смена',
  max_seats: 6,
  organizer_id: '11111111-1111-4111-8111-111111111111',
  created_at: '2026-01-01T12:00:00+00:00',
  members: [
    {
      guest_id: '11111111-1111-4111-8111-111111111111',
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
  invitation: { active: true, secret: null, path: null },
};

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('JoinScreen', () => {
  it('joins by the link secret and reports the campaign', async () => {
    const onJoined = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(campaign, 201));
    vi.stubGlobal('fetch', fetchMock);
    render(<JoinScreen secret="invitation-secret" onJoined={onJoined} />);

    fireEvent.click(screen.getByRole('button', { name: 'Присоединиться' }));

    await waitFor(() => expect(onJoined).toHaveBeenCalledWith(campaign));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/campaigns/join');
    expect(init.method).toBe('POST');
    expect(init.credentials).toBe('same-origin');
    expect(JSON.parse(String(init.body))).toEqual({ secret: 'invitation-secret' });
  });

  it('shows a readable message when the link is missing or revoked', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: 'not_found' }, 404)));
    render(<JoinScreen secret="invitation-secret" onJoined={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: 'Присоединиться' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Ссылка-приглашение не найдена или отозвана.',
    );
  });

  it.each([
    ['campaign_full', 'В кампании нет свободных мест.'],
    ['nickname_taken', 'Этот псевдоним уже занят в кампании.'],
  ])('maps the %s conflict to a readable message', async (detail, message) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail }, 409)));
    render(<JoinScreen secret="invitation-secret" onJoined={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: 'Присоединиться' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(message);
  });

  it('shows a readable rate-limit error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: 'limited' }, 429)));
    render(<JoinScreen secret="invitation-secret" onJoined={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: 'Присоединиться' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Слишком много попыток присоединиться. Попробуйте позже.',
    );
  });

  it('shows a readable network error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
    render(<JoinScreen secret="invitation-secret" onJoined={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: 'Присоединиться' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Не удалось связаться с сервером. Попробуйте ещё раз.',
    );
  });

  it('disables the join button while the request is pending', async () => {
    let resolveFetch: (value: Response) => void = () => {};
    const pending = new Promise<Response>((resolve) => {
      resolveFetch = resolve;
    });
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(pending));
    render(<JoinScreen secret="invitation-secret" onJoined={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: 'Присоединиться' }));

    expect(screen.getByRole('button', { name: 'Присоединяемся…' })).toBeDisabled();

    resolveFetch(jsonResponse(campaign, 201));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Присоединиться' })).toBeEnabled(),
    );
  });
});
