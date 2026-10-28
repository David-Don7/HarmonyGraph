# Application and study-preparation handover — 29 October 2026

Scope: finish the local application workflow and prepare the research study.
The research questions, independent annotation and publication evidence remain
governed by the proposal; no human relevance results have been manufactured.

## Delivered

- Full Docker deployment: PostgreSQL, migrations, API, production web and two
  resumable catalog workers. Persistent data and native SQLite stay separate.
- Studio automatically uses a published catalog analysis when no independent
  research analysis is active. Default search respects publication watermarks;
  separately selected research analyses retain precedence.
- Research pilot panel with per-query protocol checks, declared split leakage
  checks, candidate/independent-review/adjudication coverage, and blinded exports.
- Hash-checked, atomic independent-response imports. Earlier submissions remain
  in history. Reviewer profiles record qualifications; adjudications reference
  judgments from at least two distinct reviewers of the same passage.
- Durable seven-method v2 comparisons from Studio: explicit bounded song scope,
  pinned analysis and benchmark/label identity, progress, cancellation checkpoints
  and downloadable reports. Changed benchmark material invalidates queued runs.
- Missing top-ten labels withhold nDCG@10. Unresolved cases remain ungraded.
- Bookmarkable Studio tabs; readable small labels and flat research surfaces.
- Patched Vite within major version 7 and updated source-map-js. Final npm audit
  reported zero vulnerabilities; this is a point-in-time dependency check.
- macOS/Linux Docker startup and backup scripts, plus study and recovery guides.

## Executed verification

| Check | Result |
|---|---|
| Complete Python suite in Docker, including PostgreSQL integration | 76 passed |
| Consumer Chromium flows | 4 passed |
| Context-path explanation / legacy-control browser flow | 1 passed |
| Pilot preparation / export / queued comparison / report browser flow | 1 passed |
| TypeScript and production frontend build | Passed |
| Ruff, dependency consistency and shell syntax | Passed |
| Mobile/tablet/desktop study widths | No horizontal page overflow at 390, 768, 1440 px |
| Recovery backup | Created; database dump listing and archive readability verified |

There is one upstream Starlette/httpx test-client deprecation warning. The full
destructive restore procedure was documented, not executed against the live data.
Browser checks create labelled synthetic software-check benchmarks; these are
not expert research contributions. Raw local logs are under
`artifacts/completion-verification/`.

## Fresh bounded feasibility packet

Local artifact: `artifacts/study-preparation/90fa73222af776b4/`.
Files: `audit.json`, `annotation-packet.json`, `annotation-packet.md`.

Eight analyzed real-song IDs with 3–80 events were selected in ID order, before
inspecting comparative scores. All 395 chord events parsed as known. The fixed
`ii V I` query used a key-path budget of 4 for its candidate audit: 334 indexed
starts versus 395 exhaustive starts, with all exhaustive fixed-model top-ten
results retained and no candidate-limit truncation. The packet also records
approximation curves at budgets 4, 16 and 64.

This is a feasibility sample, not a representative catalog sample or independently
classified ambiguity set. It measures computational behavior for a fixed model;
human relevance and independent review remain pending. The packet is ungraded.

## Scientific work that follows

See [study workflow](study-workflow.md), [research specification](research-proposal-v2.md)
and [alignment report](research-v2-alignment.md). Obtain qualified independent
feasibility review before expanding to a pilot. Strong prior-work comparators,
full overlap and pooling audits, protocol freezing and held-out evaluation are
still required before paper-level comparative claims. The application cannot
verify a reviewer's expertise or independence merely from a profile entry.

See [local operations](local-operations.md) for backup/recovery. The local backup
is under `artifacts/backups/20261028T212540Z/`; copy it to a separate device to
protect against another device failure. Catalog metadata processing continues
incrementally and depends on upstream availability and local processing budget.

## Interface notes

The existing Studio identity and shell were retained. The new study section uses
the skill's data-terminal direction with existing palette/type; an initial light
framed-sheet draw was replaced because the established app is dark. Its main
question is which protocol and review evidence is ready; real query/annotation
counts supply the content, with unavailable metrics shown explicitly. New source
lint passed. Visual checks prompted larger existing labels and flatter surfaces.
The legacy controls intentionally follow the pilot panel; they remain accessible
below it instead of competing with the current study workflow.

Final rendered inspection: zero failures and five warnings. The retained low-alpha
panel edges were visually checked (the meter reports their uncomposited RGB);
11–12 px text remains on legacy metadata and sublines; legacy experiments start
below the pilot workflow deliberately; form spacing separates related actions;
the phone's edge-text warning refers to its fixed navigation item, while page
content keeps its own gutter. Desktop, tablet and phone renders were inspected.
