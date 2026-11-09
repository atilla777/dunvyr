import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { newerProposals, useProposals, type ProposalState } from './useProposals';
import type { GameSessionState, QueueState } from './chat';

const session: GameSessionState = {
  revision: 3,
  session: { id: 's', status: 'running', started_at: '', ended_at: null },
};
const queue: QueueState = { version: 2, queue: null };
const selection = { encounter_id: 'e', object_id: 'o', solution_id: 's' };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

it('never resurrects an item from an older receipt', () => {
  const newer: ProposalState = { version: 2, proposals: [] };
  const older: ProposalState = {
    version: 1,
    proposals: [{ id: 'old', character_id: 'c', availability: 'unavailable', selection: null }],
  };
  expect(newerProposals(newer, older)).toEqual(newer);
});

it('retries an unknown outcome with exactly the same key and body', async () => {
  let calls = 0;
  const requests: RequestInit[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/character')) return json({ id: 'c' });
      if (init?.method === 'POST') {
        requests.push(init);
        if (++calls === 1) throw new Error('lost');
        return json({ version: 1, proposals: [] });
      }
      return json({ version: 0, proposals: [] });
    }),
  );
  const { result } = renderHook(() =>
    useProposals(
      'campaign',
      'guest',
      queue,
      vi.fn(),
      session,
      vi.fn().mockResolvedValue(true),
      'open',
    ),
  );
  await waitFor(() => expect(result.current.ready).toBe(true));
  act(() => result.current.execute('create', selection));
  await waitFor(() => expect(result.current.pending).not.toBeNull());
  act(() => result.current.retry());
  await waitFor(() => expect(result.current.pending).toBeNull());
  expect(requests[1].headers).toEqual(requests[0].headers);
  expect(requests[1].body).toEqual(requests[0].body);
});

it('retains the original command after a lost committed receipt, refresh and rate limit', async () => {
  const requests: RequestInit[] = [];
  const saved = {
    id: 'p',
    character_id: 'c',
    availability: 'unavailable' as const,
    selection: null,
  };
  let server: ProposalState = { version: 0, proposals: [] };
  let originalKey = '';
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/character')) return json({ id: 'c' });
      if (init?.method !== 'POST') return json(server);
      requests.push(init);
      const key = (init.headers as Record<string, string>)['Idempotency-Key'];
      if (requests.length === 1) {
        originalKey = key;
        server = { version: 1, proposals: [saved] };
        throw new Error('receipt lost after commit');
      }
      if (requests.length === 2)
        return new Response(null, { status: 429, headers: { 'Retry-After': '7' } });
      if (key !== originalKey)
        server = { version: 2, proposals: [...server.proposals, { ...saved, id: 'duplicate' }] };
      return json({ ...server, replayed: key === originalKey });
    }),
  );
  const { result } = renderHook(() =>
    useProposals(
      'campaign',
      'guest',
      queue,
      vi.fn(),
      session,
      vi.fn().mockResolvedValue(true),
      'open',
    ),
  );
  await waitFor(() => expect(result.current.ready).toBe(true));
  act(() => result.current.execute('create', selection));
  await waitFor(() => expect(result.current.pending).not.toBeNull());
  await act(async () => {
    await result.current.refresh();
  });
  expect(result.current.state).toEqual({ version: 1, proposals: [saved] });
  act(() => result.current.retry());
  await waitFor(() => expect(result.current.error).toContain('через 7 сек.'));
  expect(result.current.pending).not.toBeNull();
  expect(result.current.ready).toBe(false);
  act(() => result.current.execute('create', selection));
  expect(requests).toHaveLength(2);
  act(() => result.current.retry());
  await waitFor(() => expect(result.current.pending).toBeNull());
  expect(requests).toHaveLength(3);
  for (const request of requests) {
    expect(request.headers).toEqual(requests[0].headers);
    expect(request.body).toEqual(requests[0].body);
  }
  expect(result.current.state).toEqual({ version: 1, proposals: [saved] });
  expect(server.proposals).toHaveLength(1);
});

it('refreshes proposal, lifecycle and queue after conflict', async () => {
  const refreshSession = vi.fn().mockResolvedValue(true);
  const acceptQueue = vi.fn();
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith('/character')) return json({ id: 'c' });
    if (url.endsWith('/queue')) return json(queue);
    if (init?.method === 'POST') return json({}, 409);
    return json({ version: 0, proposals: [] });
  });
  vi.stubGlobal('fetch', fetcher);
  const { result } = renderHook(() =>
    useProposals('campaign', 'guest', queue, acceptQueue, session, refreshSession, 'open'),
  );
  await waitFor(() => expect(result.current.ready).toBe(true));
  act(() => result.current.execute('create', selection));
  await waitFor(() => expect(result.current.error).toContain('Состояние изменилось'));
  expect(refreshSession).toHaveBeenCalled();
  expect(acceptQueue).toHaveBeenCalledWith(queue);
  expect(fetcher.mock.calls.filter(([url]) => url.endsWith('/proposals'))).toHaveLength(3);
});

it('disables changes when paused and editing outside the turn', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) =>
      url.endsWith('/character') ? json({ id: 'c' }) : json({ version: 0, proposals: [] }),
    ),
  );
  const { result, rerender } = renderHook(
    ({ current }) => useProposals('campaign', 'guest', queue, vi.fn(), current, vi.fn(), 'open'),
    { initialProps: { current: session } },
  );
  await waitFor(() => expect(result.current.ready).toBe(true));
  expect(result.current.ownTurn).toBe(false);
  rerender({ current: { ...session, session: { ...session.session!, status: 'paused' } } });
  expect(result.current.ready).toBe(false);
});

it('retains the confirmation key and versions after a lost response and rate limit', async () => {
  const requests: RequestInit[] = [];
  const proposal = {
    id: 'p',
    character_id: 'c',
    availability: 'available' as const,
    selection: { ...selection, encounter_name: 'E', solution_name: 'S' },
  };
  const active: QueueState = {
    version: 2,
    queue: {
      encounter_id: 'e',
      participants: [{ guest_id: 'guest', character_id: 'c' }],
      round_order: ['guest'],
      round_number: 1,
      cursor: 0,
      skipped: [],
      current_guest_id: 'guest',
    },
  };
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/character')) return json({ id: 'c' });
      if (init?.method !== 'POST') return json({ version: 1, proposals: [proposal] });
      requests.push(init);
      if (requests.length === 1) throw new Error('lost');
      if (requests.length === 2) return new Response(null, { status: 429 });
      return json({
        result: {
          dice: [0, 0, 0, 0],
          characteristic: 4,
          skill: 1,
          modifier: 0,
          difficulty: 5,
          total: 5,
          success: true,
        },
        replayed: true,
      });
    }),
  );
  const confirmed = vi.fn();
  const { result } = renderHook(() =>
    useProposals('campaign', 'guest', active, vi.fn(), session, vi.fn(), 'open', confirmed),
  );
  await waitFor(() => expect(result.current.canConfirm(proposal)).toBe(true));
  act(() => result.current.execute('confirm', undefined, 'p'));
  await waitFor(() => expect(result.current.pending).not.toBeNull());
  act(() => result.current.retry());
  await waitFor(() => expect(requests).toHaveLength(2));
  await waitFor(() => expect(result.current.busy).toBe(false));
  act(() => result.current.retry());
  await waitFor(() => expect(confirmed).toHaveBeenCalledOnce());
  expect(requests).toHaveLength(3);
  for (const request of requests) {
    expect(request.headers).toEqual(requests[0].headers);
    expect(request.body).toEqual(requests[0].body);
  }
  expect(sessionStorage.length).toBe(0);
});
