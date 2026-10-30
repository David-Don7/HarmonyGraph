import {test, expect, type Page} from '@playwright/test';

const songId = 'studio-ui-fixture';
const result = {
  passage_id: `${songId}:0:1`, song_id: songId, title: 'UI fixture passage', artist: 'Software fixture',
  section: 'chorus_1', start: 0, end: 1, labels: ['G7','C'], score: .9995006160799509,
  key_hypotheses: [], retained_mass: .9995650509721522, interpretation: ['V7','I'], alignment: [],
  components: {path_expectation: {value: .9995006160799509, weight: 1, contribution: .9995006160799509}},
  evidence: {synthetic: true, context_labels: ['G7','C'], paths: {
    semantics: 'path_expectation', retained_mass: .9995650509721522, omitted_mass: .0004349490278478,
    expected_similarity_bounds: [.9995006160799509,.9999355651077987],
    paths: [{functions: ['V7','I'], key_names: ['C major','C major'], probability: .9995650509721522,
      similarity: .999935537071, contribution: .9995006160799509, alignment: []}],
    probability_note: 'Software fixture probabilities',
  }}, explanation: 'Software fixture, not a musical finding.', analysis_id: 'analysis-ui-fixture',
};

async function fixtures(page: Page) {
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    let json: any = [];
    if (path.endsWith('/overview')) json = {analysis: {id: 'analysis-ui-fixture'}, genres: ['rock']};
    if (path.endsWith('/benchmarks')) json = [{id: 'benchmark-ui-fixture', name: 'UI fixture benchmark', query_count: 1, synthetic: true}];
    if (path.endsWith('/annotators')) json = [{id: 'reviewer-ui-fixture', name: 'UI fixture reviewer'}];
    if (path.endsWith('/queries')) json = [{id: 'query-ui-fixture', source_song_id: songId, category: 'software-check',
      request: {progression: 'V7 I', mode: 'functional'}, protocol: {split: 'pilot', family: 'fixture'}, pool: [result]}];
    if (path.endsWith('/blind-pool')) json = {candidates: [{...result, context: ['G7','C']}]};
    if (path.endsWith('/readiness')) json = {protocol_ready: true, annotation_ready: true, review_complete: false,
      synthetic: true, issues: [], queries: [{query_id: 'query-ui-fixture', progression: 'V7 I', split: 'pilot', family: 'fixture',
        subtype: 'software-check', pool_size: 1, double_reviewed: 0, adjudicated: 0, issues: []}], research: {comparators: {pending: []}}};
    if (path.endsWith('/songs')) json = [{id: songId, title: 'UI fixture passage', artist: 'Software fixture', synthetic: true}];
    if (path.endsWith(`/songs/${songId}`)) {
      const posterior = Array(24).fill(0); posterior[0] = .6; posterior[7] = .4;
      json = {id: songId, title: 'UI fixture passage', artist: 'Software fixture', synthetic: true, analysis_id: 'analysis-ui-fixture',
        sections: [{id: 'section', start: 0, end: 1, label: 'chorus_1'}],
        events: [0,1].map(ordinal => ({id: `event-${ordinal}`, ordinal, label: ordinal ? 'C' : 'G7', path_key: 0, posterior,
          interpretations: {0: [{roman: 'V7', function: 'dominant', weight: 1}], 7: [{roman: 'I7', function: 'tonic', weight: 1}]}})),
        relations: [{id: 'r1', kind: 'secondary', start: 0, end: 1, confidence: .00001},
          {id: 'r2', kind: 'secondary', start: 0, end: 1, confidence: .00002}], source: {source_id: 'fixture'}};
    }
    if (path.endsWith('/catalog/songs')) json = {items: []};
    if (path.endsWith('/jobs')) json = [{id: 'job-ui-fixture', kind: 'catalog_analyze', status: 'queued', progress: 1,
      created_at: '2026-10-29T00:00:00Z', updated_at: '2026-10-29T00:01:00Z', parameters: {},
      result: {continue: true, indexed_this_batch: 20}, error: null}];
    if (path.endsWith('/search')) {
      const body = route.request().postDataJSON();
      const deterministic = body.ranking === 'hard_path';
      const value = deterministic ? {...result, score: 1, retained_mass: 1, evidence: {...result.evidence, paths: {
        ...result.evidence.paths, semantics: 'hard_path', retained_mass: 1, omitted_mass: 0,
        expected_similarity_bounds: [1,1], paths: [{...result.evidence.paths.paths[0], probability: 1, similarity: 1, contribution: 1}],
      }}} : result;
      json = {results: [value], analysis_id: 'analysis-ui-fixture', candidate_count: 500, candidate_limit_reached: true,
        timings: {total_ms: 12221, candidate_ms: 100, rerank_ms: 12121}};
    }
    await route.fulfill({json});
  });
}

test.beforeEach(async ({page}) => {await fixtures(page);});

test('precise evidence separates scores, model mass and candidate limits', async ({page}) => {
  await page.goto('/studio#search');
  await expect(page.getByRole('heading', {name: 'Harmonic search', exact: true})).toBeVisible();
  await expect(page.getByText('Find the harmony.', {exact: false})).toHaveCount(0);
  await page.getByRole('button', {name: 'Find matches', exact: true}).click();
  await expect(page.getByRole('heading', {name: '1 passage shown'})).toBeVisible();
  await expect(page.locator('.score strong')).toHaveText('0.999501');
  await expect(page.getByText('Unresolved', {exact: true})).toHaveCount(0);
  await expect(page.getByText(/Candidate cap reached: 500 starts evaluated/)).toBeVisible();
  await page.getByRole('button', {name: 'Why this matches', exact: true}).click();
  await expect(page.locator('.evidence-summary').getByText('99.9565%', {exact: true})).toBeVisible();
  await expect(page.locator('.evidence-summary').getByText('0.0435%', {exact: true})).toBeVisible();
  await page.getByText('Search details', {exact: true}).click();
  await expect(page.getByText('12.22 s', {exact: true})).toBeVisible();
  await page.getByLabel('Research model').selectOption('legacy_mixture');
  await expect(page.locator('.section-heading .muted')).toHaveText('Context paths');
  await expect(page.getByText('Technical details and provenance', {exact: true})).toBeVisible();
  for (const width of [1440,768,390]) {
    await page.setViewportSize({width, height: 950});
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await page.screenshot({path: `test-results/studio-clean-search-${width}.png`, fullPage: true});
  }
});

test('only effective model controls are offered', async ({page}) => {
  await page.goto('/studio');
  await expect(page.getByLabel('Key-path budget')).toHaveValue('4');
  await page.getByRole('button', {name: 'More filters', exact: true}).click();
  await expect(page.getByLabel(/Legacy alignment tolerance/)).toHaveCount(0);
  await page.getByLabel('Research model').selectOption('hard_path');
  await expect(page.getByLabel('Key-path budget')).toHaveCount(0);
  await page.getByLabel('Research model').selectOption('legacy_mixture');
  await page.getByRole('button', {name: 'Fuzzy functional', exact: true}).click();
  await expect(page.getByLabel(/Legacy alignment tolerance/)).toBeVisible();
  await page.getByRole('button', {name: 'Literal', exact: true}).click();
  await expect(page.getByLabel('Research model')).toHaveCount(0);
  await expect(page.getByLabel(/Legacy alignment tolerance/)).toHaveCount(0);
});

test('deterministic evidence does not claim full posterior coverage', async ({page}) => {
  await page.goto('/studio');
  await page.getByLabel('Research model').selectOption('hard_path');
  await page.getByRole('button', {name: 'Find matches', exact: true}).click();
  await page.getByRole('button', {name: 'Why this matches', exact: true}).click();
  await expect(page.getByRole('heading', {name: 'Selected interpretation', exact: true})).toBeVisible();
  await expect(page.getByText('Retained model mass', {exact: true})).toHaveCount(0);
  await expect(page.getByText('Expected similarity bounds', {exact: true})).toHaveCount(0);
  await expect(page.getByText('Unresolved', {exact: true})).toHaveCount(0);
});

test('song details distinguish key probabilities and conditional functions', async ({page}) => {
  await page.goto('/studio#songs');
  await page.getByRole('button', {name: /UI fixture passage/}).click();
  await expect(page.getByText('60% key probability', {exact: true})).toBeVisible();
  await expect(page.getByText('40% key probability', {exact: true})).toBeVisible();
  await expect(page.getByText('100% conditional weight', {exact: true})).toHaveCount(0);
  await expect(page.locator('.relation-row')).toHaveCount(1);
  await expect(page.getByText('0%', {exact: true})).toHaveCount(0);
  await expect(page.getByText('Individual hypotheses and model weights')).toBeVisible();
});

test('recurring jobs show batch status and maintenance stays secondary', async ({page}) => {
  await page.goto('/studio#data');
  await expect(page.getByText('Waiting for next batch', {exact: true})).toBeVisible();
  await expect(page.getByText('100%', {exact: true})).toHaveCount(0);
  await expect(page.getByRole('button', {name: 'Load synthetic demo'})).toBeHidden();
  await page.getByText('Import or analyze a dataset', {exact: true}).click();
  await expect(page.getByRole('button', {name: 'Analyze & index corpus'})).toBeVisible();
});

test('study scope defaults to source songs and legacy tools are collapsed', async ({page}) => {
  await page.goto('/studio#experiments');
  await expect(page.getByRole('heading', {name: 'Automatic parameter optimization'})).toBeHidden();
  await page.getByLabel('Study benchmark', {exact: true}).selectOption('benchmark-ui-fixture');
  await expect(page.getByText('1 benchmark source song', {exact: true})).toBeVisible();
  await expect(page.getByRole('button', {name: 'Queue context-path comparison'})).toBeEnabled();
  await expect(page.getByLabel('Development song IDs')).toHaveCount(0);
  await page.getByText('Change comparison scope', {exact: true}).click();
  await page.getByLabel('Use a custom song set').check();
  await expect(page.getByLabel('Development song IDs')).toHaveValue(songId);
  await page.getByRole('button', {name: 'Use source songs', exact: true}).click();
  await expect(page.getByLabel('Development song IDs')).toHaveCount(0);
  await page.getByText('Legacy experiments and tuning', {exact: true}).click();
  await expect(page.getByRole('heading', {name: 'Automatic parameter optimization'})).toBeVisible();
});

test('benchmark review hides explanation ratings during independent grading', async ({page}) => {
  await page.goto('/studio#benchmarks');
  await expect(page.getByRole('link', {name: 'Export query records'})).toHaveCount(0);
  await page.getByLabel('Benchmark', {exact: true}).selectOption('benchmark-ui-fixture');
  await page.locator('.query-list > button').first().click();
  await expect(page.getByRole('combobox', {name: 'Relevance', exact: true})).toBeVisible();
  await expect(page.getByLabel('Correctness', {exact: true})).toHaveCount(0);
  await expect(page.getByText('Unresolved', {exact: true})).toHaveCount(0);
});

test('near-certain values are not rounded into exact certainty', async ({page}) => {
  await page.route('**/api/v1/search', async route => route.fulfill({json: {
    results: [{...result, score: 1 - 1e-10, evidence: {...result.evidence, paths: {...result.evidence.paths,
      retained_mass: 1 - 1e-10, omitted_mass: 1e-10, expected_similarity_bounds: [1 - 1e-10, 1]}}}],
    analysis_id: result.analysis_id, candidate_count: 1, candidate_limit_reached: false, timings: {total_ms: 1},
  }}));
  await page.goto('/studio');
  await page.getByRole('button', {name: 'Find matches', exact: true}).click();
  await expect(page.locator('.score strong')).toHaveText('<1.000000');
  await page.getByRole('button', {name: 'Why this matches', exact: true}).click();
  await expect(page.locator('.evidence-summary').getByText('>99.9999%', {exact: true})).toBeVisible();
  await expect(page.locator('.evidence-summary').getByText('<0.0001%', {exact: true})).toBeVisible();
});
