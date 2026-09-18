# Executed demonstration and verification

Recorded on 19 September 2026. **Docker verification has now also passed; see [Docker results](docker-results.md).** This is a local software demonstration with original synthetic music, not a completed scientific study.

## Delivered corpus and interfaces

- 120 original synthetic songs, 2,388 chord events, and 120 constructed benchmark queries.
- Canonical demo songs and query records are in `data/demo/`. Their relevance labels are synthetic.
- Four retrieval modes, five workbench pages, versioned API, shared CLI, and durable worker are implemented.
- Chordonomicon, Billboard, and Isophonics adapters have focused format fixtures. No complete external corpus was imported for this delivery.
- Final default analysis: `hmm-functional-v4`, eight-event context, three retained hypotheses.
- Analysis ID: `517923db-a17f-4c8c-bb12-e6c06402b9bb`. Its combined analysis/indexing time was 32.47 seconds for 120 songs. This is one local measurement, not an index-only throughput claim.

## Executed checks

| Check | Observed result |
|---|---|
| Original native Python suite | 41 passed; 2 PostgreSQL tests skipped because `TEST_POSTGRES_URL` was not supplied |
| Final targeted follow-ups | Seeded optimization/resume tests and annotation-revision preservation passed |
| Static Python checks | Passed for application, tests, and scripts |
| Generated API types and production web build | Passed |
| Browser scenarios | 3 passed in 37.1 seconds: search/evidence/song inspection, annotation/export, and durable analysis/comparison jobs |
| Durable optimization | Three seeded validation trials completed through the worker |
| Container configuration | `docker compose config --quiet` passed; sandbox emitted a Docker user-config access warning |
| Fresh Docker deployment / PostgreSQL runtime | Subsequently verified: 43 containerized Python checks and 3 production browser scenarios passed; see [Docker results](docker-results.md) |

The Python suite covers chord aliases, inversions, alterations, no-chord versus unknown labels, posterior normalization, transposition across all twelve roots, structural filtering, score reconstruction, idempotent ingestion, failed-index activation protection, stale-job recovery, annotation independence, revisions, migrations, grouped splits, metric fixtures, and test-set safeguards. There is one non-failing upstream warning about Starlette's httpx test-client integration.

Both PostgreSQL tests subsequently passed in the Docker verification container, covering migrations, indexes, row locking, imports, filtering, version isolation, and job recovery in isolated schemas. CI is also configured to execute them, but no remote CI run is asserted here.

## Measured retrieval demonstration

The final run executed B1–B6, the proposed configuration, and all eight ablations on **six validation queries**. Results, per-query requests and judgments, configurations, split assignments, environment details, intervals, and figures are exported in [the final report directory](measured/f9764a0b-fc70-4a3a-a59e-29d47a87696b/report.md).

| Configuration | Synthetic validation nDCG@10 |
|---|---:|
| B1 absolute | 0.5726 |
| B2 intervals | 1.0000 |
| B3 global key | 0.6667 |
| B4 deterministic local | 1.0000 |
| B5 uniform edit | 1.0000 |
| B6 manual / proposed defaults | 1.0000 |
| Without local changes | 0.6667 |
| Other seven ablations | 1.0000 |

The ties are a limitation of this small, regular smoke set. They do not establish a benefit for uncertainty, section context, optimization, or any other component. No final held-out test study was performed. Expert harmonic and explanation ratings remain unavailable where references are absent.

The three-trial seeded optimization demonstration used the preceding `hmm-functional-v3` rules, on six validation queries per trial. Trial objective values were 1.0, 1.0, and 0.6667. Its complete trial parameters and selected configuration are in [optimization.json](measured/optimization.json) and [selected-config.json](measured/selected-config.json). The final v4 addition records secondary-dominant-chain evidence; this historical study is intentionally labeled with its original version.

## Warm search measurements

Ten serial repetitions per query, after warm-up, on the 120-song corpus:

| Mode | Median ms | p95 ms |
|---|---:|---:|
| functional | 106.5 | 122.1 |
| transposed | 38.0 | 61.8 |
| fuzzy | 437.9 | 565.0 |

These measured queries met the one-second warm p95 target. This is application-service latency on SQLite, not browser/network latency or full-corpus PostgreSQL performance. Three queries cannot characterize the entire query distribution. The computer was not isolated from other local workloads.

Environment: Windows 11 build 26200, Python 3.12.4, Intel64 Family 6 Model 151 Stepping 2, 12 logical CPUs. Measurements at 12, 60, and 120 songs, candidate/reranking timings, and serial throughput are in [performance-v4.json](measured/performance-v4.json).

The active index contained 34,728 postings. The database occupied 464,461,824 bytes and contained many historical analysis and experiment versions; that size is **not** the size of one index. A separate fuzzy query peaked at 5,323,345 bytes of Python allocations. Process RSS was not measured.

The bounded exhaustive audit of `V7 I` in choruses found all 60 matcher-accepted start positions in indexed candidates, with no truncation: candidate-start recall 1.0. This tests candidate generation against the same matcher and is not human relevance recall. See [candidate-audit-v4.json](measured/candidate-audit-v4.json).

## Corrections and retained history

The earliest benchmark omitted exact matching subpassages from constructed relevance labels, producing invalid all-zero demonstration rankings. Those labels were corrected and the benchmark was versioned as v2. `legacy-incomplete-labels.json` is retained only as an explicitly superseded diagnostic; it is excluded from the results above. Earlier v3 performance and comparison exports remain identified by their analysis IDs.

A real optimization job initially exposed a collision between the application's migration table and Optuna's migration table. The namespaces were separated, a regression check was added, and the subsequent durable three-trial job completed. Failed job history remains visible locally.

## Remaining verification and research work

The fresh-container workflow and PostgreSQL checks are now complete; see [Docker results](docker-results.md). External-corpus import validation at scale, expert annotations, confidence calibration findings, transfer studies, the explicit 100–300-trial research preset, and final frozen test evaluation are subsequent research work.
