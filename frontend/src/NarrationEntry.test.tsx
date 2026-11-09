import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { retryNarration } from './api';
import { NarrationEntry } from './NarrationEntry';
import type { NarrationState } from './chat';

vi.mock('./api', () => ({ retryNarration: vi.fn() }));
const state: NarrationState = {
  result_event_id: 'result',
  state: 'failed',
  revision: 3,
  text: null,
  error: 'retryable_provider_error',
};
beforeEach(() => vi.clearAllMocks());

it('shows each lifecycle state and renders ready text without markup', () => {
  const props = { campaignId: 'campaign', onRefresh: vi.fn() };
  const view = render(<NarrationEntry {...props} narration={{ ...state, state: 'pending' }} />);
  expect(screen.getByText('Описание ожидает очереди…')).toBeVisible();
  view.rerender(<NarrationEntry {...props} narration={{ ...state, state: 'generating' }} />);
  expect(screen.getByText('Ведущий готовит описание…')).toBeVisible();
  view.rerender(
    <NarrationEntry {...props} narration={{ ...state, state: 'ready', text: '<b>Факт</b>' }} />,
  );
  expect(screen.getByText('<b>Факт</b>')).toBeVisible();
  expect(view.container.querySelector('b')).toBeNull();
});

it('retries narration only, refreshes and has accessible failure feedback', async () => {
  const refresh = vi.fn().mockResolvedValue(undefined);
  vi.mocked(retryNarration).mockResolvedValue({ ...state, state: 'pending', revision: 4 });
  render(<NarrationEntry campaignId="campaign" narration={state} onRefresh={refresh} />);
  expect(screen.getByText(/Результат действия сохранён/)).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Повторить описание' }));
  await waitFor(() => expect(refresh).toHaveBeenCalledOnce());
  expect(retryNarration).toHaveBeenCalledWith('campaign', state, expect.any(String));
  vi.mocked(retryNarration).mockRejectedValue(new Error('offline'));
  await waitFor(() => expect(screen.getByRole('button')).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Повторить описание' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Подождите 10 секунд');
  const calls = vi.mocked(retryNarration).mock.calls;
  expect(calls[0][2]).toBe(calls[1][2]);
});
