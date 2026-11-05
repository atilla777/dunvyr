import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { App } from './App';

const guest = { id: '11111111-1111-4111-8111-111111111111', nickname: 'Алиса' };

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

  it('greets the authenticated guest and keeps the session out of localStorage', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(guest)));

    render(<App />);

    expect(await screen.findByText('Вы вошли как Алиса')).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: 'Псевдоним' })).not.toBeInTheDocument();
    expect(window.localStorage.length).toBe(0);
    expect(document.cookie).not.toContain('dunvyr_session');
  });

  it('falls back to the login form when the session check fails over the network', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));

    render(<App />);

    expect(await screen.findByRole('textbox', { name: 'Псевдоним' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'Dunvyr' })).toBeInTheDocument();
  });
});
