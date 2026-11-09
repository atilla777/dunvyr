import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { QueuePanel } from './QueuePanel';
import { newerQueueState, type GameSessionState, type QueueState } from './chat';

const running: GameSessionState = {
  revision: 3,
  session: { id: 's', status: 'running', started_at: 'now', ended_at: null },
};
const empty: QueueState = { version: 0, queue: null };
const queue: QueueState = {
  version: 2,
  queue: {
    encounter_id: 'e',
    participants: [
      { guest_id: 'a', character_id: 'ca' },
      { guest_id: 'b', character_id: 'cb' },
      { guest_id: 'c', character_id: 'cc' },
    ],
    round_order: ['a', 'b', 'c'],
    round_number: 1,
    cursor: 0,
    skipped: [],
    current_guest_id: 'a',
  },
};
const members = ['a', 'b', 'c'].map((id) => ({
  guest_id: id,
  nickname: id,
  role: 'player' as const,
  joined_at: 'now',
}));
const response = (data: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => data }) as Response;
function mockFetch() {
  const mock = vi.fn((url: string, init?: RequestInit) => {
    void init;
    return Promise.resolve(
      response(
        url.endsWith('/character')
          ? { id: 'ca' }
          : { status: 'ready', catalog: { encounters: [{ id: 'e', name: 'Испытание' }] } },
      ),
    );
  });
  vi.stubGlobal('fetch', mock);
  return mock;
}
function view(state: QueueState, session = running, currentGuestId = 'a') {
  return (
    <QueuePanel
      campaignId="campaign"
      currentGuestId={currentGuestId}
      members={members}
      state={state}
      accept={vi.fn()}
      session={session}
      presence={{ epoch: 'x', revision: 1, online_guest_ids: ['a', 'b'] }}
      connection="open"
    />
  );
}
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it('accepts only increasing queue versions, including zero', () => {
  expect(newerQueueState(null, empty)).toEqual(empty);
  expect(newerQueueState(queue, empty)).toEqual(queue);
  expect(newerQueueState(queue, { ...empty, version: 2 })).toEqual(queue);
});
it('starts only with character and running meeting, with expected revisions', async () => {
  const fetch = mockFetch();
  render(view(empty));
  fireEvent.click(await screen.findByRole('button', { name: 'Начать: Испытание' }));
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
  const init = fetch.mock.calls[2][1] as RequestInit;
  expect(JSON.parse(init.body as string)).toEqual({
    expected_version: 0,
    expected_lifecycle_revision: 3,
    character_id: 'ca',
    encounter_id: 'e',
  });
});
it('allows only current player to swap with a later online player', async () => {
  mockFetch();
  const { rerender } = render(view(queue));
  expect(screen.getByRole('button', { name: 'Обменяться с b' })).toBeEnabled();
  expect(screen.queryByRole('button', { name: 'Обменяться с c' })).not.toBeInTheDocument();
  rerender(view(queue, running, 'b'));
  expect(screen.queryByRole('button', { name: /Обменяться/ })).not.toBeInTheDocument();
  rerender(view(queue, { ...running, session: { ...running.session!, status: 'paused' } }));
  expect(screen.getByText(/Встреча на паузе/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Обменяться/ })).not.toBeInTheDocument();
  rerender(
    view({
      ...queue,
      queue: { ...queue.queue!, current_guest_id: null, cursor: 3, skipped: ['a', 'b', 'c'] },
    }),
  );
  expect(screen.getByText(/Ожидаем игроков/)).toBeInTheDocument();
});
