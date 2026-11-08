import type { ChatConnectionStatus } from './chatSocket';
import type { useGameSession } from './useGameSession';

type SessionController = ReturnType<typeof useGameSession>;
export function GameSessionPanel({
  controller,
  organizer,
  connection,
}: {
  controller: SessionController;
  organizer: boolean;
  connection: ChatConnectionStatus;
}) {
  const { state, error, busy, pending, stale, execute, refresh } = controller;
  const status = state?.session?.status;
  const label =
    state === null
      ? 'Загружаем состояние встречи…'
      : status === 'running'
        ? 'Встреча идёт'
        : status === 'paused'
          ? 'Встреча на паузе'
          : status === 'ended'
            ? 'Встреча завершена'
            : 'Встреча ещё не началась';
  const disabled = busy || stale || state === null || connection !== 'open';
  return (
    <section aria-labelledby="session-title">
      <h3 id="session-title">Игровая встреча</h3>
      <p aria-live="polite">
        {label}
        {connection !== 'open' && state !== null
          ? ' (состояние может устареть: нет соединения)'
          : ''}
      </p>
      {error && <p role="alert">{error}</p>}
      {(state === null || stale) && error && (
        <button type="button" onClick={() => void refresh()}>
          Обновить состояние
        </button>
      )}
      {organizer &&
        (pending ? (
          <button type="button" disabled={disabled} onClick={() => void execute(pending.action)}>
            Повторить запрос
          </button>
        ) : (
          <>
            {(status === undefined || status === 'ended') && (
              <button type="button" disabled={disabled} onClick={() => void execute('start')}>
                Начать встречу
              </button>
            )}
            {status === 'running' && (
              <button type="button" disabled={disabled} onClick={() => void execute('pause')}>
                Пауза
              </button>
            )}
            {status === 'paused' && (
              <button type="button" disabled={disabled} onClick={() => void execute('resume')}>
                Продолжить встречу
              </button>
            )}
            {(status === 'running' || status === 'paused') && (
              <button type="button" disabled={disabled} onClick={() => void execute('end')}>
                Завершить встречу
              </button>
            )}
          </>
        ))}
    </section>
  );
}
