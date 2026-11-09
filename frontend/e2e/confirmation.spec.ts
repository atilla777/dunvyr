import { expect, test } from '@playwright/test';
import { loginWithRateLimit } from './login';

test('два участника видят результат и последствия после перезагрузки', async ({
  browser,
  page,
}) => {
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
    await page.getByLabel('Название кампании').fill('Проверка');
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
    const queue = page.getByRole('region', { name: 'Очередь испытания' });
    await queue.getByRole('button', { name: /Начать: Нестабильный терминал/ }).click();
    const prepare = page.getByRole('button', { name: /^Подготовить:/ }).first();
    await expect(prepare).toBeEnabled();
    await prepare.click();
    await page.getByLabel('Сообщение').fill('Перед проверкой');
    await page.getByRole('button', { name: 'Отправить' }).click();
    await expect(guest.getByText('Перед проверкой')).toBeVisible();
    const draft = guest.getByLabel('Сообщение');
    await draft.fill('Черновик остаётся');
    await draft.focus();
    await page.getByRole('button', { name: 'Подтвердить и бросить' }).click();
    for (const viewer of [page, guest]) {
      const result = viewer.getByRole('region', { name: 'Результат проверки' });
      await expect(result).toContainText(/Успех|Неудача/);
      await expect(result).toContainText('Кубики:');
      await expect(
        viewer.locator('p:visible').filter({ hasText: /Цель: .*осмотр/i }),
      ).toBeVisible();
    }
    await expect(draft).toHaveValue('Черновик остаётся');
    await expect(draft).toBeFocused();
    await page.getByLabel('Сообщение').fill('После проверки');
    await page.getByRole('button', { name: 'Отправить' }).click();
    const stream = guest.getByRole('list', { name: 'Сообщения чата' });
    await expect(stream.getByText('После проверки')).toBeVisible();
    const assertOrder = async () => {
      const items = await stream.getByRole('listitem').allTextContents();
      const before = items.findIndex((item) => item.includes('Перед проверкой'));
      const check = items.findIndex((item) => item.includes('Проверка:'));
      const after = items.findIndex((item) => item.includes('После проверки'));
      expect(before).toBeGreaterThanOrEqual(0);
      expect(check).toBeGreaterThan(before);
      expect(after).toBeGreaterThan(check);
      expect(items[check]).toContain('Кубики:');
      expect(items[check]).not.toContain('terminal-diagnostics-success');
    };
    await assertOrder();
    await guest.reload();
    await expect(guest.getByRole('region', { name: 'Результат проверки' })).toContainText(
      'Кубики:',
    );
    await expect(guest.locator('p:visible').filter({ hasText: /Цель: .*осмотр/i })).toBeVisible();
    await expect(stream.getByText('После проверки')).toBeVisible();
    await assertOrder();
    await guest.getByLabel('Сообщение').fill('Продолжаем');
    await guest.getByRole('button', { name: 'Отправить' }).click();
    await expect(page.getByText('Продолжаем')).toBeVisible();
  } finally {
    await participant.close();
  }
});
