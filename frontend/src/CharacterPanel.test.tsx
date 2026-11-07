import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { CharacterPanel } from './CharacterPanel';

const character = {
  id: '1',
  name: 'Ада',
  appearance: 'Плащ',
  archetype_id: 'engineer',
  archetype_name: 'Инженер',
  characteristics: { intellect: 4 },
  skills: [{ id: 'repair', name: 'Ремонт', value: 3 }],
};

const templates = {
  status: 'ready',
  archetypes: [
    {
      id: 'engineer',
      name: 'Инженер',
      characteristics: { strength: 2, agility: 2, intellect: 4, presence: 1 },
      skills: [
        { skill_id: 'repair', value: 3 },
        { skill_id: 'hacking', value: 2 },
      ],
      budget: 23,
    },
    {
      id: 'scout',
      name: 'Разведчик',
      characteristics: { strength: 2, agility: 4, intellect: 2, presence: 1 },
      skills: [{ skill_id: 'repair', value: 1 }],
      budget: 19,
    },
  ],
  skills: [
    { id: 'repair', name: 'Ремонт', characteristic: 'intellect' },
    { id: 'hacking', name: 'Взлом', characteristic: 'intellect' },
    { id: 'stealth', name: 'Скрытность', characteristic: 'agility' },
  ],
  creation_rules: {
    id: 'archetype-budget-v1',
    minimum: 0,
    maximum: 10,
    relative_limit: 1,
    characteristic_cost: 2,
    skill_cost: 1,
  },
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it('creates a customized character and displays the server card', async () => {
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith('character-templates')) return Response.json(templates);
    if (init?.method === 'POST') return Response.json(character, { status: 201 });
    return Response.json(null);
  });
  vi.stubGlobal('fetch', fetcher);
  render(<CharacterPanel campaignId="campaign" />);
  fireEvent.change(await screen.findByLabelText('Имя персонажа'), { target: { value: 'Ада' } });
  fireEvent.change(screen.getByLabelText('Внешность'), { target: { value: 'Плащ' } });
  fireEvent.change(screen.getByLabelText('Архетип'), { target: { value: 'engineer' } });
  fireEvent.change(screen.getByLabelText('Сила'), { target: { value: '1' } });
  fireEvent.change(screen.getByLabelText('Ловкость'), { target: { value: '3' } });
  fireEvent.change(screen.getByLabelText('Ремонт'), { target: { value: '2' } });
  fireEvent.change(screen.getByLabelText('Скрытность'), { target: { value: '1' } });
  expect(screen.getByText('Потрачено: 23 / Бюджет: 23 / Осталось: 0')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Создать персонажа' }));
  expect(await screen.findByRole('heading', { name: 'Ада' })).toBeInTheDocument();
  expect(screen.getByText('Ремонт: 3')).toBeInTheDocument();
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(3));
  const request = fetcher.mock.calls[2][1];
  expect(JSON.parse(String(request?.body))).toEqual({
    name: 'Ада',
    appearance: 'Плащ',
    archetype_id: 'engineer',
    allocation: {
      characteristics: { strength: 1, agility: 3, intellect: 4, presence: 1 },
      skills: { repair: 2, hacking: 2, stealth: 1 },
    },
  });
  expect(screen.queryByLabelText('Сила')).not.toBeInTheDocument();
});

it('shows a creation error and retains the draft for retry', async () => {
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith('character-templates')) return Response.json(templates);
    if (init?.method === 'POST') return Response.json({ detail: 'rate_limited' }, { status: 429 });
    return Response.json(null);
  });
  vi.stubGlobal('fetch', fetcher);
  render(<CharacterPanel campaignId="campaign" />);
  fireEvent.change(await screen.findByLabelText('Имя персонажа'), { target: { value: 'Ада' } });
  fireEvent.change(screen.getByLabelText('Внешность'), { target: { value: 'Плащ' } });
  fireEvent.change(screen.getByLabelText('Архетип'), { target: { value: 'engineer' } });
  fireEvent.change(screen.getByLabelText('Сила'), { target: { value: '1' } });
  fireEvent.click(screen.getByRole('button', { name: 'Создать персонажа' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Слишком много попыток');
  expect(screen.getByLabelText('Имя персонажа')).toHaveValue('Ада');
  expect(screen.getByLabelText('Внешность')).toHaveValue('Плащ');
  expect(screen.getByLabelText('Архетип')).toHaveValue('engineer');
  expect(screen.getByLabelText('Сила')).toHaveValue(1);
});

it('enforces control bounds, displays immutable bindings and disables overspending', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) =>
      url.endsWith('character-templates') ? Response.json(templates) : Response.json(null),
    ),
  );
  render(<CharacterPanel campaignId="campaign" />);
  fireEvent.change(await screen.findByLabelText('Архетип'), { target: { value: 'engineer' } });
  const strength = screen.getByLabelText('Сила');
  expect(strength).toHaveAttribute('min', '1');
  expect(strength).toHaveAttribute('max', '3');
  expect(screen.getByLabelText('Скрытность')).toHaveAttribute('min', '0');
  expect(screen.getByLabelText('Скрытность')).toHaveAttribute('max', '1');
  expect(screen.getAllByText('Характеристика: Интеллект')).toHaveLength(2);
  fireEvent.change(strength, { target: { value: '4' } });
  expect(strength).toHaveValue(2);
  fireEvent.change(strength, { target: { value: '3' } });
  expect(screen.getByRole('alert')).toHaveTextContent('Превышен бюджет');
  expect(screen.getByRole('button', { name: 'Создать персонажа' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Сбросить распределение' }));
  expect(strength).toHaveValue(2);
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

it('resets allocation on archetype change while preserving text', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) =>
      url.endsWith('character-templates') ? Response.json(templates) : Response.json(null),
    ),
  );
  render(<CharacterPanel campaignId="campaign" />);
  fireEvent.change(await screen.findByLabelText('Имя персонажа'), { target: { value: 'Ада' } });
  fireEvent.change(screen.getByLabelText('Внешность'), { target: { value: 'Плащ' } });
  fireEvent.change(screen.getByLabelText('Архетип'), { target: { value: 'engineer' } });
  fireEvent.change(screen.getByLabelText('Сила'), { target: { value: '1' } });
  fireEvent.change(screen.getByLabelText('Архетип'), { target: { value: 'scout' } });
  expect(screen.getByLabelText('Сила')).toHaveValue(2);
  expect(screen.getByLabelText('Ловкость')).toHaveValue(4);
  expect(screen.getByLabelText('Имя персонажа')).toHaveValue('Ада');
  expect(screen.getByLabelText('Внешность')).toHaveValue('Плащ');
});
