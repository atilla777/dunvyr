import { expect, test } from '@playwright/test';
import { loginWithRateLimit } from './login';

// End-to-end reconnect slice: two guest browser contexts meet in one campaign,
// exchange chat messages in both directions and one participant reloads the
// page. The collaboration scenario runs in both smoke projects (desktop and
// mobile), so the second context inherits the device settings of its project.
test('гости видят чат друг друга и сохраняют историю после перезагрузки', async ({
  browser,
  page,
}) => {
  test.setTimeout(90_000);
  const projectUse = test.info().project.use;
  const secondGuestContext = await browser.newContext({
    viewport: projectUse.viewport,
    userAgent: projectUse.userAgent,
    deviceScaleFactor: projectUse.deviceScaleFactor,
    isMobile: projectUse.isMobile,
    hasTouch: projectUse.hasTouch,
  });

  let failed = false;
  try {
    const guestB = await secondGuestContext.newPage();

    await page.goto('/');
    await loginWithRateLimit(page, 'Алиса');
    await expect(page.getByText('Вы вошли как Алиса')).toBeVisible();

    await page.getByLabel('Название кампании').fill('Ночная смена');
    await page.getByRole('button', { name: 'Создать кампанию' }).click();
    await expect(page.getByRole('heading', { level: 2, name: 'Ночная смена' })).toBeVisible();
    await expect(page.getByText('Чат на связи')).toBeVisible();

    const invitationUrl = await page.getByRole('link').getAttribute('href');
    expect(invitationUrl).not.toBeNull();

    await guestB.goto(invitationUrl ?? '');
    await loginWithRateLimit(guestB, 'Боб');
    await guestB.getByRole('button', { name: 'Присоединиться' }).click();
    await expect(guestB.getByRole('heading', { level: 2, name: 'Ночная смена' })).toBeVisible();
    await expect(guestB.getByText('Чат на связи')).toBeVisible();

    await expect(page.getByText('Боб присоединился к кампании')).toBeVisible();
    await expect(page.getByText(/Мест занято: 2 из \d+/)).toBeVisible();

    await page.getByLabel('Сообщение').fill('Привет от Алисы');
    await page.getByRole('button', { name: 'Отправить' }).click();
    await expect(page.getByText('Привет от Алисы')).toBeVisible();
    await expect(guestB.getByText('Привет от Алисы')).toBeVisible();

    await guestB.getByLabel('Сообщение').fill('Привет от Боба');
    await guestB.getByRole('button', { name: 'Отправить' }).click();
    await expect(guestB.getByText('Привет от Боба')).toBeVisible();
    await expect(page.getByText('Привет от Боба')).toBeVisible();

    const bobRoster = page.locator('.campaign__member').filter({ hasText: 'Боб' });
    await expect(bobRoster).toContainText('В сети');
    const secondTab = await secondGuestContext.newPage();
    await secondTab.goto('/');
    await expect(secondTab.getByText('Чат на связи')).toBeVisible();
    await guestB.close();
    // Wait beyond the server grace to prove the remaining tab keeps Bob online.
    await page.waitForTimeout(6000);
    await expect(bobRoster).toContainText('В сети');
    await secondTab.close();
    await expect(bobRoster).toContainText('Не в сети', { timeout: 12000 });
    const restored = await secondGuestContext.newPage();
    await restored.goto('/');
    await expect(restored.getByText('Чат на связи')).toBeVisible();
    await expect(bobRoster).toContainText('В сети', { timeout: 12000 });
    await expect(restored.getByText('Привет от Алисы')).toHaveCount(1);
    await expect(restored.getByText('Привет от Боба')).toHaveCount(1);

    // Reload: the snapshot restores the roster and the whole history once,
    // without duplicates from the previously received live stream.
    await page.reload();
    await expect(page.getByRole('heading', { level: 2, name: 'Ночная смена' })).toBeVisible();
    await expect(page.getByText(/Мест занято: 2 из \d+/)).toBeVisible();
    await expect(page.getByText('Привет от Алисы')).toHaveCount(1);
    await expect(page.getByText('Привет от Боба')).toHaveCount(1);
    await expect(page.getByText('Боб присоединился к кампании')).toHaveCount(1);
    await expect(page.getByText('Чат на связи')).toBeVisible();
  } catch (error) {
    failed = true;
    throw error;
  } finally {
    try {
      await secondGuestContext.close();
    } catch (error) {
      if (!failed) throw error;
    }
  }
});
