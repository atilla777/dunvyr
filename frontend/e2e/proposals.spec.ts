import { expect, test } from '@playwright/test';
import { loginWithRateLimit } from './login';

test('личные предложения сохраняются и изменяются на своём ходу', async ({ browser, page }) => {
  test.setTimeout(90000);
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
    await page.getByLabel('Название кампании').fill('Предложения');
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
    await expect(
      hostQueue.getByRole('button', { name: /Начать: Нестабильный терминал/ }),
    ).toBeEnabled({ timeout: 15000 });
    await hostQueue.getByRole('button', { name: /Начать: Нестабильный терминал/ }).click();
    await expect(guest.getByText('Сейчас: Алиса')).toBeVisible();
    const prepare = guest.getByRole('button', { name: /^Подготовить:/ }).first();
    await expect(prepare).toBeEnabled();
    await prepare.click();
    const panel = guest.getByRole('region', { name: 'Мои предложения' });
    await expect(panel.getByText(/Сохранено;/)).toHaveCount(1);
    await prepare.click();
    await expect(panel.getByText(/Сохранено;/)).toHaveCount(2);
    await expect(
      page.getByRole('region', { name: 'Мои предложения' }).getByText(/Сохранено;/),
    ).toHaveCount(0);
    await guest.reload();
    await expect(panel.getByText(/Сохранено;/)).toHaveCount(2);
    await hostQueue.getByRole('button', { name: 'Обменяться с Боб' }).click();
    await expect(guest.getByText('Сейчас: Боб')).toBeVisible();
    const otherTab = await participant.newPage();
    await otherTab.goto(guest.url());
    const otherPanel = otherTab.getByRole('region', { name: 'Мои предложения' });
    await expect(otherPanel.getByText(/Сохранено;/)).toHaveCount(2);
    const draft = guest.getByLabel('Сообщение');
    await draft.fill('Черновик остаётся');
    await draft.focus();
    const beforeEdit = await panel.locator('li').first().innerText();
    await otherPanel
      .getByRole('button', { name: /^Изменить на:/ })
      .first()
      .click();
    await expect
      .poll(async () => await panel.locator('li').first().innerText())
      .not.toEqual(beforeEdit);
    await expect(draft).toHaveValue('Черновик остаётся');
    await expect(draft).toBeFocused();
    await panel.getByRole('button', { name: 'Отменить предложение' }).last().click();
    await expect(panel.getByText(/Сохранено;/)).toHaveCount(1);
  } finally {
    await participant.close();
  }
});
