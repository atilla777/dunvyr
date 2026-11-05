import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { CreateCampaignForm } from './CreateCampaignForm';

const campaign = {
  id: '22222222-2222-4222-8222-222222222222',
  name: 'Ночная смена',
  max_seats: 6,
  organizer_id: '11111111-1111-4111-8111-111111111111',
  created_at: '2026-01-01T12:00:00+00:00',
  members: [],
  invitation: { active: true, secret: null, path: null },
};

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

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

describe('CreateCampaignForm', () => {
  it('creates a campaign with a generated idempotency key and reports it', async () => {
    const onCreated = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(campaign, 201));
    vi.stubGlobal('fetch', fetchMock);
    render(<CreateCampaignForm onCreated={onCreated} />);

    fireEvent.change(screen.getByLabelText('Название кампании'), {
      target: { value: 'Ночная смена' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Создать кампанию' }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(campaign));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/campaigns');
    expect(init.method).toBe('POST');
    expect(init.credentials).toBe('same-origin');
    expect(JSON.parse(String(init.body))).toEqual({ name: 'Ночная смена' });
    const headers = init.headers as Record<string, string>;
    expect(headers['Content-Type']).toBe('application/json');
    expect(headers['Idempotency-Key']).toMatch(UUID_PATTERN);
  });

  it('shows a readable validation error and does not report creation', async () => {
    const onCreated = vi.fn();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ detail: 'Campaign name must not be empty' }, 422)),
    );
    render(<CreateCampaignForm onCreated={onCreated} />);

    fireEvent.click(screen.getByRole('button', { name: 'Создать кампанию' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Название кампании должно содержать от 1 до 60 символов без управляющих символов.',
    );
    expect(onCreated).not.toHaveBeenCalled();
  });

  it('shows a readable network error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
    render(<CreateCampaignForm onCreated={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: 'Создать кампанию' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Не удалось связаться с сервером. Попробуйте ещё раз.',
    );
  });

  it('disables the submit button while the request is pending', async () => {
    let resolveFetch: (value: Response) => void = () => {};
    const pending = new Promise<Response>((resolve) => {
      resolveFetch = resolve;
    });
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(pending));
    render(<CreateCampaignForm onCreated={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: 'Создать кампанию' }));

    expect(screen.getByRole('button', { name: 'Создаём…' })).toBeDisabled();

    resolveFetch(jsonResponse(campaign, 201));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Создать кампанию' })).toBeEnabled(),
    );
  });
});
