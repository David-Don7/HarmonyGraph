# Search optimization

Implemented 2026-10-30. These changes speed up the existing context-path and
deterministic research models. The search request, candidate limit, musical
rules, beam budgets, ranking equation, and uncertainty bounds are unchanged.
Literal/transposed and legacy-mixture search retain their existing algorithms.

## Changes

- **Reuse chart inference.** A process-local LRU retains query-independent HMM
  messages. Its content key includes chord roots, qualities, intervals, bass,
  status, section IDs, durations, window, key-change penalty and local-key mode.
  Changed inputs select a different entry. Arrays are read-only. The cache has
  at most 128 charts and a conservative 32 MiB reservation budget including
  possible conditional matrices; larger charts bypass it. This is an estimated
  cache budget, not a limit on total process memory.
- **Reuse overlapping computations.** Backward conditional transition matrices
  are computed lazily once per retained chart position. An 8,192-entry LRU
  stores immutable Roman-numeral/weight options by chord, key and following
  chord. No query-dependent scores or database candidate lists are cached.
- **Select prefixes with a heap.** Each beam expansion uses bounded top-k
  selection over a generator instead of materializing and sorting all expanded
  paths. Original probabilities and lexicographic tie order are preserved.
  This accelerates the same prefix beam; it does not make it an exact global
  joint-path search.
- **Skip unused deterministic work.** The deterministic control directly uses
  its Viterbi path instead of constructing and discarding an uncertainty beam.
- **Fetch only required evidence.** Interactive path searches omit the legacy
  per-event/per-key interpretation table. Lean and complete evidence have
  distinct cache keys. Shared research comparison contexts remain complete so
  a later legacy control receives all its evidence.

No migration, extra dependency, user setting, or catalog re-index is required.
Caches reset when the process restarts. Separate API/worker processes have
separate caches. Worker images need rebuilding when deploying this change to
background experiment runners as well as the API.

## Measurements

Reference: commit `f3662563a8709cac5e50e80395377a59cd093bbf`.
Both the reference paths and retrieval implementations were compared with the
updated code. Complete returned payloads, excluding timings, matched exactly.

### Offline software benchmark

Twelve generated transposed charts, 72 chord events per chart, 500 candidate
starts, SQLite. Warm times are medians of five repetitions. These are backend
search measurements; HTTP, persistence and response serialization are excluded.

| Query/model | Before | After | Speedup |
| --- | ---: | ---: | ---: |
| Functional, path budget 4 | 125 ms | 73 ms | 1.71× |
| Functional, path budget 16 | 332 ms | 177 ms | 1.87× |
| Fuzzy, path budget 16 | 1,310 ms | 840 ms | 1.56× |
| Deterministic control | 515 ms | 34 ms | 15.21× |

Reproduce from the repository root:

```sh
PYTHONPATH=. .venv/bin/python scripts/benchmark_search_optimization.py \
  --baseline-ref f366256 \
  --output artifacts/search-optimization/comparison.json
```

The script executes the trusted local revision's Python source to construct the
reference. It creates and removes a temporary fixture database; the published
catalog is untouched. Fixture IDs are generated per run, so payload fingerprints
are useful for within-run comparisons rather than cross-run identity checks.

### Local PostgreSQL catalog check

Pinned analysis `1054d2a9-75ed-4c61-8141-0ec0fed02561`, snapshot
`72abdb2b8ee3f002f621bf5123b70417e18e71628859bb8f320fac9309b15f01`.
Query `V7 I`, functional context paths, budget 4, chorus endings, 500 candidate
starts, three displayed results. Searches did not persist queries or modify data.

| Application cache state | Before | After |
| --- | ---: | ---: |
| Fresh process caches | 4,035 ms | 2,737 ms |
| Warm, median of three repetitions | 1,476 ms | 1,452 ms |

The fresh-cache improvement is about 32%; repeated searches are effectively
similar at this sample size. Database buffers were already warm: the first row
is not a cold-disk measurement. Candidate generation still takes roughly
0.7 seconds here and is not changed by these optimizations. These measurements
are from one local machine, not throughput guarantees or musical relevance
evidence. Raw results are in `artifacts/search-optimization/`.

## Verification

- Nine new regression cases cover exact probabilities, tied beam cutoffs,
  cache invalidation, bounded eviction, read-only arrays, full search payloads
  across six research ranking/mode combinations, and safe lean/full loading.
- Native suite: 82 passed, three PostgreSQL checks skipped without its URL.
- Docker suite with PostgreSQL: 85 passed. Tests use temporary schemas; the
  test container alone used `CATALOG_DATABASE_BUDGET_GB=0` because the shared
  catalog database is already above its 20 GiB processing cap. The deployed
  application's cap was unchanged.
- Ruff and `git diff --check` passed. Local web-to-API health and a real search
  succeeded after deployment.
