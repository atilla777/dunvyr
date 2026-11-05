import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { LoginForm } from './LoginForm';

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
});

describe('LoginForm', () => {
  it('submits the nickname and reports the authenticated guest', async () => {
    const onAuthenticated = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(guest, 201));
    vi.stubGlobal('fetch', fetchMock);
    render(<LoginForm onAuthenticated={onAuthenticated} />);

    fireEvent.change(screen.getByLabelText('Псевдоним'), { target: { value: '  Алиса ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Войти' }));

    await waitFor(() => expect(onAuthenticated).toHaveBeenCalledWith(guest));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/identity/sessions');
    expect(init.method).toBe('POST');
    expect(init.credentials).toBe('same-origin');
    expect(JSON.parse(String(init.body))).toEqual({ nickname: '  Алиса ' });
  });

  it('shows a readable validation error and does not authenticate', async () => {
    const onAuthenticated = vi.fn();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ detail: 'Nickname is invalid' }, 422)),
    );
    render(<LoginForm onAuthenticated={onAuthenticated} />);

    fireEvent.change(screen.getByLabelText('Псевдоним'), { target: { value: '   ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Войти' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Псевдоним должен содержать от 1 до 32 символов без управляющих символов.',
    );
    expect(onAuthenticated).not.toHaveBeenCalled();
  });

  it('shows a readable network error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
    render(<LoginForm onAuthenticated={vi.fn()} />);

    fireEvent.change(screen.getByLabelText('Псевдоним'), { target: { value: 'Алиса' } });
    fireEvent.click(screen.getByRole('button', { name: 'Войти' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Не удалось связаться с сервером. Попробуйте ещё раз.',
    );
  });

  it('disables the submit button while the request is pending', async () => {
    const onAuthenticated = vi.fn();
    let resolveFetch: (value: Response) => void = () => {};
    const pending = new Promise<Response>((resolve) => {
      resolveFetch = resolve;
    });
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(pending));
    render(<LoginForm onAuthenticated={onAuthenticated} />);

    fireEvent.change(screen.getByLabelText('Псевдоним'), { target: { value: 'Алиса' } });
    fireEvent.click(screen.getByRole('button', { name: 'Войти' }));

    expect(screen.getByRole('button', { name: 'Входим…' })).toBeDisabled();

    resolveFetch(jsonResponse(guest, 201));
    await waitFor(() => expect(onAuthenticated).toHaveBeenCalledWith(guest));
    expect(screen.getByRole('button', { name: 'Войти' })).toBeEnabled();
  });
});
