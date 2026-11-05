import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { App } from './App';

const guest = { id: '11111111-1111-4111-8111-111111111111', nickname: 'Алиса' };
const campaign = {
  id: '22222222-2222-4222-8222-222222222222',
  name: 'Ночная смена',
  max_seats: 6,
  organizer_id: guest.id,
  created_at: '2026-01-01T12:00:00+00:00',
  members: [
    {
      guest_id: guest.id,
      nickname: 'Алиса',
      role: 'organizer',
      joined_at: '2026-01-01T12:00:00+00:00',
    },
  ],
  invitation: { active: true, secret: 'invitation-secret', path: '/join/invitation-secret' },
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
  window.localStorage.clear();
});

describe('App', () => {
  it('renders the title and the login form when there is no session', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ detail: 'Not authenticated' }, 401));
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);

    expect(screen.getByRole('heading', { level: 1, name: 'Dunvyr' })).toBeInTheDocument();
    expect(await screen.findByRole('textbox', { name: 'Псевдоним' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Войти' })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith('/api/identity/me', {
      credentials: 'same-origin',
    });
  });

  it('greets the authenticated guest and offers campaign creation', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(guest)));

    render(<App />);

    expect(await screen.findByText('Вы вошли как Алиса')).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: 'Псевдоним' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Создать кампанию' })).toBeInTheDocument();
    expect(window.localStorage.length).toBe(0);
    expect(document.cookie).not.toContain('dunvyr_session');
  });

  it('falls back to the login form when the session check fails over the network', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));

    render(<App />);

    expect(await screen.findByRole('textbox', { name: 'Псевдоним' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'Dunvyr' })).toBeInTheDocument();
  });

  it('shows the campaign screen with the invitation link and member list after creation', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(guest))
      .mockResolvedValueOnce(jsonResponse(campaign, 201));
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);

    fireEvent.change(await screen.findByRole('textbox', { name: 'Название кампании' }), {
      target: { value: 'Ночная смена' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Создать кампанию' }));

    expect(
      await screen.findByRole('heading', { level: 2, name: 'Ночная смена' }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(new URL('/join/invitation-secret', window.location.origin).toString()),
    ).toBeInTheDocument();
    expect(screen.getByText('Алиса')).toBeInTheDocument();
    expect(screen.getByText('— организатор')).toBeInTheDocument();
    expect(screen.getByText('(вы)')).toBeInTheDocument();
  });
});
