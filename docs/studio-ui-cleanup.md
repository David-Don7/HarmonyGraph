# Research Studio UI cleanup — 29 October 2026

The five research workflows remain available. Retrieval algorithms, persisted
judgments and datasets were not changed by this interface update.

## Removed from the primary interface

- Search marketing hero, decorative chapter numbers, preset artwork and the
  duplicated record shelf.
- Fake researcher account row, slogans, duplicate navigation/status/footer copy.
- The `Unresolved` search-card fallback caused by missing legacy key fields.
- Empty legacy hypothesis panels on v2 results.
- Fixed deterministic weight displayed as if it were complete posterior coverage.
- Repeated 100% conditional-function labels and rounded 0% relation rows.
- Inapplicable key-path-budget and fuzzy-tolerance controls.
- The legacy modulation-pattern selector from the v2 progression form. The backend
  pattern capability remains available to legacy/API/CLI workflows.

## Clearer evidence

- Model scores use six decimals, with bounds notation near exact zero/one.
- Retained/omitted joint mass uses four percentage decimals; tiny residuals do not
  round into certainty. Legacy averaged-key mass is labelled separately.
- Result counts say passages shown; diagnostics identify candidate starts and
  processing seconds. Candidate-cap warnings remain visible.
- Score bounds use overall ranking bounds when preferences affect the score.
- Leading interpretations are labelled as one reading. Detailed paths, score
  contributions and raw provenance are expandable; large path lists load on demand.
- Song details retain the analysis ID from a clicked search result.
- Function readings show the assumed key's probability. Duplicate relation types
  and event ranges are grouped; individual hypotheses/weights remain inspectable.

## Simpler workflows

- Effective controls appear only for the selected search mode/model. Additional
  requirements and ranking preferences have separate groups; hidden active filters
  are counted. Context-path search starts at budget 4.
- Data & jobs prioritizes queued/running jobs and failures. Completed history,
  imports, analysis versions and fixtures are expandable. Recurring job completion
  is explicitly a batch status.
- Benchmark/reviewer creation is secondary; explanation ratings are hidden during
  independent relevance grading. Query forms reset between reviewers/queries.
- Experiments starts with the current context-path comparison. Legacy experiments
  and tuning are collapsed and explicitly identified. Comparisons default to the
  chosen benchmark's source songs, with optional custom scope.
- Missing relevance metrics say ungraded, rather than implying zero performance.

## Verification

- TypeScript and Vite production build passed.
- 14 Chromium checks passed against the Docker frontend: four consumer scenarios,
  two live research workflows and eight targeted Studio UI regressions.
- UI regressions cover score/mass precision, near-certain values, candidate limits,
  ineffective controls, deterministic semantics, conditional functions, recurring
  batches, independent review and comparison scope.
- Source design lint: zero failures/warnings. Rendered production checks at 1440,
  768 and 390 px: zero failures. Search has one intentional empty-space warning:
  the results area remains empty until a query is submitted.
- The live comparison check used a temporary comparison-only worker because an
  existing full-corpus demo analysis occupied the normal worker. That analysis
  was not stopped. Only the production web container was rebuilt/replaced.

The data-terminal direction (seed 1436413720) retains the dark workspace and gold
selection marks. Musical accidentals such as sharp/flat symbols are meaningful
notation and intentionally exempted from the decorative-emoji source lint rule.
Local verification logs/screenshots are under artifacts/studio-ui-cleanup/.
