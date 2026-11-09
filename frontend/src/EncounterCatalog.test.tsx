import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

import { EncounterCatalog } from './EncounterCatalog';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

const ready = {
  status: 'ready',
  catalog: {
    fingerprint: 'a',
    current_location_id: 'airlock',
    encounters: [
      {
        id: 'terminal',
        object_id: 'terminal',
        name: '<Терминал>',
        description: 'Описание',
        solutions: [
          {
            id: 'repair',
            name: 'Ремонт',
            description: 'Осмотр',
            check: {
              skill_id: 'repair',
              skill_name: 'Ремонт',
              characteristic: 'intellect',
              difficulty: 5,
            },
          },
        ],
      },
    ],
  },
};
const response = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });

it('shows safe text and check metadata without execution controls', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(ready)));
  const { container } = render(<EncounterCatalog campaignId="one" />);
  expect(screen.getByText('Загружаем испытания…')).toBeInTheDocument();
  expect(await screen.findByText('<Терминал>')).toBeInTheDocument();
  expect(
    screen.getByText(/Навык: Ремонт · Характеристика: Интеллект · Сложность: 5/),
  ).toBeInTheDocument();
  expect(screen.queryByText('Выполнение действий пока недоступно.')).not.toBeInTheDocument();
  expect(
    within(screen.getByRole('region', { name: 'Испытания' })).queryByRole('button'),
  ).toBeNull();
  expect(container.querySelector('терминал')).toBeNull();
});

it('offers retry and displays legacy empty catalog', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockRejectedValueOnce(Error('offline'))
      .mockResolvedValueOnce(
        response({ status: 'ready', catalog: { ...ready.catalog, encounters: [] } }),
      ),
  );
  render(<EncounterCatalog campaignId="one" />);
  fireEvent.click(await screen.findByRole('button', { name: 'Повторить' }));
  expect(await screen.findByText('Доступных испытаний нет.')).toBeInTheDocument();
});

it('polls waiting only and cancels on unmount', async () => {
  vi.useFakeTimers();
  const fetcher = vi.fn().mockResolvedValue(response({ status: 'waiting', catalog: null }));
  vi.stubGlobal('fetch', fetcher);
  const { unmount } = render(<EncounterCatalog campaignId="one" />);
  await act(async () => {});
  expect(screen.getByText('Испытания появятся после выбора приключения.')).toBeInTheDocument();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(3000);
  });
  expect(fetcher).toHaveBeenCalledTimes(2);
  unmount();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(6000);
  });
  expect(fetcher).toHaveBeenCalledTimes(2);
});

it('ignores stale results after switching campaigns and aborts the old request', async () => {
  let resolve!: (value: Response) => void;
  const old = new Promise<Response>((done) => {
    resolve = done;
  });
  const fetcher = vi
    .fn()
    .mockReturnValueOnce(old)
    .mockResolvedValueOnce(
      response({ status: 'ready', catalog: { ...ready.catalog, encounters: [] } }),
    );
  vi.stubGlobal('fetch', fetcher);
  const { rerender } = render(<EncounterCatalog campaignId="one" />);
  const signal = (fetcher.mock.calls[0][1] as RequestInit).signal!;
  rerender(<EncounterCatalog campaignId="two" />);
  expect(signal.aborted).toBe(true);
  expect(await screen.findByText('Доступных испытаний нет.')).toBeInTheDocument();
  await act(async () => resolve(response(ready)));
  await waitFor(() => expect(screen.queryByText('<Терминал>')).not.toBeInTheDocument());
});
