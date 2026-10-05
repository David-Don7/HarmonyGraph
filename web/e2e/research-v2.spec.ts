import { test, expect } from '@playwright/test';

test('research v2 exposes coherent paths, omitted mass and legacy control', async ({ page, request }) => {
  const response = await request.post('/api/v1/search', {data: {progression: 'V7 I', mode: 'functional', section: 'chorus', boundary: 'end', limit: 3}});
  expect(response.ok()).toBeTruthy();
  const found = await response.json();
  expect(found.results.length).toBeGreaterThan(0);
  const ids = [...new Set(found.results.map((r: any) => r.song_id))];
  // Keep this live browser check bounded; it exercises real API inference, not mocks.
  await page.route('**/api/v1/search', async route => {
    const body = route.request().postDataJSON();
    await route.continue({postData: JSON.stringify({...body, song_ids: ids, path_budget: 4})});
  });
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/studio');
  await expect(page.getByLabel('Research model')).toHaveValue('path_expectation');
  await page.getByRole('button', {name: 'Find matches', exact: true}).click();
  await expect(page.locator('.result').first()).toBeVisible();
  await page.getByRole('button', {name: 'Why this matches'}).first().click();
  await expect(page.getByRole('heading', {name: 'Alternative context paths'}).first()).toBeVisible();
  await expect(page.getByText(/Retained joint mass:/).first()).toBeVisible();
  await page.getByText(/retained paths and their alignments/).first().click();
  await expect(page.getByText(/Original probability/).first()).toBeVisible();
  await page.getByLabel('Research model').selectOption('legacy_mixture');
  await page.getByRole('button', {name: 'Find matches', exact: true}).click();
  await expect(page.locator('.result').first()).toBeVisible();
  await page.setViewportSize({width: 390, height: 844});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  expect(errors).toEqual([]);
});
