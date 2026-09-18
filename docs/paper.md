# HarmonyGraph: Uncertainty-Aware Functional Harmony Retrieval

**Status:** research paper scaffold. Synthetic software demonstrations only; expert annotation and real-corpus evaluation are pending.

## Abstract

HarmonyGraph is a reproducible platform for investigating local harmonic uncertainty in symbolic progression retrieval. It combines a 24-state major/minor Hidden Markov Model, weighted functional interpretations, structural constraints, indexed candidate generation, theory-informed alignment, and auditable scoring. This implementation supports controlled baselines, ablations, and validation-only hyperparameter optimization. Claims about retrieval superiority, generalization, and explanation usefulness require the planned external-corpus and human evaluations.

## 1. Motivation and research questions

Global key assumptions and exact chord names can conceal functional equivalence. Conversely, a confident but incorrect local analysis can propagate errors through retrieval. The principal question is whether preserving alternatives and section context improves ranked passage retrieval compared with literal, interval, global-key, deterministic-local, and uniform-edit methods.

## 2. Data and provenance

The included demonstration comprises 120 original synthetic songs with explicit section labels, transformed across all twelve roots. Constructed labels describe fixture intent and are not expert judgments. Chordonomicon, McGill Billboard, and Isophonics adapters accept user-supplied releases. Raw annotations remain separate from inferences. Input fingerprints, algorithm versions, configuration hashes, and split manifests identify all experiments.

Report for the final study: release identifiers; license and attribution; imported/rejected/unknown counts; duplicate groups; artist coverage; genre and period distributions; benchmark sampling; independent annotator qualifications; disagreement and adjudication procedure.

## 3. Method

### Canonical representation

Chord events retain original spelling, root pitch class, quality, pitch-class intervals, bass, event order, section, and available timing. Unsupported chords and no-chord events are distinct. Functional Roman numerals use major-reference altered scale degrees in both modes, with lowercase minor triads.

### Local-key uncertainty

Emission evidence combines scale compatibility, tonic and dominant evidence, bounded duration weights, and moving-window context. The transition model discourages changes and reduces that penalty at section boundaries. Forward-backward yields marginal posteriors; Viterbi yields a separate most likely path. The full 24-state posterior is retained. Top-k retained mass is exposed without renormalizing it for probabilistic retrieval.

The first rule system handles major/minor tonality and conditional secondary-dominant and parallel-mode borrowing interpretations. These are explicit heuristics. They are neither a learned theory model nor a guarantee of calibrated probabilities.

### Candidate retrieval and alignment

Position-aware token/interval postings generate candidate starts. Literal n-grams are materialized. Structural constraints eliminate impossible positions before reranking. Approximate queries explore bounded insertion/deletion drift and passage lengths; candidate truncation is reported. An explicit exhaustive audit measures candidate-start recall on a bounded corpus.

Weighted dynamic programming separates insertions, deletions, repeated chords, and degree/function/quality disagreement. A bounded interpretation beam integrates functional alternatives. Explanations expose the chosen alignment and the retained interpretation mass.

### Ranking

The score follows the supplied four-component expectation, including chord similarity inside the key expectation. Only active optional structural score terms receive normalized weights. Required constraints are hard filters. Optional harmonic features break equal-score ties and do not introduce an undocumented fifth score term. Literal and transposed search use exact canonical matching as their acceptance criterion.

### Reproducibility and optimization

Grouped partitions connect songs sharing artist, declared duplicate group, or canonical content. Optimization uses the validation partition, seeded Optuna TPE or random sampling, persistent trial records, and optional latency constraints. A frozen manifest is required before test evaluation; subsequent test runs require an explicit recorded rerun.

## 4. Experimental protocol

1. Collect approximately 100–200 queries spanning the brief's categories.
2. Pool candidates, retain unjudged status, obtain independent graded relevance labels, and document adjudication.
3. Evaluate B1–B6 and the proposed configuration on identical query and corpus partitions.
4. Run the eight component ablations and transfer experiments by genre, period, and dataset.
5. Report pooled recall, nDCG, precision, MRR, MAP, judgment coverage, confidence intervals, and paired differences.
6. Evaluate local-key and harmonic-reference annotations where available; mark missing metrics unavailable.
7. Measure indexing cost, storage, warm/cold query latency, throughput, and candidate recall under stated hardware and corpus sizes.
8. Freeze the complete manifest, perform the held-out evaluation, and report all outcomes, including negative findings.

## 5. Results

See `docs/demo-results.md` for executed software demonstrations and their exact limitations. These results must not be used as evidence supporting the research hypotheses.

**Real-corpus retrieval results:** pending.

**Expert harmonic-analysis and explanation evaluation:** pending.

**Cross-domain generalization and full-corpus scalability:** pending.

## 6. Limitations

The default tonal state space excludes independent modal keys. Rule-based functional alternatives cannot resolve all musical ambiguity. Chord-only cadence candidates omit melodic and voice-leading evidence. Bounded indexing can miss fuzzy matches, especially when few query tokens survive. Confidence is not established calibration. The synthetic corpus is small and deliberately regular. Named local profiles support independent workflow views, not authenticated identities. SQLite is a development fallback; PostgreSQL is the deployment and concurrency target.

## 7. Reproducibility checklist

Archive the dataset fingerprint, source adapters, parsing report, algorithm and dependency versions, frozen configuration, split and benchmark hashes, annotation audit history, experiment export, and measurement environment. Report final-test reruns. Do not omit failed or pruned optimization trials.

## References to complete and verify

- Kantarelis et al. CHORDONOMICON: A Dataset of 666,000 Songs and their Chord Progressions. https://arxiv.org/abs/2410.22046
- Burgoyne, Wild, and Fujinaga. An Expert Ground Truth Set for Audio Chord Recognition and Music Analysis. ISMIR 2011.
- Isophonics reference annotation documentation: https://isophonics.net/content/reference-annotations.html
- Akiba et al. Optuna: A Next-generation Hyperparameter Optimization Framework. https://arxiv.org/abs/1907.10902

Add and verify the theoretical key-profile, alignment, calibration, and statistical references used in the final study before submission.
