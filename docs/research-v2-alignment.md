# Research v2 alignment — 2 October 2026

The governing documents are [research-proposal-v2.md](research-proposal-v2.md) and [novelty-audit-2026-10-01.md](novelty-audit-2026-10-01.md). Their central change is substantive: the old passage average of event-key marginals is not a coherent path posterior. The new implementation is an explicit versioned alternative. The documents describe a gated research program; completing software does not complete independent scientific evaluation.

## Implemented

| Requirement | Current implementation |
|---|---|
| Coherent query-independent paths | `harmonygraph/paths.py`, version `context-path-expectation-v1`; full-chart HMM messages, outside-passage states marginalized |
| Original probability mass | Posterior transition products; conditional function products; no retained-beam renormalization; key and function truncation both counted |
| Expected best alignment | Every retained path has its own dynamic-programming alignment, probability, similarity and contribution; separate threshold-match bounds |
| Auditable approximation | Partial expectation and omitted-mass bounds; candidate-set membership certificate; no corpus-wide guarantee |
| Legacy reproducibility | Default API/product behavior remains `legacy_mixture`; Studio explicitly offers the v2 method and deterministic control |
| Evidence | Context labels, key timeline per path, function sequence, alignment operations, model/config/analysis identifiers and exact score components |
| Hard constraints | Required section/boundary filters remain active even in legacy structural ablations; optional preferences are separate |
| Candidate generation | Union of retained function, key-free quality and canonical interval postings; explicit audit song IDs restrict the covering index directly |
| Controlled comparison | `research-v2-compare` shares one candidate-start pool, analysis and inference settings across seven controls; no reanalysis for edit-cost comparisons |
| Annotation | Frozen context snapshots and hashes, reviewer qualifications field, blinded pool endpoint/UI, nullable unresolved labels, interpretation/section/evidence-basis fields, preserved adjudication sources |
| Evaluation | Adjudicated chord-only labels primary; optional individual-rater sensitivity; gain 0/1/3; clustered paired bootstrap; family split-leakage checks; tonic-only calibration via mode marginalization |
| Held-out protection | V2 development runner rejects test queries and requires explicit split/family/subtype/context metadata; it does not reuse legacy test permissions |
| Reproducibility | Migration 0004, regenerated OpenAPI/TypeScript, manifest-hashed CLI exports, bounded audit script and updated paper scaffold |

The deterministic control uses a point mass on the Viterbi/leading-function path. Its weight of one is explicitly not that path's original HMM probability. Equal/max/shuffled controls are diagnostics; they are not the primary expectation. Prefix beam selection is approximate and is not claimed to find globally best joint paths. Function weights remain unvalidated assumptions. Score certificates do not bound omitted corpus candidates.

`functional` v2 ranks exact-length candidate windows by expected alignment similarity; `fuzzy` also considers nearby lengths. Legacy functional mode keeps its exact-match acceptance semantics for ordinary use; the controlled runner disables that acceptance threshold so all methods rank the shared structurally eligible pool. Hard constraints are not ablated away.

## Executed bounded real-data milestone

The downloaded 264,198,044-byte Chordonomicon CSV matched SHA-256 `9d2f4ccdc876a4e816712f128e4772b2af558c2a2923cce5be3a0364fbad9a8d`, revision `f3a8b678bd65639c01caa342921733f1db01be23`. Dataset attribution is CC-BY-NC-4.0, distinct from software licensing.

A separate local database contains the first eight publisher records with 6–80 chord events. All 469 events parsed as known chords. These are eight charts, not a verified count of unique recordings. Full chord contexts were retained. Missing song names were not invented. Selection was source-based before viewing model scores; the sample is neither representative nor a labelled ambiguity set.

The [eight-example review packet](research-v2-review-packet.md) includes complete chord contexts, fixed query, model-suggested alternative readings, a 0/1/2 rubric and an unresolved option. It hides method scores. All labels remain ungraded; no reviewer has been recruited or contacted.

| Key beam | Joint mass minimum | Joint mass median | Joint mass maximum | Median passage scoring time |
|---:|---:|---:|---:|---:|
| 4 | 0.8902 | 0.9706 | 0.9976 | 1.92 ms |
| 16 | 0.9523 | 0.9924 | 0.9994 | 3.88 ms |
| 64 | 0.9903 | 0.9980 | 0.9998 | 11.24 ms |

These are three-event passage checks on eight section openings, using a function beam of 16. Windows 11 build 26200, Python 3.12.4, Intel Core i5-12450HX (12 logical processors), sequential execution, in-process evidence cache and precomputed HMM messages. The SQLite database file was 4,796,416 bytes. These timings exclude candidate generation/database/context inference; they are not end-to-end search latency. Peak memory was not instrumented. Larger, more ambiguous passages may retain much less mass.

For the single `ii V I` query at key beam 4, indexed generation supplied 347 starts versus 469 exhaustively enumerated starts. It contained all of the exhaustive fixed-model top ten (1.0 candidate recall at that cutoff), without hitting the configured cap. This is bounded model-candidate recall, not human relevance recall or a full-catalog guarantee. Raw measurements and hashes are in [the audit JSON](measured/research-v2-audit.json).

## Verification

- Exact enumeration of 24-state, three-event sequences agrees with conditioned two-event path probabilities.
- Full joint key/function enumeration has unit mass; partial scores bound the exact expectation; retained probabilities match the originals.
- Tests cover score reconstruction, hard filters, unresolved adjudication, blinding, context hashes, family leakage, seeded clustered resampling and tonic-only references.
- Controlled-run fixture verifies seven methods share the candidate pool and retain chorus-ending constraints; held-out queries are rejected.
- Local full suite: 66 passed, 3 PostgreSQL checks skipped without the native test URL. Docker verification then ran all 3 PostgreSQL checks plus 9 v2 checks: 12 passed. Subsequent focused v2/scaling verification: 15 passed. TypeScript/Vite build and the live Playwright regression passed. The later controlled-run test is included in the focused count.
- PostgreSQL migration 0004 was applied successfully. API and frontend were rebuilt with the existing real-song database; no full-corpus reanalysis or optimization was started.

## Remaining research gates — explicitly incomplete

1. **Data/reviewer feasibility:** independently classify natural contexts and subtypes, audit expert reference coverage and cross-corpus/cover overlaps, record qualifications and annotation burden. The current packet is for feasibility, not expert evidence.
2. **Strong comparators:** implement and validate Hanna-style local-transposition alignment, a faithful documented HarmTrace adaptation, a training-only sequence embedding and the expected-local-cost control. A global-key path control is also pending in the v2 runner. Legacy controls alone cannot establish research superiority.
3. **Pilot:** use 24–30 independently reviewed queries if reviewer access permits; measure context-pair ordering, per-stratum quality, retained-mass/error and top-ten stability curves, memory, and end-to-end p50/p95 under fixed conditions. Add cross-method deduplicated/random/adversarial pools with adequate coverage.
4. **Study protocol:** implement the complete cover/source/query-template/cross-corpus grouping audit, freeze rubric/exclusions/normalization/candidate budget/methods before test use, and run balanced end-to-end tuning separately from fixed-inference controls. The v2 CLI currently refuses final-test execution.
5. **Paper:** only report relevance, explanation usefulness, calibration and superiority after the appropriate independent measurements. No first-system or guaranteed-improvement claim is made.

## Run the workflow

```powershell
.\.venv\Scripts\python.exe scripts/research_v2_local_audit.py
# Existing analyzed songs, explicit bounded scope:
harmonygraph research-v2-audit --song-id <id> --song-id <id> --examples 8
# Each query must have protocol.split=pilot/train/validation,
# a family, a prelabelled subtype and its stored source context:
harmonygraph research-v2-compare <benchmark-id> --song-id <id> --path-budget 32
```

Open `/studio`, select Context paths, enter 2–8 Roman numerals, and inspect Why this matches. The API exposes `ranking`, `path_budget`, `function_budget`, and `match_threshold` on `/api/v1/search`; `/api/v1/research-v2/status` reports the remaining gates. Legacy experiment/HPO controls are labelled as legacy in the Studio. New benchmark query creation with a source song automatically snapshots that chord context; edits create a new benchmark revision. A pool with judgments cannot be silently rebuilt.
