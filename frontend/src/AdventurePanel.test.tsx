import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AdventurePanel } from './AdventurePanel';

const adventure = {
  adventure_id: 'shift',
  title: 'Последняя смена',
  description: 'Экспедиция',
  edition: '1',
  fingerprint: 'a'.repeat(64),
};
const waiting = { status: 'waiting', adventure: null };
const pinned = { status: 'pinned', adventure };
function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('AdventurePanel', () => {
  it('shows waiting to a participant without fetching the catalog', async () => {
    const fetcher = vi.fn().mockResolvedValue(response(waiting));
    vi.stubGlobal('fetch', fetcher);
    render(<AdventurePanel campaignId="c" isOrganizer={false} />);
    expect(await screen.findByText(/Ожидаем выбора/)).toBeInTheDocument();
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button', { name: /Выбрать/ })).not.toBeInTheDocument();
  });
  it('shows catalog and pins the selected version', async () => {
    const fetcher = vi
      .fn()
      .mockImplementation((url: string, options?: RequestInit) =>
        Promise.resolve(
          response(
            options?.method === 'POST'
              ? pinned
              : url.endsWith('/adventures')
                ? { adventures: [adventure] }
                : waiting,
          ),
        ),
      );
    vi.stubGlobal('fetch', fetcher);
    render(<AdventurePanel campaignId="c" isOrganizer />);
    expect(await screen.findByText(/Выбор окончательный/)).toBeInTheDocument();
    expect(screen.getByText('Экспедиция')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Выбрать Последняя смена' }));
    expect(await screen.findByText(`Версия: ${adventure.fingerprint}`)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Выбрать/ })).not.toBeInTheDocument();
    expect(
      JSON.parse(fetcher.mock.calls.find(([, options]) => options?.method === 'POST')![1].body),
    ).toEqual({ adventure_id: 'shift', fingerprint: adventure.fingerprint });
  });
  it.each(['stale_fingerprint', 'adventure_conflict'])(
    'handles %s and refreshes authoritative state',
    async (code) => {
      let refreshed = false;
      vi.stubGlobal(
        'fetch',
        vi.fn().mockImplementation((url: string, options?: RequestInit) => {
          if (options?.method === 'POST') {
            refreshed = true;
            return Promise.resolve(response({ detail: code }, 409));
          }
          return Promise.resolve(
            response(
              url.endsWith('/adventures')
                ? { adventures: [adventure] }
                : refreshed
                  ? pinned
                  : waiting,
            ),
          );
        }),
      );
      render(<AdventurePanel campaignId="c" isOrganizer />);
      fireEvent.click(await screen.findByRole('button', { name: /Выбрать/ }));
      expect(await screen.findByRole('alert')).toHaveTextContent(
        code === 'stale_fingerprint' ? 'Версия приключения изменилась' : 'уже выбрано',
      );
      fireEvent.click(screen.getByRole('button', { name: 'Обновить' }));
      expect(await screen.findByText(`Версия: ${adventure.fingerprint}`)).toBeInTheDocument();
    },
  );
  it('offers retry after a loading error', async () => {
    const fetcher = vi
      .fn()
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValue(response(pinned));
    vi.stubGlobal('fetch', fetcher);
    render(<AdventurePanel campaignId="c" isOrganizer={false} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось связаться');
    fireEvent.click(screen.getByRole('button', { name: 'Обновить' }));
    await waitFor(() =>
      expect(screen.getByText(`Версия: ${adventure.fingerprint}`)).toBeInTheDocument(),
    );
  });
});
