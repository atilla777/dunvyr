import { useEffect, useState } from 'react';
import { fetchEncounterCatalog, type EncounterCatalogState } from './api';
import type { useProposals } from './useProposals';

export function ProposalsPanel({
  campaignId,
  controller,
}: {
  campaignId: string;
  controller: ReturnType<typeof useProposals>;
}) {
  const [catalog, setCatalog] = useState<EncounterCatalogState | null>(null);
  useEffect(() => {
    let active = true;
    const load = () =>
      void fetchEncounterCatalog(campaignId)
        .then((next) => {
          if (active) setCatalog(next);
        })
        .catch(() => {
          if (active) setCatalog(null);
        });
    load();
    const timer = window.setInterval(load, 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [campaignId]);
  return (
    <section aria-label="Мои предложения">
      <h3>Мои предложения</h3>
      {!controller.ready && (
        <p>Подготовка доступна при подключении, активной встрече и наличии персонажа.</p>
      )}
      {!controller.ownTurn && <p>Редактирование и отмена доступны только на вашем ходу.</p>}
      {controller.state === null ? (
        <p>Загружаем предложения…</p>
      ) : (
        <ul>
          {controller.state.proposals.map((proposal) => (
            <li key={proposal.id}>
              {proposal.selection ? (
                <p>
                  {proposal.selection.encounter_name} — {proposal.selection.solution_name}
                </p>
              ) : (
                <p>Предложение недоступно.</p>
              )}
              <p>Сохранено; перед выполнением потребуется повторная проверка.</p>
              {proposal.availability === 'available' && proposal.selection && (
                <button
                  type="button"
                  disabled={!controller.canConfirm(proposal)}
                  onClick={() => controller.execute('confirm', undefined, proposal.id)}
                >
                  Подтвердить и бросить
                </button>
              )}
              {proposal.availability === 'available' &&
                proposal.selection &&
                catalog?.status === 'ready' &&
                catalog.catalog.encounters
                  .filter(
                    (e) =>
                      e.id === proposal.selection?.encounter_id &&
                      e.object_id === proposal.selection?.object_id,
                  )
                  .flatMap((encounter) =>
                    encounter.solutions
                      .filter((solution) => solution.id !== proposal.selection?.solution_id)
                      .map((solution) => (
                        <button
                          key={solution.id}
                          type="button"
                          disabled={!controller.ownTurn}
                          onClick={() =>
                            controller.execute(
                              'edit',
                              {
                                encounter_id: encounter.id,
                                object_id: encounter.object_id,
                                solution_id: solution.id,
                              },
                              proposal.id,
                            )
                          }
                        >
                          Изменить на: {solution.name}
                        </button>
                      )),
                  )}
              <button
                type="button"
                disabled={!controller.ownTurn}
                onClick={() => controller.execute('cancel', undefined, proposal.id)}
              >
                Отменить предложение
              </button>
            </li>
          ))}
        </ul>
      )}
      {controller.error && <p role="alert">{controller.error}</p>}
      {controller.pending && (
        <button type="button" disabled={controller.busy} onClick={controller.retry}>
          Повторить запрос
        </button>
      )}
    </section>
  );
}
