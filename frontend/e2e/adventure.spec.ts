import { expect, test } from '@playwright/test';

test('организатор выбирает приключение, участник видит версию и сохраняет черновик', async ({
  browser,
  page,
}) => {
  const settings = test.info().project.use;
  const participant = await browser.newContext({
    viewport: settings.viewport,
    userAgent: settings.userAgent,
    deviceScaleFactor: settings.deviceScaleFactor,
    isMobile: settings.isMobile,
    hasTouch: settings.hasTouch,
  });
  try {
    await page.goto('/');
    await page.getByLabel('Псевдоним').fill('Организатор');
    await page.getByRole('button', { name: 'Войти' }).click();
    await page.getByLabel('Название кампании').fill('Приключение');
    await page.getByRole('button', { name: 'Создать кампанию' }).click();
    const url = await page.getByRole('link').getAttribute('href');
    expect(url).not.toBeNull();
    const guest = await participant.newPage();
    await guest.goto(url!);
    await guest.getByLabel('Псевдоним').fill('Участник');
    await guest.getByRole('button', { name: 'Войти' }).click();
    await guest.getByRole('button', { name: 'Присоединиться' }).click();
    await expect(guest.getByText(/Ожидаем выбора/)).toBeVisible();
    await expect(guest.getByText('Чат на связи')).toBeVisible();
    const draft = guest.getByLabel('Сообщение');
    await draft.fill('Черновик');
    await draft.focus();
    await page.getByRole('button', { name: 'Выбрать Последняя смена' }).click();
    await expect(page.getByText(/Версия: [a-f0-9]{64}/)).toBeVisible();
    await expect(guest.getByText(/Версия: [a-f0-9]{64}/)).toBeVisible({ timeout: 15000 });
    await expect(draft).toHaveValue('Черновик');
    await expect(draft).toBeFocused();
    await expect(guest.getByRole('button', { name: /Выбрать/ })).toHaveCount(0);
    await guest.reload();
    await expect(guest.getByText(/Версия: [a-f0-9]{64}/)).toBeVisible();
    await expect(guest.getByText('Чат на связи')).toBeVisible();
  } finally {
    await participant.close();
  }
});

test('ошибка загрузки приключения позволяет повторить запрос', async ({ page }) => {
  await page.route('**/api/campaigns/*/adventure', async (route) => {
    await route.fulfill({ status: 503, json: { detail: 'unavailable' } });
  });
  await page.goto('/');
  await page.getByLabel('Псевдоним').fill('Алиса');
  await page.getByRole('button', { name: 'Войти' }).click();
  await page.getByLabel('Название кампании').fill('Ошибка');
  await page.getByRole('button', { name: 'Создать кампанию' }).click();
  await expect(page.getByRole('alert')).toContainText('Не удалось загрузить');
  await page.unroute('**/api/campaigns/*/adventure');
  await page.getByRole('button', { name: 'Обновить' }).click();
  await expect(page.getByRole('button', { name: 'Выбрать Последняя смена' })).toBeVisible();
});
