import { useRef, useState } from 'react';

import { retryNarration } from './api';
import type { NarrationState } from './chat';

export function NarrationEntry({
  campaignId,
  narration,
  onRefresh,
}: {
  campaignId: string;
  narration: NarrationState;
  onRefresh: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const retryKey = useRef({ revision: narration.revision, key: crypto.randomUUID() });
  async function retry() {
    if (busy) return;
    if (retryKey.current.revision !== narration.revision)
      retryKey.current = { revision: narration.revision, key: crypto.randomUUID() };
    setBusy(true);
    setError(null);
    try {
      await retryNarration(campaignId, narration, retryKey.current.key);
      await onRefresh();
    } catch {
      setError('Не удалось повторить описание. Подождите 10 секунд и попробуйте снова.');
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="chat__narration" aria-live="polite">
      <strong>Ведущий</strong>
      {narration.state === 'ready' ? (
        <p className="chat__text">{narration.text}</p>
      ) : narration.state === 'failed' ? (
        <>
          <p>Описание недоступно. Результат действия сохранён — игру можно продолжить.</p>
          <button type="button" disabled={busy} onClick={() => void retry()}>
            {busy ? 'Повторяем описание…' : 'Повторить описание'}
          </button>
        </>
      ) : (
        <p>
          {narration.state === 'pending'
            ? 'Описание ожидает очереди…'
            : 'Ведущий готовит описание…'}
        </p>
      )}
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
