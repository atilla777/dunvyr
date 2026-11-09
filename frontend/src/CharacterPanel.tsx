import { useCallback, useEffect, useState, type FormEvent } from 'react';
import {
  createCharacter,
  fetchCharacter,
  fetchCharacterTemplates,
  type Character,
  type CharacterAllocation,
  type CharacteristicId,
  type ArchetypeTemplate,
  type CharacterTemplates,
} from './api';

const characteristicNames: Record<CharacteristicId, string> = {
  strength: 'Сила',
  agility: 'Ловкость',
  intellect: 'Интеллект',
  presence: 'Влияние',
};
const characteristicIds = Object.keys(characteristicNames) as CharacteristicId[];

function initialAllocation(archetype: ArchetypeTemplate): CharacterAllocation {
  return {
    characteristics: { ...archetype.characteristics },
    skills: Object.fromEntries(archetype.skills.map((skill) => [skill.skill_id, skill.value])),
  };
}

export function CharacterPanel({
  campaignId,
  onCharacter,
}: {
  campaignId: string;
  onCharacter?: (character: Character) => void;
}) {
  const [character, setCharacter] = useState<Character | null>(null);
  const [templates, setTemplates] = useState<CharacterTemplates | null>(null);
  const [name, setName] = useState('');
  const [appearance, setAppearance] = useState('');
  const [archetype, setArchetype] = useState('');
  const [allocation, setAllocation] = useState<CharacterAllocation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const refresh = useCallback(async () => {
    try {
      const [current, available] = await Promise.all([
        fetchCharacter(campaignId),
        fetchCharacterTemplates(campaignId),
      ]);
      setCharacter((previous) => current ?? previous);
      setTemplates(available);
      setError('');
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : 'Не удалось загрузить персонажа.');
    }
  }, [campaignId]);
  useEffect(() => {
    void Promise.resolve().then(refresh);
  }, [refresh]);
  useEffect(() => {
    if (templates?.status !== 'waiting') return;
    const timer = window.setInterval(() => {
      void refresh();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [refresh, templates?.status]);
  const selected =
    templates?.status === 'ready'
      ? templates.archetypes.find((item) => item.id === archetype)
      : undefined;
  const rules = templates?.status === 'ready' ? templates.creation_rules : undefined;
  const spent =
    allocation && rules
      ? Object.values(allocation.characteristics).reduce((sum, value) => sum + value, 0) *
          rules.characteristic_cost +
        Object.values(allocation.skills).reduce((sum, value) => sum + value, 0) * rules.skill_cost
      : 0;
  const overBudget = selected !== undefined && spent > selected.budget;
  function selectArchetype(id: string) {
    setArchetype(id);
    const item =
      templates?.status === 'ready' ? templates.archetypes.find((a) => a.id === id) : undefined;
    setAllocation(item ? initialAllocation(item) : null);
  }
  function changeValue(
    kind: 'characteristics' | 'skills',
    id: string,
    raw: string,
    min: number,
    max: number,
  ) {
    if (raw === '') return;
    const value = Number(raw);
    if (!Number.isInteger(value) || value < min || value > max) return;
    setAllocation(
      (current) =>
        current && {
          ...current,
          [kind]: { ...current[kind], [id]: value },
        },
    );
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || !allocation || !selected || overBudget) return;
    setBusy(true);
    setError('');
    try {
      const created = await createCharacter(campaignId, name, appearance, archetype, allocation);
      setCharacter(created);
      onCharacter?.(created);
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : 'Не удалось создать персонажа.');
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="character" aria-labelledby="character-title">
      <h3 id="character-title">Ваш персонаж</h3>
      {error && (
        <div>
          <p role="alert">{error}</p>
          {templates === null && (
            <button type="button" onClick={() => void refresh()}>
              Повторить загрузку персонажа
            </button>
          )}
        </div>
      )}
      {character ? (
        <article>
          <h4>{character.name}</h4>
          <p>{character.archetype_name}</p>
          <p>{character.appearance}</p>
          <h5>Характеристики</h5>
          <ul>
            {Object.entries(character.characteristics).map(([key, value]) => (
              <li key={key}>
                {characteristicNames[key as CharacteristicId] ?? key}: {value}
              </li>
            ))}
          </ul>
          <h5>Навыки</h5>
          <ul>
            {character.skills.map((skill) => (
              <li key={skill.id}>
                {skill.name}: {skill.value}
              </li>
            ))}
          </ul>
        </article>
      ) : templates?.status === 'ready' ? (
        <form onSubmit={(event) => void submit(event)}>
          <label>
            Имя персонажа
            <input
              value={name}
              maxLength={60}
              required
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <label>
            Внешность
            <textarea
              value={appearance}
              maxLength={2000}
              required
              onChange={(event) => setAppearance(event.target.value)}
            />
          </label>
          <label>
            Архетип
            <select
              value={archetype}
              required
              onChange={(event) => selectArchetype(event.target.value)}
            >
              <option value="">Выберите архетип</option>
              {templates.archetypes.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          {selected && allocation && rules && templates.status === 'ready' && (
            <>
              <fieldset className="character__allocation">
                <legend>Характеристики</legend>
                {characteristicIds.map((id) => {
                  const baseline = selected.characteristics[id];
                  const min = Math.max(rules.minimum, baseline - rules.relative_limit);
                  const max = Math.min(rules.maximum, baseline + rules.relative_limit);
                  return (
                    <label key={id}>
                      {characteristicNames[id]}
                      <input
                        type="number"
                        min={min}
                        max={max}
                        step={1}
                        value={allocation.characteristics[id]}
                        onChange={(event) =>
                          changeValue('characteristics', id, event.target.value, min, max)
                        }
                      />
                    </label>
                  );
                })}
              </fieldset>
              <fieldset className="character__allocation">
                <legend>Навыки</legend>
                {templates.skills.map((skill) => {
                  const baseline =
                    selected.skills.find((item) => item.skill_id === skill.id)?.value ?? 0;
                  const min = Math.max(rules.minimum, baseline - rules.relative_limit);
                  const max = Math.min(rules.maximum, baseline + rules.relative_limit);
                  return (
                    <label key={skill.id}>
                      {skill.name}
                      <span>Характеристика: {characteristicNames[skill.characteristic]}</span>
                      <input
                        aria-label={skill.name}
                        type="number"
                        min={min}
                        max={max}
                        step={1}
                        value={allocation.skills[skill.id] ?? 0}
                        onChange={(event) =>
                          changeValue('skills', skill.id, event.target.value, min, max)
                        }
                      />
                    </label>
                  );
                })}
              </fieldset>
              <p>
                Потрачено: {spent} / Бюджет: {selected.budget} / Осталось: {selected.budget - spent}
              </p>
              {overBudget && <p role="alert">Превышен бюджет характеристик и навыков.</p>}
              <button type="button" onClick={() => setAllocation(initialAllocation(selected))}>
                Сбросить распределение
              </button>
            </>
          )}
          <button type="submit" disabled={busy || !allocation || overBudget}>
            {busy ? 'Создаём…' : 'Создать персонажа'}
          </button>
        </form>
      ) : templates?.status === 'waiting' ? (
        <p>Дождитесь выбора приключения организатором.</p>
      ) : (
        !error && <p>Загружаем персонажа…</p>
      )}
    </section>
  );
}
