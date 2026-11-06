import { useCallback, useEffect, useRef, useState } from 'react';

import {
  AdventureError,
  fetchAdventure,
  fetchAdventureCatalog,
  selectAdventure,
  type AdventureState,
  type CatalogAdventure,
} from './api';

export function AdventurePanel({
  campaignId,
  isOrganizer,
}: {
  campaignId: string;
  isOrganizer: boolean;
}) {
  const [state, setState] = useState<AdventureState | null>(null);
  const [catalog, setCatalog] = useState<CatalogAdventure[] | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);

  const refresh = useCallback(async () => {
    const request = ++generation.current;
    try {
      const current = await fetchAdventure(campaignId);
      if (request !== generation.current) return;
      setState(current);
      if (current.status === 'waiting' && isOrganizer) {
        const entries = await fetchAdventureCatalog(campaignId);
        if (request !== generation.current) return;
        setCatalog(entries);
      }
      setError('');
    } catch (problem) {
      if (request !== generation.current) return;
      setError(problem instanceof Error ? problem.message : 'Не удалось загрузить приключение.');
    }
  }, [campaignId, isOrganizer]);

  useEffect(() => {
    void Promise.resolve().then(refresh);
  }, [refresh]);
  useEffect(() => {
    if (state?.status !== 'waiting' || error || busy) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void refresh();
    }, 5000);
    const onVisibility = () => {
      if (document.visibilityState === 'visible') void refresh();
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [state?.status, refresh, error, busy]);

  async function choose(adventure: CatalogAdventure) {
    ++generation.current;
    setBusy(true);
    setError('');
    try {
      setState(await selectAdventure(campaignId, adventure));
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : 'Не удалось выбрать приключение.');
      if (
        problem instanceof AdventureError &&
        (problem.code === 'stale_fingerprint' || problem.code === 'adventure_conflict')
      ) {
        setCatalog(null);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="adventure" aria-labelledby="adventure-title">
      <h3 id="adventure-title" className="campaign__subtitle">
        Приключение
      </h3>
      {state === null && !error && <p>Загружаем приключение…</p>}
      {error && (
        <div>
          <p className="campaign__error" role="alert">
            {error}
          </p>
          <button type="button" className="campaign__copy" onClick={() => void refresh()}>
            Обновить
          </button>
        </div>
      )}
      {state?.status === 'pinned' && (
        <div>
          <p>
            <strong>{state.adventure.title}</strong>
          </p>
          <p>{state.adventure.description}</p>
          <p className="adventure__version">Версия: {state.adventure.fingerprint}</p>
        </div>
      )}
      {state?.status === 'waiting' && (
        <>
          <p>Ожидаем выбора приключения организатором.</p>
          {isOrganizer && catalog !== null && (
            <>
              <p>
                Выбор окончательный: изменить приключение или его версию для этой кампании нельзя.
              </p>
              {catalog.length === 0 && <p>Доступных приключений пока нет.</p>}
              {catalog.map((adventure) => (
                <article key={adventure.adventure_id} className="adventure__item">
                  <h4>{adventure.title}</h4>
                  <p>{adventure.description}</p>
                  <p>Редакция: {adventure.edition}</p>
                  <button
                    type="button"
                    className="campaign__copy"
                    disabled={busy}
                    onClick={() => void choose(adventure)}
                  >
                    Выбрать {adventure.title}
                  </button>
                </article>
              ))}
            </>
          )}
        </>
      )}
    </section>
  );
}
