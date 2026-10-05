# HarmonyGraph: Context-Sensitive Harmonic Passage Retrieval under Tonal Uncertainty

**Status:** methods scaffold and bounded computational checks. Independent annotation, strong prior-work comparisons and held-out findings are pending. This document follows [research v2](research-proposal-v2.md) and the [novelty audit](novelty-audit-2026-10-01.md).

## Research questions

Does marginalizing coherent key/function paths help context-sensitive functional retrieval compared with deterministic paths and averaged-key mixtures? Does it distinguish similar chord surfaces in different natural contexts? What is lost through path and candidate pruning? These are questions, not demonstrated advantages. HMMs, posterior marginalization, alignment and elementary probability bounds are established tools.

## Task and data

Primary queries contain 2–8 explicit Roman numerals. Required section/boundary conditions are hard filters; optional preferences are separate. The evidence is chord-only, in a Western major/minor idiom. Modal or unsupported contexts remain limitations. Roman degree, broad harmonic function and harmonic cadence candidates are distinct claims.

Chordonomicon supplies naturally occurring chord charts, not passage-relevance truth. Preserve the pinned release, file checksum, source rows and CC-BY-NC-4.0 attribution. Billboard tonic labels do not imply mode; Isophonics missing changes are not evidence that no change occurred. Audit external reference coverage before using it. Synthetic fixtures test algorithms only.

## Implemented method

`context-path-expectation-v1` uses the existing 24-state HMM emission/transition model and full chart context. Forward/backward messages marginalize states outside a passage. Inside it, posterior conditional transitions define coherent key paths. Function alternatives depend on the path key and the following observed chord; their conditional weights remain unvalidated theory assumptions.

A prefix key beam and a conditional function beam retain distinct complete passage assignments with their original normalized-model probabilities. They are not guaranteed to be the globally highest-probability joint paths. The query never changes the path distribution. Weighted global dynamic programming finds each retained path's best alignment, with deterministic diagonal/deletion/insertion tie order and normalization by the larger sequence length.

Primary score is the retained partial expectation `L = sum p(z|context) a(Q,P,z)`. Joint retained mass is `m`; the complete-model expectation satisfies `L <= S <= L + 1 - m`. This is not a confidence interval for human relevance. Match-probability bounds at a specified threshold are a separate output, never substituted for the rank score. Optional preferences combine as `(L + w_section*s + w_boundary*b)/(1+w_section+w_boundary)`; the same transform applies to score bounds. There is no extra observed-quality term multiplied by beam mass.

The old passage-averaged-key method remains `legacy_mixture`. Hard-path, maximum, equal-weight, shuffled-weight and uniform-cost controls are explicitly labelled. Their diagnostic scores must not be mistaken for the primary expected score. Indexed candidate generation unions retained functional postings and key-free quality/interval evidence. Candidate omission is audited separately from path truncation. Membership certificates refer only to evaluated candidates.

## Evaluation protocol and gates

The current deliverable is a bounded computational audit and eight-example chord-only review packet. Source-ordered natural sections are not an expert-verified ambiguity benchmark. A 24–30-query pilot requires qualified independent reviewers; a later approximately 120-query study depends on feasibility and variance.

The development runner shares candidate starts, configuration, analysis and hard filters across methods. Primary labels are resolved adjudications; independent-rater sensitivity is supported separately. Missing and unresolved judgments are excluded from ground truth, not converted to grade zero. Relevance gain is 0/1/3, with source/query-family clustered paired bootstrap intervals. Raw disagreements and adjudication provenance remain stored. Audio-assisted ratings are separate.

Hanna-style local-transposition alignment, a faithful documented HarmTrace adaptation, a train-only chord-sequence embedding and expected-local-cost alignment remain required comparisons before research superiority claims. Their absence is an explicit study gate. The v2 runner refuses held-out queries until a full study protocol is implemented and frozen; legacy test results do not satisfy that gate.

## Results

See [the alignment report](research-v2-alignment.md) for executed algorithm tests and the bounded real-chart audit. No independently judged retrieval relevance, explanation usefulness, calibrated-function performance or research superiority result has been established.

## Limitations and reproducibility

Record release/content hashes, inference and path-model versions, query contexts, method settings, candidate budgets, exclusions, rubric, family/cover/cross-corpus overlap groups, cache/hardware state and test-use history. Small software fixtures cannot validate musical interpretation. Prefix pruning can lose substantial mass; high mass is not promised. The existing product metadata/catalog coverage is distinct from research evidence.

## Related work

Use the source-linked comparisons in [the novelty audit](novelty-audit-2026-10-01.md), especially Hanna, Robine and Rocher (2009), HarmTrace (2011), and prior probabilistic tonal/harmonic retrieval. Implementations must be documented adaptations or validated reproductions, never relabelled authors' results. Hyperparameter optimization is methodology, not the principal contribution.
