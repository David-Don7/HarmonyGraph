import { test, expect } from '@playwright/test';

test('pilot preparation, blinded export and durable context-path comparison', async ({ page, request }) => {
  test.setTimeout(180000);
  const songs = await (await request.get('/api/v1/catalog/songs?ready=true&limit=1')).json();
  expect(songs.items.length).toBeGreaterThan(0);
  const song = songs.items[0];
  const benchmark = await (await request.post('/api/v1/benchmarks', {data: {
    name: `Browser pilot workflow check ${Date.now()}`, synthetic: true,
  }})).json();
  const created = await request.post(`/api/v1/benchmarks/${benchmark.id}/queries`, {data: {
    category: 'software-check', source_song_id: song.id,
    request: {progression: 'V I', mode: 'functional', ranking: 'path_expectation',
      song_ids: [song.id], path_budget: 1},
    protocol: {split: 'pilot', family: song.id, subtype: 'software-check'},
  }});
  expect(created.ok()).toBeTruthy();
  const query = await created.json();
  expect((await request.post(`/api/v1/benchmark-queries/${query.id}/pool`)).ok()).toBeTruthy();
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/studio');
  await page.getByRole('button', {name: 'Experiments', exact: true}).click();
  await page.getByLabel('Study benchmark', {exact: true}).selectOption(benchmark.id);
  await expect(page.getByText('Ready for comparison', {exact: true})).toBeVisible();
  const downloading = page.waitForEvent('download');
  await page.getByRole('link', {name: 'Download blinded packet', exact: true}).click();
  expect((await downloading).suggestedFilename()).toBe('blinded-review-packet.json');
  await page.getByRole('button', {name: 'Use source songs', exact: true}).click();
  await expect(page.getByLabel('Development song IDs')).toHaveValue(song.id);
  const queuedResponse = page.waitForResponse(r => r.url().endsWith('/api/v1/jobs') && r.request().method() === 'POST');
  await page.getByRole('button', {name: 'Queue context-path comparison', exact: true}).click();
  const queued = await (await queuedResponse).json();
  expect(queued.kind).toBe('research_v2_compare');
  expect(queued.parameters.analysis_id).toBeTruthy();
  await expect.poll(async () => {
    const job = await (await request.get(`/api/v1/jobs/${queued.id}`)).json();
    if (job.status === 'failed') throw new Error(job.error);
    return job.status;
  }, {timeout: 120000, intervals: [1000, 2000, 5000]}).toBe('completed');
  await expect(page.getByRole('link', {name: 'Download v2 comparison JSON'})).toBeVisible();
  const report = await (await request.get(`/api/v1/jobs/${queued.id}/export`)).json();
  expect(Object.keys(report.methods)).toHaveLength(7);
  expect(report.methods.path_expectation[0].metrics['ndcg@10']).toBeNull();
  for (const width of [1440, 768, 390]) {
    await page.setViewportSize({width, height: 1000});
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await page.screenshot({path: `test-results/study-${width}.png`, fullPage: true});
  }
  expect(errors).toEqual([]);
});
