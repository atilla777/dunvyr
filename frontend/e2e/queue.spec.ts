import { expect, test } from '@playwright/test';
import { loginWithRateLimit } from './login';

test('общая очередь, обмен, автопропуск и восстановление', async ({ browser, page }) => {
  test.setTimeout(90000);
  const settings = test.info().project.use;
  const options = {
    viewport: settings.viewport,
    userAgent: settings.userAgent,
    deviceScaleFactor: settings.deviceScaleFactor,
    isMobile: settings.isMobile,
    hasTouch: settings.hasTouch,
  };
  let participant = await browser.newContext(options);
  try {
    await page.goto('/');
    await loginWithRateLimit(page, 'Алиса');
    await page.getByLabel('Название кампании').fill('Очередь');
    await page.getByRole('button', { name: 'Создать кампанию' }).click();
    const invitation = await page.getByRole('link').getAttribute('href');
    const guest = await participant.newPage();
    await guest.goto(invitation!);
    await loginWithRateLimit(guest, 'Боб');
    await guest.getByRole('button', { name: 'Присоединиться' }).click();
    await page.getByRole('button', { name: 'Выбрать Последняя смена' }).click();
    for (const [viewer, name, archetype] of [
      [page, 'Инженер', 'engineer'],
      [guest, 'Разведчица', 'scout'],
    ] as const) {
      await viewer.getByLabel('Имя персонажа').fill(name, { timeout: 15000 });
      await viewer.getByLabel('Внешность').fill('Плащ');
      await viewer.getByLabel('Архетип').selectOption(archetype);
      await viewer.getByRole('button', { name: 'Создать персонажа' }).click();
      await expect(viewer.getByRole('heading', { name, exact: true })).toBeVisible();
    }
    await page.getByRole('button', { name: 'Начать встречу' }).click();
    const hostQueue = page.getByRole('region', { name: 'Очередь испытания' });
    const guestQueue = guest.getByRole('region', { name: 'Очередь испытания' });
    await expect(
      hostQueue.getByRole('button', { name: /Начать: Нестабильный терминал/ }),
    ).toBeEnabled({ timeout: 15000 });
    await hostQueue.getByRole('button', { name: /Начать: Нестабильный терминал/ }).click();
    await expect(guestQueue.getByText('Сейчас: Алиса')).toBeVisible();
    await hostQueue.getByRole('button', { name: 'Обменяться с Боб' }).click();
    await expect(guestQueue.getByText('Сейчас: Боб')).toBeVisible();
    const storageState = await participant.storageState();
    const guestUrl = guest.url();
    await participant.close();
    await expect(hostQueue.getByText('Сейчас: Алиса')).toBeVisible({ timeout: 20000 });
    await expect(hostQueue.getByText(/Боб — пропущен/)).toBeVisible();
    participant = await browser.newContext({ ...options, storageState });
    const returning = await participant.newPage();
    await returning.goto(guestUrl);
    const returningQueue = returning.getByRole('region', { name: 'Очередь испытания' });
    await expect(returningQueue.getByText('Сейчас: Алиса')).toBeVisible();
    await expect(returningQueue.getByText(/Боб — пропущен/)).toBeVisible();
    await returning.reload();
    await expect(returningQueue.getByText('Сейчас: Алиса')).toBeVisible();
    await expect(returningQueue.getByText(/Боб — пропущен/)).toBeVisible();
  } finally {
    await participant.close();
  }
});
