# Implementation map

HarmonyGraph is a local symbolic-music research application. The Python API, command line, and durable worker share the same services; the browser is a client of `/api/v1`.

| Area | Implementation | Main persisted evidence |
|---|---|---|
| Contracts and configuration | `harmonygraph/contracts.py` | Validated requests, stable SHA-256 configuration fingerprints |
| Storage and migrations | `db.py`, `migrations/` | Source records, versioned analyses, postings, jobs, judgments, experiments |
| Import adapters | `ingestion.py` | Raw annotations, source IDs, timing units, licensing, validation reports |
| Chord parsing and tonal model | `music.py` | Canonical pitches and spelling; 24-state posterior and Viterbi path |
| Inference and indexing | `analysis.py` | Key hypotheses, weighted Roman alternatives, harmonic relations, positional postings |
| Passage retrieval | `retrieval.py` | Candidate diagnostics, alignment operations, probability-weighted components |
| Research protocols | `research.py` | Grouped splits, frozen manifests, independent judgments, baselines, ablations, trials |
| Metrics and references | `metrics.py`, `validation.py` | Retrieval, calibration, agreement, boundaries, bootstrap comparisons |
| Performance and candidate audits | `performance.py` | Corpus sizes, timings, memory/storage, exhaustive candidate-start comparison |
| API, CLI, worker | `api.py`, `cli.py`, `jobs.py` | Shared workflows and durable progress, cancellation, recovery, errors |
| Browser workbench | `web/src/` | Search, song inspection, data/jobs, annotation, experiment and report interfaces |

## Analysis lifecycle

A run references its configuration and corpus fingerprint. It begins in `building`, writes event-level hypotheses and indexes together, and becomes `ready` only when all songs finish. Activation happens after that transition. A failed run retains its failure and cannot silently replace the active analysis. Historical searches can select a ready analysis ID explicitly.

Source keys remain available for evaluation and are excluded from inferred-key emissions. No-chord and unsupported events retain separate statuses. Posterior confidence is not a claim of calibration. Cadences and descending-fifth secondary-dominant chains are inspectable harmonic candidates.

## Retrieval bounds

Ordinary queries use indexed postings to propose starts, then rerank a bounded candidate set. Fuzzy windows permit up to two inserted or omitted events. Alternative interpretation search uses a beam of at most 16 paths. The configured candidate ceiling and any truncation are exposed. `candidate-audit` is an explicit expensive diagnostic and compares candidate starts against the same matcher's exhaustive output; it is distinct from recall against human relevance labels.

A bounded cache retains detached song snapshots (at most 256 songs or 50,000 events) for an analysis. Alignment results are memoized by query, target and cost settings. A complete ready analysis is reused by configuration and corpus fingerprint.

## Jobs and recovery

PostgreSQL workers claim rows with `FOR UPDATE SKIP LOCKED`. A heartbeat renews the lease; stale work returns to the queue after five minutes. Imports resume by source identity. Analyses restart safely and reuse complete configurations. Optimization resumes the durable study associated with its job ID; interrupted running trials are marked failed. Partial analyses and failed jobs remain visible for audit. Cancellation is cooperative at progress checkpoints.

The SQLite fallback supports local development with compare-and-set job claims. PostgreSQL remains the deployment target. Native and container operation share migrations; application and Optuna schema-version tables have separate names.

## Research boundaries

The included judgments describe original synthetic fixtures. Browser-test annotation entries are test contributions, not expert evaluations. The measured comparison is a six-query validation smoke run, not a final held-out study. A test evaluation requires frozen dataset, benchmark, split, analysis and configuration identities, and subsequent final-test runs require explicit rerun intent.

Editing a query creates a new benchmark revision with a distinct benchmark ID and copied query definitions. The edited query receives a new identity, empty pool, and no constructed labels. Earlier queries, pools, and independent judgments remain intact in the previous benchmark. Human judgments are not copied into the new annotation round. Stored experiment query snapshots and manifests preserve the context of measured runs.

No full external-corpus ingestion, expert study, full-scale throughput claim, authenticated collaboration, audio processing, or cloud deployment is asserted by this delivery. See `demo-results.md` for actually executed checks.
