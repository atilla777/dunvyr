import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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

afterEach(() => vi.unstubAllGlobals());

it('creates and displays the server card without sending numbers', async () => {
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith('character-templates'))
      return Response.json({ status: 'ready', archetypes: [{ id: 'engineer', name: 'Инженер' }] });
    if (init?.method === 'POST') return Response.json(character, { status: 201 });
    return Response.json(null);
  });
  vi.stubGlobal('fetch', fetcher);
  render(<CharacterPanel campaignId="campaign" />);
  fireEvent.change(await screen.findByLabelText('Имя персонажа'), { target: { value: 'Ада' } });
  fireEvent.change(screen.getByLabelText('Внешность'), { target: { value: 'Плащ' } });
  fireEvent.change(screen.getByLabelText('Архетип'), { target: { value: 'engineer' } });
  fireEvent.click(screen.getByRole('button', { name: 'Создать персонажа' }));
  expect(await screen.findByRole('heading', { name: 'Ада' })).toBeInTheDocument();
  expect(screen.getByText('Ремонт: 3')).toBeInTheDocument();
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(3));
  const request = fetcher.mock.calls[2][1];
  expect(JSON.parse(String(request?.body))).toEqual({
    name: 'Ада',
    appearance: 'Плащ',
    archetype_id: 'engineer',
  });
});

it('shows a creation error and retains the draft for retry', async () => {
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith('character-templates'))
      return Response.json({ status: 'ready', archetypes: [{ id: 'engineer', name: 'Инженер' }] });
    if (init?.method === 'POST') return Response.json({ detail: 'rate_limited' }, { status: 429 });
    return Response.json(null);
  });
  vi.stubGlobal('fetch', fetcher);
  render(<CharacterPanel campaignId="campaign" />);
  fireEvent.change(await screen.findByLabelText('Имя персонажа'), { target: { value: 'Ада' } });
  fireEvent.change(screen.getByLabelText('Внешность'), { target: { value: 'Плащ' } });
  fireEvent.change(screen.getByLabelText('Архетип'), { target: { value: 'engineer' } });
  fireEvent.click(screen.getByRole('button', { name: 'Создать персонажа' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Слишком много попыток');
  expect(screen.getByLabelText('Имя персонажа')).toHaveValue('Ада');
});
