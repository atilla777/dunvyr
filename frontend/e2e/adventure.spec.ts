import { expect, test, type Page } from '@playwright/test';

async function loginWithRateLimit(page: Page, nickname: string) {
  await page.getByLabel('Псевдоним').fill(nickname);
  while (true) {
    const responsePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith('/api/identity/sessions') && response.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Войти' }).click();
    const response = await responsePromise;
    if (response.status() !== 429) {
      expect(response.ok()).toBeTruthy();
      return;
    }
    const seconds = Number(response.headers()['retry-after']);
    expect(seconds).toBeGreaterThan(0);
    await page.waitForTimeout((seconds + 1) * 1000);
  }
}

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
    await expect(guest.getByLabel('Имя персонажа')).toBeVisible({ timeout: 15000 });
    await guest.getByLabel('Имя персонажа').fill('Разведчица');
    await guest.getByLabel('Внешность').fill('Синяя куртка');
    await guest.getByLabel('Архетип').selectOption('scout');
    await guest.route('**/api/campaigns/*/character', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({ status: 429, json: { detail: 'rate_limited' } });
      } else {
        await route.continue();
      }
    });
    await guest.getByRole('button', { name: 'Создать персонажа' }).click();
    await expect(guest.getByRole('alert')).toContainText('Слишком много попыток');
    await expect(guest.getByLabel('Имя персонажа')).toHaveValue('Разведчица');
    await guest.unroute('**/api/campaigns/*/character');
    await guest.getByRole('button', { name: 'Создать персонажа' }).click();
    await expect(guest.getByRole('heading', { name: 'Разведчица' })).toBeVisible();
    await expect(draft).toHaveValue('Черновик');
    await expect(page.getByLabel('Имя персонажа')).toBeVisible({ timeout: 15000 });
    await page.getByLabel('Имя персонажа').fill('Инженер');
    await page.getByLabel('Внешность').fill('Красный плащ');
    await page.getByLabel('Архетип').selectOption('engineer');
    await page.getByRole('button', { name: 'Создать персонажа' }).click();
    await expect(page.getByRole('heading', { name: 'Инженер', exact: true })).toBeVisible();
    await expect(guest.getByRole('button', { name: /Выбрать/ })).toHaveCount(0);
    await guest.reload();
    await expect(guest.getByText(/Версия: [a-f0-9]{64}/)).toBeVisible();
    await expect(guest.getByText('Чат на связи')).toBeVisible();
    await expect(guest.getByRole('heading', { name: 'Разведчица' })).toBeVisible();
  } finally {
    await participant.close();
  }
});

test('два настроенных персонажа и чат сохраняются после перезагрузки', async ({
  browser,
  page,
}) => {
  test.setTimeout(120_000);
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
    await loginWithRateLimit(page, 'Алиса');
    await page.getByLabel('Название кампании').fill('Настроенная команда');
    await page.getByRole('button', { name: 'Создать кампанию' }).click();
    const invitation = await page.getByRole('link').getAttribute('href');
    expect(invitation).not.toBeNull();
    const guest = await participant.newPage();
    await guest.goto(invitation!);
    await loginWithRateLimit(guest, 'Боб');
    await guest.getByRole('button', { name: 'Присоединиться' }).click();
    await page.getByRole('button', { name: 'Выбрать Последняя смена' }).click();
    await page.getByLabel('Имя персонажа').fill('Мастер');
    await page.getByLabel('Внешность').fill('Красный плащ');
    await page.getByLabel('Архетип').selectOption('engineer');
    await page.getByLabel('Сила').fill('1');
    await page.getByLabel('Ловкость').fill('3');
    await page.getByLabel('Ремонт').fill('2');
    await page.getByLabel('Скрытность').fill('1');
    await page.getByRole('button', { name: 'Создать персонажа' }).click();
    await expect(page.getByRole('heading', { name: 'Мастер' })).toBeVisible();
    await expect(guest.getByLabel('Имя персонажа')).toBeVisible({ timeout: 15000 });
    await guest.getByLabel('Имя персонажа').fill('Следопыт');
    await guest.getByLabel('Внешность').fill('Синяя куртка');
    await guest.getByLabel('Архетип').selectOption('scout');
    await guest.getByLabel('Сила').fill('1');
    await guest.getByLabel('Ловкость').fill('5');
    await guest.getByLabel('Скрытность').fill('2');
    await guest.getByLabel('Ремонт').fill('1');
    await guest.getByRole('button', { name: 'Создать персонажа' }).click();
    await expect(guest.getByRole('heading', { name: 'Следопыт' })).toBeVisible();
    await page.getByLabel('Сообщение').fill('Готовы к вылазке');
    await page.getByRole('button', { name: 'Отправить' }).click();
    await expect(guest.getByText('Готовы к вылазке')).toBeVisible();
    await guest.getByLabel('Сообщение').fill('Вперёд');
    await guest.getByRole('button', { name: 'Отправить' }).click();
    await expect(page.getByText('Вперёд')).toBeVisible();
    await page.reload();
    await guest.reload();
    await expect(page.getByRole('heading', { name: 'Мастер' })).toBeVisible();
    await expect(page.getByText('Ловкость: 3')).toBeVisible();
    await expect(guest.getByRole('heading', { name: 'Следопыт' })).toBeVisible();
    await expect(guest.getByText('Ловкость: 5')).toBeVisible();
    await expect(guest.getByText('Готовы к вылазке')).toBeVisible();
    await expect(page.getByText('Вперёд')).toBeVisible();
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
