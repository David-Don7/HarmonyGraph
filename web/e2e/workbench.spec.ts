import { test, expect } from '@playwright/test';

test('search evidence, song timeline, and responsive navigation', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /Find the harmony/ })).toBeVisible();
  await page.getByRole('button', { name: 'Find matches' }).click();
  await expect(page.locator('.result').first()).toBeVisible();
  await page.getByRole('button', { name: 'Why this matches' }).first().click();
  await expect(page.getByText('Score contributions').first()).toBeVisible();
  await page.locator('.result-title button').first().click();
  await expect(page.getByRole('heading', { name: 'Functional alternatives' })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  expect(errors).toEqual([]);
});

test('independent annotation and research result export', async ({ page, request }) => {
  const profiles = await (await request.post('/api/v1/annotators', { data: { name: 'Browser test annotator' } })).json();
  await page.goto('/');
  await page.evaluate(id => localStorage.setItem('annotator', id), profiles.id);
  await page.reload();
  await page.getByRole('button', { name: 'Benchmark lab' }).click();
  await page.locator('.query-list > button').first().click();
  await page.getByRole('button', { name: 'Build candidate pool' }).click();
  await expect(page.locator('.judgment').first()).toBeVisible();
  await page.getByRole('button', { name: 'Save judgment', exact: true }).first().click();
  await expect(page.getByText('Judgment saved.', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: 'Experiments', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Automatic parameter optimization' })).toBeVisible();
  const exports = page.getByRole('link', { name: 'JSON', exact: true });
  if (await exports.count()) {
    const download = page.waitForEvent('download');
    await exports.first().click();
    expect((await download).suggestedFilename()).toBe('experiment.json');
  }
});


test('durable jobs execute and experiment reports download', async ({ page, request }) => {
  test.setTimeout(180000);
  await page.goto('/');
  await page.getByRole('button', { name: 'Data & jobs', exact: true }).click();
  await page.getByRole('button', { name: 'Analyze & index corpus' }).click();
  await expect(page.getByText('Job queued.', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: 'Experiments', exact: true }).click();
  const queuedResponse = page.waitForResponse(response => response.url().endsWith('/api/v1/jobs') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Run comparison' }).click();
  const queuedJob = await (await queuedResponse).json();
  expect(queuedJob.kind).toBe('evaluate');
  await expect.poll(async () => {
    const job = await (await request.get(`/api/v1/jobs/${queuedJob.id}`)).json();
    if (job?.status === 'failed') throw new Error(job.error);
    return job?.status;
  }, { timeout: 150000, intervals: [1000, 2000, 5000] }).toBe('completed');
  await expect(page.getByRole('link', { name: 'CSV', exact: true }).first()).toBeVisible();
  const downloading = page.waitForEvent('download');
  await page.getByRole('link', { name: 'CSV', exact: true }).first().click();
  expect((await downloading).suggestedFilename()).toBe('metrics.csv');
});
