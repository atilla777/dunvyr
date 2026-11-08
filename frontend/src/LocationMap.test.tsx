import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

import { LocationMap } from './LocationMap';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

it('renders explicit known rooms and separate unknown stubs without HTML interpretation', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          status: 'ready',
          map: {
            fingerprint: 'a',
            current_location_id: 'start',
            locations: [
              { id: 'start', name: '<start>', state: 'visited' },
              { id: 'known', name: 'Зал', state: 'discovered' },
            ],
            exits: [
              { source_location_id: 'start', label: 'Дверь', target_location_id: 'known' },
              { source_location_id: 'start', label: 'Первый', target_location_id: null },
              { source_location_id: 'start', label: 'Второй', target_location_id: null },
            ],
          },
        }),
        { status: 200 },
      ),
    ),
  );
  const { container } = render(<LocationMap campaignId="campaign" />);
  expect(await screen.findByText('<start> — текущая, посещено')).toBeInTheDocument();
  expect(screen.getByText('Зал — обнаружено')).toBeInTheDocument();
  expect(screen.getAllByText(/→ Неизвестная область/)).toHaveLength(2);
  expect(container.querySelector('start')).toBeNull();
  const svg = container.querySelector('svg')!;
  expect(within(svg as unknown as HTMLElement).getAllByText('Неизвестная область')).toHaveLength(2);
  const before = Number(svg.getAttribute('width'));
  fireEvent.click(screen.getByRole('button', { name: 'Увеличить карту' }));
  expect(Number(svg.getAttribute('width'))).toBeGreaterThan(before);
  fireEvent.click(screen.getByRole('button', { name: 'Сбросить масштаб карты' }));
  expect(Number(svg.getAttribute('width'))).toBe(before);
});

it('offers retry after error and reports waiting', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: 'waiting', map: null }), { status: 200 }),
      ),
  );
  render(<LocationMap campaignId="campaign" />);
  fireEvent.click(await screen.findByRole('button', { name: 'Повторить' }));
  expect(await screen.findByText('Карта появится после выбора приключения.')).toBeInTheDocument();
});

it('opens a dialog and restores focus on Escape', async () => {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', {
    configurable: true,
    value: function (this: HTMLDialogElement) {
      this.setAttribute('open', '');
    },
  });
  Object.defineProperty(HTMLDialogElement.prototype, 'close', {
    configurable: true,
    value: function (this: HTMLDialogElement) {
      this.removeAttribute('open');
    },
  });
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          status: 'ready',
          map: {
            fingerprint: 'a',
            current_location_id: 'start',
            locations: [{ id: 'start', name: 'Шлюз', state: 'visited' }],
            exits: [],
          },
        }),
        { status: 200 },
      ),
    ),
  );
  render(<LocationMap campaignId="campaign" />);
  const opener = await screen.findByRole('button', { name: 'Открыть карту' });
  fireEvent.click(opener);
  const dialog = screen.getByRole('dialog', { name: 'Карта группы' });
  fireEvent(dialog, new Event('cancel', { bubbles: false, cancelable: true }));
  expect(opener).toHaveFocus();
});
