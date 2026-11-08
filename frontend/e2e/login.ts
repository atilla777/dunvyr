import { expect, test, type Page } from '@playwright/test';

/** Respect the shared server's identity limit without retrying the test itself. */
export async function loginWithRateLimit(page: Page, nickname: string) {
  await page.getByLabel('Псевдоним').fill(nickname);
  for (let retries = 0; ; retries += 1) {
    const responsePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith('/api/identity/sessions') && response.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Войти' }).click();
    const response = await responsePromise;
    if (response.status() !== 429) {
      expect(response.ok(), `identity login returned ${response.status()}`).toBeTruthy();
      return;
    }
    expect(retries, 'identity rate-limit retry budget exhausted').toBeLessThan(3);
    const retryAfter = response.headers()['retry-after'];
    expect(retryAfter, '429 must include a Retry-After in seconds').toMatch(/^[1-9]\d*$/);
    const seconds = Number(retryAfter);
    expect(seconds).toBeLessThanOrEqual(60);
    const wait = seconds * 1000;
    console.log(`Identity 429: Retry-After ${seconds}s; waiting ${wait}ms`);
    test.info().setTimeout(test.info().timeout + wait);
    await page.waitForTimeout(wait);
  }
}
