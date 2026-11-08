import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

import { SceneViewer } from './SceneViewer';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it('renders author text as text and offers the complete object list', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          status: 'ready',
          scene: {
            name: '<img src=x onerror=alert(1)>',
            description: '<script>bad()</script>',
            illustration: 'image',
            objects: [
              {
                id: 'box',
                name: 'Ящик',
                description: '<b>Текст</b>',
                hotspot: { x: 0, y: 0, width: 0.1, height: 0.1 },
              },
            ],
          },
        }),
        { status: 200 },
      ),
    ),
  );
  const { container } = render(<SceneViewer campaignId="c" />);
  expect(await screen.findAllByText('<script>bad()</script>')).not.toHaveLength(0);
  expect(container.querySelector('script')).toBeNull();
  const buttons = screen.getAllByRole('button', { name: 'Ящик' });
  fireEvent.click(buttons[buttons.length - 1]);
  expect(screen.getByText('<b>Текст</b>')).toBeInTheDocument();
  expect(container.querySelector('b')).toBeNull();
});

it('allows retry when loading fails', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: 'waiting', scene: null }), { status: 200 }),
      ),
  );
  render(<SceneViewer campaignId="c" />);
  fireEvent.click(await screen.findByRole('button', { name: 'Повторить' }));
  expect(await screen.findByText('Сцена появится после выбора приключения.')).toBeInTheDocument();
});
