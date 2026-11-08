import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { GameSessionPanel } from './GameSessionPanel';
import { newerSessionState, useGameSession } from './useGameSession';
import type { GameSessionState } from './chat';

const empty: GameSessionState = { revision: 0, session: null };
const running: GameSessionState = {
  revision: 1,
  session: { id: 'one', status: 'running', started_at: 'now', ended_at: null },
};
const paused: GameSessionState = {
  revision: 2,
  session: { ...running.session!, status: 'paused' },
};
function response(body: unknown, status = 200) {
  return { ok: status < 400, status, json: async () => body } as Response;
}
function View({
  organizer = true,
  connection = 'open' as const,
}: {
  organizer?: boolean;
  connection?: 'open' | 'reconnecting';
}) {
  const controller = useGameSession('c');
  return (
    <>
      <GameSessionPanel controller={controller} organizer={organizer} connection={connection} />
      <button onClick={() => controller.accept(paused)}>snapshot</button>
      <button onClick={() => controller.accept(running)}>old event</button>
    </>
  );
}
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it('accepts revision zero initially and never regresses for older snapshots or responses', () => {
  expect(newerSessionState(null, empty)).toEqual(empty);
  expect(newerSessionState(paused, running)).toEqual(paused);
  expect(newerSessionState(paused, { ...running, revision: 2 })).toEqual(paused);
});
it('preserves newest state when a delayed GET and old event arrive', async () => {
  let resolve!: (value: Response) => void;
  vi.stubGlobal(
    'fetch',
    vi.fn(
      () =>
        new Promise<Response>((r) => {
          resolve = r;
        }),
    ),
  );
  render(<View />);
  fireEvent.click(screen.getByText('snapshot'));
  fireEvent.click(screen.getByText('old event'));
  await waitFor(() => expect(resolve).toBeTypeOf('function'));
  resolve(response(empty));
  await waitFor(() => expect(screen.getByText('Встреча на паузе')).toBeInTheDocument());
});
it('hides controls from players and disables them while reconnecting', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(empty)));
  const { rerender } = render(<View organizer={false} />);
  await screen.findByText('Встреча ещё не началась');
  expect(screen.queryByText('Начать встречу')).not.toBeInTheDocument();
  rerender(<View connection="reconnecting" />);
  expect(screen.getByText('Начать встречу')).toBeDisabled();
  expect(screen.getByText(/состояние может устареть/)).toBeInTheDocument();
});
it('retries an uncertain command with identical key and body, ignoring an old replay', async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(response(empty))
    .mockRejectedValueOnce(new Error('offline'))
    .mockResolvedValueOnce(response(running));
  vi.stubGlobal('fetch', fetchMock);
  render(<View />);
  fireEvent.click(await screen.findByText('Начать встречу'));
  await screen.findByText(/Результат запроса неизвестен/);
  fireEvent.click(screen.getByText('snapshot'));
  fireEvent.click(screen.getByText('Повторить запрос'));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
  expect(fetchMock.mock.calls[1][1]).toEqual(fetchMock.mock.calls[2][1]);
  await screen.findByText('Встреча на паузе');
});
it('refreshes on conflict and reports access errors', async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(response(empty))
    .mockResolvedValueOnce(response({}, 409))
    .mockResolvedValueOnce(response(running))
    .mockResolvedValueOnce(response({}, 403));
  vi.stubGlobal('fetch', fetchMock);
  render(<View />);
  fireEvent.click(await screen.findByText('Начать встречу'));
  await screen.findByText(/Состояние встречи изменилось/);
  fireEvent.click(screen.getByText('Пауза'));
  await screen.findByText('Нет прав управлять встречей.');
});
