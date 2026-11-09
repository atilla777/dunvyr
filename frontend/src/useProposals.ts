import { useCallback, useEffect, useState } from 'react';
import { createIdempotencyKey, fetchCharacter, type Character } from './api';
import { isQueueState, type GameSessionState, type QueueState } from './chat';
import type { ChatConnectionStatus } from './chatSocket';

export type Selection = { encounter_id: string; object_id: string; solution_id: string };
export type Proposal = {
  id: string;
  character_id: string;
  availability: 'available' | 'unavailable';
  selection: (Selection & { encounter_name: string; solution_name: string }) | null;
};
export type ProposalState = { version: number; proposals: Proposal[] };
export function newerProposals(current: ProposalState | null, next: ProposalState): ProposalState {
  return current === null || next.version > current.version ? next : current;
}
type Command = { suffix: string; body: object; key: string };

export function useProposals(
  campaignId: string,
  guestId: string,
  queue: QueueState | null,
  acceptQueue: (value: QueueState) => void,
  session: GameSessionState | null,
  refreshSession: () => Promise<boolean>,
  connection: ChatConnectionStatus,
) {
  const [state, setState] = useState<ProposalState | null>(null);
  const [character, setCharacter] = useState<Character | null>(null);
  const [pending, setPending] = useState<Command | null>(null);
  const [busy, setBusy] = useState(false);
  const [stale, setStale] = useState(false);
  const [error, setError] = useState('');
  const url = `/api/campaigns/${encodeURIComponent(campaignId)}/proposals`;
  const refresh = useCallback(async () => {
    try {
      const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store' });
      if (!response.ok) throw new Error();
      const next = (await response.json()) as ProposalState;
      if (!Number.isSafeInteger(next.version) || !Array.isArray(next.proposals)) throw new Error();
      setState((current) => newerProposals(current, next));
      return true;
    } catch {
      setError('Не удалось загрузить предложения.');
      return false;
    }
  }, [url]);
  useEffect(() => {
    void Promise.resolve().then(refresh);
    void fetchCharacter(campaignId)
      .then(setCharacter)
      .catch(() => setError('Не удалось загрузить персонажа.'));
  }, [campaignId, refresh]);
  const ready =
    connection === 'open' &&
    session?.session?.status === 'running' &&
    queue !== null &&
    state !== null &&
    !stale &&
    character !== null;
  const ownTurn = ready && queue.queue?.current_guest_id === guestId;
  async function send(command: Command) {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      const response = await fetch(`${url}${command.suffix}`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': command.key },
        body: JSON.stringify(command.body),
      });
      if (response.status === 409) {
        setPending(null);
        setStale(true);
        const results = await Promise.allSettled([
          refresh(),
          refreshSession(),
          fetch(`/api/campaigns/${encodeURIComponent(campaignId)}/queue`, {
            credentials: 'same-origin',
          }).then(async (r) => {
            if (!r.ok) throw new Error();
            const data: unknown = await r.json();
            if (!isQueueState(data)) throw new Error();
            acceptQueue(data);
          }),
        ]);
        const failed = results.some(
          (result) =>
            result.status === 'rejected' ||
            (result.status === 'fulfilled' && result.value === false),
        );
        if (!failed) setStale(false);
        setError(
          failed
            ? 'Состояние изменилось, но обновить его не удалось. Обновите страницу.'
            : 'Состояние изменилось. Проверьте его и повторите действие.',
        );
      } else if (response.status === 429) {
        const retryAfter = response.headers.get('Retry-After');
        setPending(command);
        setError(
          `Слишком много попыток. Повторите тот же запрос позже${retryAfter && /^\d+$/.test(retryAfter) ? ` (через ${retryAfter} сек.)` : ''}.`,
        );
      } else if (response.status >= 500) throw new Error();
      else if (!response.ok) {
        setPending(null);
        setError('Не удалось сохранить предложение. Проверьте доступ и состояние встречи.');
      } else {
        const next = (await response.json()) as ProposalState;
        if (!Number.isSafeInteger(next.version) || !Array.isArray(next.proposals))
          throw new Error();
        setState((current) => newerProposals(current, next));
        setPending(null);
      }
    } catch {
      setPending(command);
      setError('Результат запроса неизвестен. Повторите тот же запрос.');
    } finally {
      setBusy(false);
    }
  }
  function execute(action: 'create' | 'edit' | 'cancel', selection?: Selection, id?: string) {
    if (
      !ready ||
      busy ||
      pending ||
      !state ||
      !session ||
      !queue ||
      !character ||
      (action !== 'create' && !ownTurn)
    )
      return;
    const body = {
      expected_version: state.version,
      expected_queue_version: queue.version,
      expected_lifecycle_revision: session.revision,
      ...(action === 'create' ? { character_id: character.id } : {}),
      ...(selection ?? {}),
    };
    void send({
      suffix: action === 'create' ? '' : `/${encodeURIComponent(id!)}/${action}`,
      body,
      key: createIdempotencyKey(),
    });
  }
  return {
    state,
    character,
    setCharacter,
    refresh,
    ready: !!ready && !busy && !pending,
    ownTurn: !!ownTurn && !busy && !pending,
    pending,
    busy,
    error,
    execute,
    retry: () => {
      if (pending) void send(pending);
    },
  };
}
