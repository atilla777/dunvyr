import { useCallback, useEffect, useRef, useState } from 'react';
import { createIdempotencyKey } from './api';
import { isGameSessionState, type GameSessionState } from './chat';

type Action = 'start' | 'pause' | 'resume' | 'end';
interface Command {
  action: Action;
  revision: number;
  sessionId: string | null;
  key: string;
}

export function newerSessionState(
  current: GameSessionState | null,
  incoming: GameSessionState,
): GameSessionState {
  return current === null || incoming.revision > current.revision ? incoming : current;
}

export function useGameSession(campaignId: string) {
  const [state, setState] = useState<GameSessionState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<Command | null>(null);
  const [stale, setStale] = useState(false);
  const active = useRef(true);
  const accept = useCallback(
    (next: GameSessionState) => setState((current) => newerSessionState(current, next)),
    [],
  );
  const url = `/api/campaigns/${encodeURIComponent(campaignId)}/game-session`;
  const refresh = useCallback(async () => {
    try {
      const response = await fetch(url, { credentials: 'same-origin' });
      if (!response.ok) throw new Error();
      const data: unknown = await response.json();
      if (!isGameSessionState(data)) throw new Error();
      if (active.current) {
        accept(data);
        setStale(false);
        setError(null);
      }
      return true;
    } catch {
      if (active.current) setError('Не удалось загрузить состояние встречи.');
      return false;
    }
  }, [url, accept]);
  useEffect(() => {
    active.current = true;
    void Promise.resolve().then(refresh);
    return () => {
      active.current = false;
    };
  }, [refresh]);

  async function execute(action: Action) {
    if (busy || state === null) return;
    const command = pending ?? {
      action,
      revision: state.revision,
      sessionId: state.session?.id ?? null,
      key: createIdempotencyKey(),
    };
    setBusy(true);
    setError(null);
    try {
      const suffix =
        command.action === 'start'
          ? 'start'
          : `${encodeURIComponent(command.sessionId!)}/${command.action}`;
      const response = await fetch(`${url}/${suffix}`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': command.key },
        body: JSON.stringify({ expected_revision: command.revision }),
      });
      if (response.status === 409) {
        setPending(null);
        setStale(true);
        const refreshed = await refresh();
        if (active.current && refreshed)
          setError('Состояние встречи изменилось. Проверьте его и повторите действие.');
      } else if (response.status >= 500) {
        throw new Error('Uncertain server response');
      } else if (!response.ok) {
        setPending(null);
        setError(
          response.status === 403
            ? 'Нет прав управлять встречей.'
            : response.status === 404
              ? 'Кампания или встреча не найдена.'
              : response.status === 429
                ? 'Слишком много попыток. Попробуйте позже.'
                : 'Не удалось изменить встречу.',
        );
      } else {
        const data: unknown = await response.json();
        if (!isGameSessionState(data)) throw new Error();
        accept(data);
        setPending(null);
      }
    } catch {
      if (active.current) {
        setPending(command);
        setError('Результат запроса неизвестен. Повторите тот же запрос.');
      }
    } finally {
      if (active.current) setBusy(false);
    }
  }
  return { state, error, busy, pending, stale, accept, refresh, execute };
}
