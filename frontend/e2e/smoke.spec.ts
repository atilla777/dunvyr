import { expect, test } from '@playwright/test';

// Mirrors DUNVYR_E2E_BACKEND_PORT of playwright.config.ts: /health lives on the
// backend, while the test baseURL points at the Vite dev server.
const backendPort = process.env.DUNVYR_E2E_BACKEND_PORT?.trim() || '8100';
const healthURL = `http://127.0.0.1:${backendPort}/health`;

test('главная страница отвечает и backend health работает', async ({ page, request }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1, name: 'Dunvyr' })).toBeVisible();

  const response = await request.get(healthURL);
  expect(response.status()).toBe(200);
  const health = (await response.json()) as { status?: string };
  expect(health.status).toBe('ok');
});
