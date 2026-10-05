# HarmonyGraph: Context-Sensitive Harmonic Passage Retrieval under Tonal Uncertainty

Proposed research specification, 1 October 2026. This document describes planned work, not established results. The [novelty audit](novelty-audit-2026-10-01.md) provides the cited prior-work comparisons and search limitations.

User constraints: no current deadline or target venue; access to music-theory annotators is not yet established. Proceed by evidence gates rather than a fixed delivery date. The larger benchmark below is conditional on obtaining independent annotation support.

## Replacement research statement

HarmonyGraph investigates whether retaining coherent alternative local-key and harmonic-function paths improves retrieval of short harmonic passages from noisy symbolic chord collections. Existing work already supports harmonic similarity, functional analysis, local alignment, and probabilistic chord hypotheses. The proposed study isolates a narrower question: when identical or similar chord sequences admit different interpretations in their surrounding musical contexts, does marginalizing over context-conditioned interpretations improve retrieval relative to deterministic analysis, passage-averaged key mixtures, and key-free alignment?

The system will support explicit functional queries and section-boundary constraints, preserve the probability mass omitted by approximate inference, and expose the interpretations and edit operations contributing to each result. Evaluation will use an independently annotated passage benchmark containing unambiguous controls, context-dependent ambiguities, within-passage key changes, and difficult structural negatives. Experiments will measure retrieval relevance, sensitivity to context, calibration where reference labels support it, candidate-generation loss, and the tradeoff between retained uncertainty and query cost. A versioned relational database and an interactive application will expose the evaluated method and its evidence.

## Contribution to claim, provisionally

The proposed contribution is a controlled study and reproducible retrieval method for **coherent tonal uncertainty at passage level**, supported by a benchmark that tests context dependence and by an audited approximation strategy. HMMs, alignment, posterior marginalization, top-k ranking, and the elementary probability bounds below are existing mathematical tools. The novelty must come from the precise task, method adaptation, and demonstrated findings, not from renaming these tools.

Do not claim “the first uncertainty-aware music search engine.” Safer wording after experiments is: “We evaluate whether coherent local-key uncertainty improves context-sensitive functional passage retrieval, and characterize when it helps, fails, or is lost during indexing.”

## Three primary questions

1. Does path-level marginalization improve nDCG@10 over deterministic paths and averaged-key mixtures on independently identified ambiguous and modulating passages?
2. Does it distinguish passages with similar chord surfaces but different harmonic contexts, without harming unambiguous queries materially?
3. How much retrieval quality and ranking stability are lost as key/function paths and candidate passages are pruned, and what computation is needed to recover them?

Section effects and explanation usefulness are secondary analyses. Hyperparameter tuning is part of fair experimental practice. Broad cross-genre transfer is an extension after the core study is adequately supported.

## Scope and query semantics

Start with chord charts in the Western major/minor tonal idiom. Treat modal, unresolved, and unsupported passages explicitly; a flat 24-key distribution is not a complete model of music outside that idiom. Roman-numeral scale degree and tonic/predominant/dominant function are separate fields. A secondary dominant does not automatically imply modulation.

Primary input: an explicit Roman-numeral sequence of 2–8 events, with optional required section and end/start position. The limit is a feasibility choice, to be adjusted after pilot measurement. Absolute-chord and transposition search remain useful application modes and controls. A short absolute progression with no context cannot be assumed to identify one intended function; ask for a key/function in the interface or show the ambiguity.

Specify hard constraints separately from preferences. “At the end of a chorus” is a hard filter when the user requires it. Unknown section labels do not silently satisfy a known label. For untimed charts, boundary distance means chord-event distance, not beats or seconds.

Use chord-only context consistently for the primary human evaluation. If an additional audio-assisted evaluation is conducted, report it separately: evaluators hearing melody and rhythm have more evidence than a chord-only algorithm.

## Proposed method

For passage P, let C(P) include its surrounding chord context and structural metadata. Let z = (K_1:T, F_1:T) be a coherent key/function interpretation path. Infer a query-independent distribution p(z | C(P)). Conditioning this model on the desired query would bias it toward finding the interpretation the user wants.

An HMM or related sequence model can supply the key-path distribution. Function rules can initially supply conditional alternatives, but their weights are model assumptions until validated. Preserve their dependency on the path and relevant context. Do not independently combine event hypotheses in ways the sequence model considers impossible.

Define bounded alignment similarity a(Q, P, z) in [0,1]. For each path, compute the best permissible alignment with documented edit costs, normalization, and deterministic tie-breaking. Then define:

    S(Q, P) = sum_z p(z | C(P)) * a(Q, P, z)

This is an expected similarity, not automatically a probability that a human will judge the result relevant. A separate match-probability query can be defined as:

    M_tau(Q, P) = sum_z p(z | C(P)) * 1[a(Q, P, z) >= tau]

Choose and freeze the ranking semantics; do not interchange these quantities in experiments or the interface. Start with expected similarity as the primary rank score. If section/boundary preferences are added, document their combination separately. Observed chord-quality evidence should not accidentally shrink solely because a key beam is smaller.

The order of operations matters: expectation of a path's best alignment is generally different from alignment using expected local edit costs. Nor does maximizing over paths measure uncertainty; it can reward an implausible interpretation. Include these simplifications as comparisons where feasible.

### Mass-preserving approximation

For a retained set B of distinct, mutually exclusive complete paths with their original normalized-model probabilities, let:

    m = sum_(z in B) p(z | C(P))
    L = sum_(z in B) p(z | C(P)) * a(Q, P, z)

Because every omitted similarity lies in [0,1]:

    L <= S <= L + (1 - m)

This elementary bound follows directly by bounding the omitted nonnegative terms. It is not a novel theorem, a confidence interval over human relevance, or a calibration guarantee. It is valid only if m is genuine retained probability mass under the stated model. Renormalized beam weights, overlapping paths, and heuristic unnormalized weights cannot be substituted without further justification.

For independent key/function truncations, track their combined mass consistently rather than reporting only key mass. First validate the computation by exact enumeration on tiny synthetic sequences; these are algorithm tests, not musical evidence. Use exact forward normalization and scored path probabilities, or another method whose approximation error can be characterized.

A practical experiment can expand paths for candidates whose score bounds overlap. If one candidate's lower bound exceeds another's upper bound, their order is certified relative to this model and candidate set. A corpus-wide top-k certificate additionally requires bounds for every omitted candidate. The first application should call its result “candidate-set ranking stability” unless that stronger requirement is met.

Do not promise that a beam will capture most path mass cheaply. Long ambiguous passages can require many paths. Measure retained mass, error, and cost; use posterior sampling with properly labelled statistical error as a possible alternative if enumeration is impractical.

### Candidate generation

Keep PostgreSQL and the existing position-aware indexes. Generate candidates from a union of key-free interval/chord features and functional postings from retained hypotheses. A top-1 functional index can discard exactly the candidates that uncertainty is intended to recover.

Use a fixed shared candidate pool for the controlled ranking experiment. Then evaluate each complete retrieval pipeline separately. On a manageable corpus, compare with exhaustive scoring to quantify candidate omission. Report candidate recall against the exhaustive model results separately from relevance against human judgments.

## Benchmark and annotation plan

A music annotator is a person who inspects musical evidence and records labels using a shared rubric. For this project, the person should be comfortable interpreting chord progressions, tonal context, and Roman numerals. A music teacher, a theory-trained performer/composer, or a musicology researcher may be suitable; musical interest alone does not establish the needed expertise.

Because annotator access is currently unknown, use this staged route:

1. Audit existing expert labels in Billboard, Isophonics, and potentially BeatlesFC. They can support selected analysis checks, but none automatically supplies the proposed search-relevance benchmark.
2. Prepare a small annotation packet with 6–10 examples, the evidence shown to the algorithm, candidate interpretations, a relevance rubric, and an “insufficient evidence” option. An academic supervisor may be able to introduce an appropriate reviewer. Do not recruit anyone or send material on the user's behalf without authorization.
3. Ask potential reviewers to complete a small trial independently and discuss whether the rubric is clear. Record qualifications and time required before choosing the full sample size. Disagreement can reflect genuine musical ambiguity rather than reviewer error.
4. Expand to the 24–30-query pilot only when review is feasible. The larger study remains a later decision.

If independent reviewers cannot be obtained, narrow the study to existing reference annotations, known transpositions, and exact-versus-approximate execution of a fixed model. That can support claims about computational correctness, approximation, and performance. It cannot establish new human-perceived relevance, explanation usefulness, or a human-verified ambiguity benchmark. Self-labels or LLM-generated labels may help develop a rubric but must not be relabelled as independent expert ground truth.

Begin with 24–30 pilot queries on a bounded corpus. After revising the rubric using the pilot, target approximately 120 main queries, subject to observed variance and annotation capacity. These are planning numbers, not a power calculation.

| Stratum | Initial target | What it tests |
|---|---:|---|
| Clear tonal controls and transpositions | 30 | Whether uncertainty damages straightforward retrieval |
| Same or similar chord surfaces in different natural contexts | 30 | Whether context changes a supported interpretation and ranking |
| Key changes within passages, tonicizations, and relative-key ambiguity | 30 | Whether coherent paths matter and whether changes are overcalled |
| Approximate matches and structural hard negatives | 30 | Substitutions/edits and explicit section constraints |

Strata are balanced diagnostic samples, not estimated population frequencies. Report each separately and include a corpus-sampled evaluation if making claims about ordinary user traffic. Label subtypes before looking at the proposed system's successes; high model entropy alone must not define the ambiguity test set.

Use real contextual pairs where possible. For example, D7–G–C can support different functions depending on the surrounding passage; do not label it automatically as either V/V–V–I or V–I–IV. Constructed context swaps are useful diagnostics but must be flagged and analyzed separately from natural passages.

Pool top results from all principal baselines and the proposed system, deduplicate overlapping windows, then add random and adversarial negatives. Aim initially for 25–40 unique candidates per main query and expand the pool when judgment coverage at the evaluation cutoff is inadequate. For 120 queries and 30 candidates, two complete independent annotations imply 7,200 relevance ratings, before contextual and explanation labels. Budget this work explicitly.

Have at least two qualified annotators independently judge the main relevance pool if feasible, hiding method identity and scores. If only a subset is double annotated, sample that subset across every stratum and report its size. Keep the raw judgments, disagreements, and adjudication provenance.

Record: relevance 0/1/2 with a written rubric; supported interpretation(s); insufficient-context/unsupported status; section correctness; and whether the label is based on chords alone. A small panel's vote proportions describe that panel, not a universal probability of musical truth. Use adjudicated labels for the primary metric and individual-rater sensitivity analyses for robustness. Avoid scoring unresolved cases as definite negatives.

Group splits by artist, duplicate/cover family, source passage, and query template/transposition family where relevant. Queries derived from the same musical example must not leak across tuning and test. Check overlap across source corpora rather than assuming different dataset names imply independence.

## Baselines and controlled experiments

| Comparator | Purpose |
|---|---|
| Literal and interval matching | Basic product modes and sanity checks |
| Global-key and deterministic local-path functional alignment | Effect of locality and hard analysis decisions |
| Current averaged-key mixture | Direct control for the proposed path representation |
| Uniform versus theory-informed alignment | Effect of edit costs, with uncertainty held fixed |
| Hanna-style local-transposition alignment | Strong key-free approximate retrieval; implement from the paper and validate small examples |
| HarmTrace functional alignment or documented faithful adaptation | Closest functional-retrieval precedent; state any adaptation and implementation limitations |
| Reasonable chord-sequence embedding comparator | Check whether a learned similarity representation offers the same gains; train only on allowed training material |
| Full proposed path expectation | Experimental method |

An adapted algorithm must not be reported as a reproduction of its authors' results. If a strong comparator cannot be run, record the limitation and narrow the paper's claims. A maximal score over the same hypotheses and a shuffled/equal-weight mixture are useful diagnostic controls for whether meaningful probabilities help beyond having more options.

Give all applicable systems identical required section/boundary filters. Evaluate optional structural preferences separately. Use the same model and frozen inference parameters in the main hard-path versus mixture versus path-expectation ablation. In a separate end-to-end comparison, give each method a comparable tuning budget and report it.

Keep the held-out test unused until the method, label rubric, exclusion rules, normalization, candidate budget, and hyperparameters are frozen. Begin with a small search space; 100–300 trials on a tiny validation set may simply overfit it.

## Measurements and decisions

Primary outcome: per-query nDCG@10 with an explicit gain mapping, such as 0/1/3 for relevance 0/1/2. Report differences with confidence intervals using resampling clustered by source/query family when observations are dependent. Predeclare the principal comparisons; mark further analyses exploratory.

Secondary outcomes: context-pair ordering accuracy; performance on each ambiguity subtype; judged-pool coverage; candidate recall against exhaustive scoring; retained mass and score error; top-10 stability as the beam grows; median/p95 latency; indexing time; database/index size; and peak memory. Fix hardware, corpus size, cache state, query concurrency, and candidate count for latency measurements.

Report corpus-wide recall only where relevance is exhaustively known. Calibration should match available ground truth: evaluate tonic marginals if only tonic is annotated, not fictitious tonic-plus-mode labels. Function and local-key calibration are separate from relevance calibration. Use Brier/log-loss where categorical reference labels are justified; do not overinterpret small-sample ECE. Predefine handling of zero probabilities and unresolved annotations.

For explanations, first verify that component contributions reproduce the score. Display the leading alternative paths and omitted mass, not just one attractive interpretation. Human usefulness can be studied separately through randomized presentation with the retrieved result held constant.

Decision gates:

1. **Data gate:** source parsing works, contextual examples exist, and annotators can apply the rubric. Otherwise reduce or reframe the task before scaling.
2. **Method gate:** exact tiny-case checks validate probabilities, coherent paths, alignment semantics, and bounds. Heuristic weights remain labelled as such.
3. **Pilot gate:** establish relevance variance, annotation burden, and feasible path mass/cost. Revise using pilot/development data only.
4. **Study gate:** freeze and run the main comparisons. Report null or adverse results; do not require every hypothesis to win.
5. **Paper gate:** make only claims supported by the held-out study, with closest prior work and failure cases included.

## Working application plan

The repository already supplies much of the required infrastructure. Reuse it and implement the research method as a versioned alternative so the current mixture remains reproducible.

| Work package | Concrete deliverable |
|---|---|
| Data/reference audit | Pinned releases, parsing coverage, unknown labels, overlap groups, reviewed contextual examples |
| Path evidence | Versioned key-path hypotheses with original probabilities, function alternatives, retained mass, and inference settings |
| Retrieval extension | Explicit expected-score semantics, path-conditioned alignments, candidate-set bounds, and exhaustive small-corpus audit |
| Annotation | Frozen query contexts, blinded pools, unresolved labels, independent ratings, and adjudication records |
| Strong baselines | Source-linked implementations/adaptations and sanity examples |
| Experiments | Frozen manifests, metrics, uncertainty/latency curves, statistical comparisons, and failure analysis |
| Interface | Query constraints, matched passage with context, alternative key timelines, score decomposition, and approximation status |
| Paper | Related work, task definition, method, benchmark protocol, measured results, limitations, and reproducibility package |

Schema additions can be small: interpretation-path records, path events, path mass summaries, immutable query context, and approximation-audit results linked to existing analysis/configuration/experiment IDs. PostgreSQL is sufficient. A separate graph database is unnecessary unless an actual graph-query experiment motivates it.

There is no fixed schedule because the user has no current deadline and annotation support is unresolved. Complete data/rubric feasibility first, then the path method and strong baselines, then independent evaluation, and finally the paper. The next concrete milestone is an audited small corpus plus a reviewable 6–10-example annotation packet. The large benchmark should not become a prerequisite for making initial engineering progress.

Defer natural-language search, GNNs, music generation, more ontology infrastructure, and broad recommendation features. They do not resolve the primary research question.

## Proposed abstract before results

Harmonic passage retrieval is sensitive to uncertain tonal interpretation: similar chord sequences can serve different functions depending on their surrounding context, while a single passage may traverse multiple keys. We propose HarmonyGraph, a system for evaluating context-conditioned functional retrieval over alternative local-key and harmonic-function paths. The method ranks passages by expected alignment similarity and tracks probability mass omitted during approximation. A controlled benchmark will compare path-level marginalization with deterministic analysis, averaged-key mixtures, key-free alignment, and functional similarity baselines, using independent graded judgments and difficult contextual negatives. The accompanying database and application preserve source evidence, inference versions, structural constraints, and score explanations. The study will characterize the conditions under which tonal uncertainty improves retrieval and the quality–cost tradeoffs introduced by indexing and path pruning.

Replace the prospective wording with actual methods and measured findings only after completing the study. This is ready to discuss with a supervisor as a focused proposal; it is not yet a completed research paper.
