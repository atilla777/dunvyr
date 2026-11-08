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
    await draft.evaluate((input: HTMLTextAreaElement) => input.setSelectionRange(1, 4));
    await page.getByRole('button', { name: 'Выбрать Последняя смена' }).click();
    await expect(page.getByText(/Версия: [a-f0-9]{64}/)).toBeVisible();
    await expect(guest.getByText(/Версия: [a-f0-9]{64}/)).toBeVisible({ timeout: 15000 });
    await expect(draft).toHaveValue('Черновик');
    await expect(draft).toBeFocused();
    expect(
      await draft.evaluate((input: HTMLTextAreaElement) => [
        input.selectionStart,
        input.selectionEnd,
      ]),
    ).toEqual([1, 4]);
    await expect(page.getByRole('heading', { name: 'Приёмный шлюз' })).toBeVisible({
      timeout: 15000,
    });
    await expect(guest.getByRole('heading', { name: 'Приёмный шлюз' })).toBeVisible({
      timeout: 15000,
    });
    if (test.info().project.name === 'smoke-mobile') {
      await guest.getByRole('button', { name: 'Открыть сцену' }).click();
      const dialog = guest.getByRole('dialog', { name: 'Сцена: Приёмный шлюз' });
      await expect(dialog).toBeVisible();
      const image = dialog.getByRole('img', { name: 'Приёмный шлюз' });
      await expect
        .poll(() => image.evaluate((img: HTMLImageElement) => img.naturalWidth))
        .toBeGreaterThan(0);
      const close = dialog.getByRole('button', { name: 'Закрыть сцену' });
      await close.focus();
      await guest.keyboard.press('Tab');
      expect(await dialog.evaluate((element) => element.contains(document.activeElement))).toBe(
        true,
      );
      await guest.keyboard.press('Shift+Tab');
      await expect(close).toBeFocused();
      await guest.keyboard.press('Shift+Tab');
      expect(await dialog.evaluate((element) => element.contains(document.activeElement))).toBe(
        true,
      );
      await guest.keyboard.press('Tab');
      await expect(close).toBeFocused();
      await dialog.getByRole('button', { name: 'Увеличить' }).click();
      const viewport = dialog.getByLabel('Изображение сцены: прокрутка при увеличении');
      expect(await viewport.evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(
        true,
      );
      const bounds = await viewport.boundingBox();
      expect(bounds).not.toBeNull();
      const cdp = await participant.newCDPSession(guest);
      const y = bounds!.y + bounds!.height / 2;
      await cdp.send('Input.dispatchTouchEvent', {
        type: 'touchStart',
        touchPoints: [{ x: bounds!.x + bounds!.width * 0.8, y }],
      });
      await cdp.send('Input.dispatchTouchEvent', {
        type: 'touchMove',
        touchPoints: [{ x: bounds!.x + bounds!.width * 0.2, y }],
      });
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
      await expect
        .poll(() => viewport.evaluate((element) => element.scrollLeft))
        .toBeGreaterThan(0);
      await cdp.detach();
      const objects = dialog.getByRole('list');
      for (const name of ['Терминал', 'Шкаф', 'Гермодверь']) {
        const object = objects.getByRole('button', { name });
        await expect(object).toBeVisible();
        const size = await object.boundingBox();
        expect(size!.width).toBeGreaterThanOrEqual(44);
        expect(size!.height).toBeGreaterThanOrEqual(44);
      }
      await objects.getByRole('button', { name: 'Терминал' }).tap();
      await expect(dialog.getByLabel('Описание объекта')).toContainText(
        'Экран терминала ещё светится.',
      );
      expect(
        await guest.evaluate(
          () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
        ),
      ).toBe(true);
      await guest.keyboard.press('Escape');
      await expect(dialog).not.toBeVisible();
      await expect(guest.getByRole('button', { name: 'Открыть сцену' })).toBeFocused();
      await expect(draft).toHaveValue('Черновик');
      await draft.focus();
      expect(
        await draft.evaluate((input: HTMLTextAreaElement) => [
          input.selectionStart,
          input.selectionEnd,
        ]),
      ).toEqual([1, 4]);
    } else {
      const scene = guest.getByRole('region', { name: 'Сцена' });
      const image = scene.getByRole('img', { name: 'Приёмный шлюз' });
      await expect
        .poll(() => image.evaluate((img: HTMLImageElement) => img.naturalWidth))
        .toBeGreaterThan(0);
      const sceneBox = await scene.boundingBox();
      const chatBox = await guest.getByRole('region', { name: 'Чат' }).boundingBox();
      expect(sceneBox).not.toBeNull();
      expect(chatBox).not.toBeNull();
      expect(sceneBox!.x + sceneBox!.width).toBeLessThanOrEqual(chatBox!.x);
      expect(Math.max(sceneBox!.y, chatBox!.y)).toBeLessThan(
        Math.min(sceneBox!.y + sceneBox!.height, chatBox!.y + chatBox!.height),
      );
    }
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
    await expect(guest.getByRole('heading', { name: 'Приёмный шлюз' })).toBeVisible();
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
    await expect(page.getByRole('heading', { name: 'Приёмный шлюз' })).toBeVisible({
      timeout: 15000,
    });
    await expect(guest.getByRole('heading', { name: 'Приёмный шлюз' })).toBeVisible({
      timeout: 15000,
    });
    const draft = guest.getByLabel('Сообщение');
    await draft.fill('Сохранённый черновик');
    await draft.focus();
    if (test.info().project.name === 'smoke-mobile') {
      const opener = guest.getByRole('button', { name: 'Открыть карту' });
      await expect(opener).toBeVisible({ timeout: 15000 });
      await opener.tap();
      const map = guest.getByRole('dialog', { name: 'Карта группы' });
      await expect(map.getByText('Приёмный зал — обнаружено')).toBeVisible();
      await expect(map.getByText(/→ Неизвестная область/)).toBeVisible();
      const viewport = map.getByLabel('Карта: прокрутка');
      await map.getByRole('button', { name: 'Увеличить карту' }).tap();
      expect(await viewport.evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(
        true,
      );
      await viewport.focus();
      await guest.keyboard.press('ArrowRight');
      await expect
        .poll(() => viewport.evaluate((element) => element.scrollLeft))
        .toBeGreaterThan(0);
      await viewport.evaluate((element) => {
        element.scrollLeft = 0;
      });
      const bounds = await viewport.boundingBox();
      expect(bounds).not.toBeNull();
      const cdp = await participant.newCDPSession(guest);
      const y = bounds!.y + bounds!.height / 2;
      await cdp.send('Input.dispatchTouchEvent', {
        type: 'touchStart',
        touchPoints: [{ x: bounds!.x + bounds!.width * 0.8, y }],
      });
      await cdp.send('Input.dispatchTouchEvent', {
        type: 'touchMove',
        touchPoints: [{ x: bounds!.x + bounds!.width * 0.2, y }],
      });
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
      await expect
        .poll(() => viewport.evaluate((element) => element.scrollLeft))
        .toBeGreaterThan(0);
      await cdp.detach();
      await map.getByRole('button', { name: 'Сбросить масштаб карты' }).tap();
      await guest.keyboard.press('Escape');
      await expect(opener).toBeFocused();
      await expect(draft).toHaveValue('Сохранённый черновик');
    } else {
      const map = guest.getByRole('region', { name: 'Карта' });
      await expect(map.getByText('Приёмный зал — обнаружено')).toBeVisible({ timeout: 15000 });
      await expect(map.getByText(/→ Неизвестная область/)).toBeVisible();
      await expect(draft).toBeFocused();
    }
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
    await expect(guest.getByRole('heading', { name: 'Приёмный шлюз' })).toBeVisible();
    if (test.info().project.name === 'smoke-mobile') {
      await guest.getByRole('button', { name: 'Открыть карту' }).tap();
      await expect(
        guest.getByRole('dialog', { name: 'Карта группы' }).getByText('Приёмный зал — обнаружено'),
      ).toBeVisible();
      await guest.keyboard.press('Escape');
    } else {
      await expect(
        guest.getByRole('region', { name: 'Карта' }).getByText('Приёмный зал — обнаружено'),
      ).toBeVisible();
    }
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
