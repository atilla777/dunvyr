import { expect, test } from '@playwright/test';
import { loginWithRateLimit } from './login';

test('два гостя видят жизненный цикл встречи и сохраняют чат', async ({ browser, page }) => {
  const use = test.info().project.use;
  const context = await browser.newContext({
    viewport: use.viewport,
    userAgent: use.userAgent,
    deviceScaleFactor: use.deviceScaleFactor,
    isMobile: use.isMobile,
    hasTouch: use.hasTouch,
  });
  let failed = false;
  try {
    const guest = await context.newPage();
    await page.goto('/');
    await loginWithRateLimit(page, 'Алиса');
    await page.getByLabel('Название кампании').fill('Встреча');
    await page.getByRole('button', { name: 'Создать кампанию' }).click();
    const invitation = await page.getByRole('link').getAttribute('href');
    expect(invitation).not.toBeNull();
    await guest.goto(invitation!);
    await loginWithRateLimit(guest, 'Боб');
    await guest.getByRole('button', { name: 'Присоединиться' }).click();
    await expect(guest.getByText('Чат на связи')).toBeVisible();
    await expect(page.getByText('Чат на связи')).toBeVisible();
    await page.getByLabel('Сообщение').fill('Привет');
    await page.getByRole('button', { name: 'Отправить' }).click();
    await expect(guest.getByText('Привет')).toBeVisible();
    await guest.getByLabel('Сообщение').fill('Черновик');
    for (const [action, status] of [
      ['Начать встречу', 'Встреча идёт'],
      ['Пауза', 'Встреча на паузе'],
      ['Продолжить встречу', 'Встреча идёт'],
      ['Завершить встречу', 'Встреча завершена'],
      ['Начать встречу', 'Встреча идёт'],
    ]) {
      await page.getByRole('button', { name: action }).click();
      await expect(page.getByText(status, { exact: true })).toBeVisible();
      await expect(guest.getByText(status, { exact: true })).toBeVisible();
      await expect(guest.getByLabel('Сообщение')).toHaveValue('Черновик');
    }
    await guest.reload();
    await expect(guest.getByText('Встреча идёт', { exact: true })).toBeVisible();
    await expect(guest.getByText('Привет')).toBeVisible();
    await expect(guest.getByRole('button', { name: 'Пауза' })).toHaveCount(0);
  } catch (error) {
    failed = true;
    throw error;
  } finally {
    try {
      await context.close();
    } catch (error) {
      if (!failed) throw error;
    }
  }
});
