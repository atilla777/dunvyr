import { expect, test } from '@playwright/test';

// End-to-end reconnect slice: two guest browser contexts meet in one campaign,
// exchange chat messages in both directions and one participant reloads the
// page. The collaboration scenario runs in both smoke projects (desktop and
// mobile), so the second context inherits the device settings of its project.
test('гости видят чат друг друга и сохраняют историю после перезагрузки', async ({
  browser,
  page,
}) => {
  const projectUse = test.info().project.use;
  const secondGuestContext = await browser.newContext({
    viewport: projectUse.viewport,
    userAgent: projectUse.userAgent,
    deviceScaleFactor: projectUse.deviceScaleFactor,
    isMobile: projectUse.isMobile,
    hasTouch: projectUse.hasTouch,
  });

  try {
    const guestB = await secondGuestContext.newPage();

    await page.goto('/');
    await page.getByLabel('Псевдоним').fill('Алиса');
    await page.getByRole('button', { name: 'Войти' }).click();
    await expect(page.getByText('Вы вошли как Алиса')).toBeVisible();

    await page.getByLabel('Название кампании').fill('Ночная смена');
    await page.getByRole('button', { name: 'Создать кампанию' }).click();
    await expect(page.getByRole('heading', { level: 2, name: 'Ночная смена' })).toBeVisible();
    await expect(page.getByText('Чат на связи')).toBeVisible();

    const invitationUrl = await page.getByRole('link').getAttribute('href');
    expect(invitationUrl).not.toBeNull();

    await guestB.goto(invitationUrl ?? '');
    await guestB.getByLabel('Псевдоним').fill('Боб');
    await guestB.getByRole('button', { name: 'Войти' }).click();
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

    // Reload: the snapshot restores the roster and the whole history once,
    // without duplicates from the previously received live stream.
    await page.reload();
    await expect(page.getByRole('heading', { level: 2, name: 'Ночная смена' })).toBeVisible();
    await expect(page.getByText(/Мест занято: 2 из \d+/)).toBeVisible();
    await expect(page.getByText('Привет от Алисы')).toHaveCount(1);
    await expect(page.getByText('Привет от Боба')).toHaveCount(1);
    await expect(page.getByText('Боб присоединился к кампании')).toHaveCount(1);
    await expect(page.getByText('Чат на связи')).toBeVisible();
  } finally {
    await secondGuestContext.close();
  }
});
