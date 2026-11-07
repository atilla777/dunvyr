import { useCallback, useEffect, useState, type FormEvent } from 'react';
import {
  createCharacter,
  fetchCharacter,
  fetchCharacterTemplates,
  type Character,
  type CharacterTemplates,
} from './api';

export function CharacterPanel({ campaignId }: { campaignId: string }) {
  const [character, setCharacter] = useState<Character | null>(null);
  const [templates, setTemplates] = useState<CharacterTemplates | null>(null);
  const [name, setName] = useState('');
  const [appearance, setAppearance] = useState('');
  const [archetype, setArchetype] = useState('');
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
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      setCharacter(await createCharacter(campaignId, name, appearance, archetype));
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
                {key}: {value}
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
              onChange={(event) => setArchetype(event.target.value)}
            >
              <option value="">Выберите архетип</option>
              {templates.archetypes.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" disabled={busy}>
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
