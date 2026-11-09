import { useCallback, useEffect, useState } from 'react';
import {
  createIdempotencyKey,
  fetchCharacter,
  fetchEncounterCatalog,
  type CampaignMember,
  type Character,
  type EncounterCatalogState,
} from './api';
import { isQueueState, type GameSessionState, type PresenceState, type QueueState } from './chat';
import type { ChatConnectionStatus } from './chatSocket';

interface Props {
  campaignId: string;
  currentGuestId: string;
  members: CampaignMember[];
  state: QueueState | null;
  accept: (state: QueueState) => void;
  session: GameSessionState | null;
  presence: PresenceState | null;
  connection: ChatConnectionStatus;
}

export function QueuePanel({
  campaignId,
  currentGuestId,
  members,
  state,
  accept,
  session,
  presence,
  connection,
}: Props) {
  const [character, setCharacter] = useState<Character | null>(null);
  const [catalog, setCatalog] = useState<EncounterCatalogState | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<{
    action: 'start' | 'swap';
    body: object;
    key: string;
  } | null>(null);
  const url = `/api/campaigns/${encodeURIComponent(campaignId)}/queue`;
  const refresh = useCallback(async () => {
    const response = await fetch(url, { credentials: 'same-origin' });
    if (!response.ok) throw new Error();
    const data: unknown = await response.json();
    if (!isQueueState(data)) throw new Error();
    accept(data);
  }, [url, accept]);
  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const [nextCharacter, nextCatalog] = await Promise.all([
          fetchCharacter(campaignId),
          fetchEncounterCatalog(campaignId),
        ]);
        if (active) {
          setCharacter(nextCharacter);
          setCatalog(nextCatalog);
        }
      } catch {
        if (active) setError('Не удалось загрузить персонажа или испытания.');
      }
    }
    void load();
    const timer = window.setInterval(() => void load(), 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [campaignId]);
  async function execute(action: 'start' | 'swap', body: object) {
    if (busy) return;
    const command = pending ?? { action, body, key: createIdempotencyKey() };
    setBusy(true);
    setError('');
    try {
      const response = await fetch(`${url}/${command.action}`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': command.key },
        body: JSON.stringify(command.body),
      });
      if (response.status === 409) {
        setPending(null);
        await refresh();
        setError('Состояние изменилось. Проверьте очередь и повторите действие.');
      } else if (response.status >= 500) throw new Error();
      else if (!response.ok) {
        setPending(null);
        setError(
          response.status === 403
            ? 'Нет доступа или персонаж недопустим.'
            : response.status === 429
              ? 'Слишком много попыток. Попробуйте позже.'
              : 'Не удалось изменить очередь.',
        );
      } else {
        const data: unknown = await response.json();
        if (!isQueueState(data)) throw new Error();
        accept(data);
        setPending(null);
      }
    } catch {
      setPending(command);
      setError('Результат запроса неизвестен. Повторите тот же запрос.');
    } finally {
      setBusy(false);
    }
  }
  const queue = state?.queue ?? null;
  const running = session?.session?.status === 'running';
  const ready = connection === 'open' && running && state !== null && session !== null;
  const name = (id: string) => members.find((member) => member.guest_id === id)?.nickname ?? id;
  return (
    <section className="queue-panel" aria-label="Очередь испытания">
      <h3>Очередь испытания</h3>
      {connection !== 'open' && <p>Состояние очереди синхронизируется.</p>}
      {session?.session?.status === 'paused' && <p>Встреча на паузе; очередь приостановлена.</p>}
      {session?.session?.status === 'ended' && (
        <p>Встреча завершена; очередь приостановлена до следующей встречи.</p>
      )}
      {state === null ? (
        <p>Загружаем очередь…</p>
      ) : queue === null ? (
        <>
          <p>Испытание ещё не начато.</p>
          {catalog?.status === 'ready' &&
            catalog.catalog.encounters.map((encounter) => (
              <button
                key={encounter.id}
                type="button"
                disabled={!ready || !character || busy || pending !== null}
                onClick={() =>
                  void execute('start', {
                    expected_version: state.version,
                    expected_lifecycle_revision: session!.revision,
                    character_id: character!.id,
                    encounter_id: encounter.id,
                  })
                }
              >
                Начать: {encounter.name}
              </button>
            ))}
          {!character && <p>Для начала нужен свой персонаж.</p>}
        </>
      ) : (
        <>
          <p>
            Испытание:{' '}
            {catalog?.status === 'ready'
              ? (catalog.catalog.encounters.find((item) => item.id === queue.encounter_id)?.name ??
                queue.encounter_id)
              : queue.encounter_id}
          </p>
          <p>Раунд: {queue.round_number}</p>
          <p>
            {queue.current_guest_id === null
              ? 'Ожидаем игроков в сети.'
              : `Сейчас: ${name(queue.current_guest_id)}`}
          </p>
          <ol>
            {queue.round_order.map((id, index) => (
              <li key={id}>
                {name(id)}
                {queue.skipped.includes(id)
                  ? ' — пропущен'
                  : index < queue.cursor
                    ? ' — уже прошёл'
                    : ''}
                {id === queue.current_guest_id ? ' — текущий' : ''}
                {ready &&
                  queue.current_guest_id === currentGuestId &&
                  index > queue.cursor &&
                  presence?.online_guest_ids.includes(id) && (
                    <button
                      type="button"
                      disabled={busy || pending !== null}
                      onClick={() =>
                        void execute('swap', {
                          expected_version: state.version,
                          expected_lifecycle_revision: session!.revision,
                          target_guest_id: id,
                        })
                      }
                    >
                      Обменяться с {name(id)}
                    </button>
                  )}
              </li>
            ))}
          </ol>
          <p>
            Участники:{' '}
            {queue.participants.map((participant) => name(participant.guest_id)).join(', ')}
          </p>
        </>
      )}
      <p>Выполнение действий пока недоступно.</p>
      {error && <p role="alert">{error}</p>}
      {pending && (
        <button
          type="button"
          disabled={busy || connection !== 'open'}
          onClick={() => void execute(pending.action, pending.body)}
        >
          Повторить запрос
        </button>
      )}
    </section>
  );
}
