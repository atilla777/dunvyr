import { useEffect, useState } from 'react';

import { fetchEncounterCatalog, type EncounterCatalogState } from './api';

type View =
  | { campaignId: string; status: 'loading' | 'error' }
  | ({ campaignId: string } & EncounterCatalogState);

const characteristics: Record<string, string> = {
  strength: 'Сила',
  agility: 'Ловкость',
  intellect: 'Интеллект',
  presence: 'Присутствие',
};

export function EncounterCatalog({ campaignId }: { campaignId: string }) {
  const [view, setView] = useState<View>({ campaignId, status: 'loading' });
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      try {
        const result = await fetchEncounterCatalog(campaignId, controller.signal);
        if (controller.signal.aborted) return;
        setView({ campaignId, ...result });
        if (result.status === 'waiting') timer = setTimeout(() => void load(), 3000);
      } catch {
        if (!controller.signal.aborted) setView({ campaignId, status: 'error' });
      }
    }
    void load();
    return () => {
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [campaignId, retry]);

  const current: View = view.campaignId === campaignId ? view : { campaignId, status: 'loading' };
  return (
    <section className="encounter-catalog" aria-label="Испытания">
      <h3>Испытания</h3>
      {current.status === 'loading' && <p>Загружаем испытания…</p>}
      {current.status === 'waiting' && <p>Испытания появятся после выбора приключения.</p>}
      {current.status === 'error' && (
        <p role="alert">
          Не удалось загрузить испытания.{' '}
          <button
            type="button"
            onClick={() => {
              setView({ campaignId, status: 'loading' });
              setRetry((value) => value + 1);
            }}
          >
            Повторить
          </button>
        </p>
      )}
      {current.status === 'ready' && (
        <>
          {current.catalog.encounters.length === 0 ? (
            <p>Доступных испытаний нет.</p>
          ) : (
            <ul>
              {current.catalog.encounters.map((encounter) => (
                <li key={encounter.id}>
                  <h4>{encounter.name}</h4>
                  <p>{encounter.description}</p>
                  <ul>
                    {encounter.solutions.map((solution) => (
                      <li key={solution.id}>
                        <strong>{solution.name}</strong>
                        <p>{solution.description}</p>
                        <p>
                          Навык: {solution.check.skill_name} · Характеристика:{' '}
                          {characteristics[solution.check.characteristic] ??
                            solution.check.characteristic}{' '}
                          · Сложность: {solution.check.difficulty}
                        </p>
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          )}
          <p>Выполнение действий пока недоступно.</p>
        </>
      )}
    </section>
  );
}
