# Research Studio: explanation and demonstration guide

This guide describes the current implementation, including its limitations. Live
search examples were checked on 29 October 2026. Catalog contents and interactive
candidate pools can change as workers publish additional data.

## The five pages

| Page | Question | Role |
|---|---|---|
| Harmonic search | Which passages match this musical request? | Run a query and inspect machine evidence |
| Song explorer | What did the model infer about this chart? | Inspect chords, sections, keys and functions |
| Data & jobs | What data and computed evidence exist? | Import, analyze, monitor and manage work |
| Benchmark lab | Which matches do people judge relevant? | Build review pools and record independent judgments |
| Experiments | Does one method rank useful passages better? | Compare methods against judgments and export evidence |

Search makes predictions. Benchmark lab records human judgments. Experiments
compare predictions against those judgments. A working search and a completed
scientific study are different milestones.

## Search modes and query notation

- **Literal:** enter chords, e.g. `G7 C`. Preserve exact canonical chord identities.
- **Transposed:** enter chords, e.g. `G7 C`. Preserve chord shapes and one consistent
  pitch shift; another match could be `A7 D` or `B7 E`.
- **Functional:** enter Roman numerals, e.g. `V7 I`. Under research v2 this ranks
  fixed-length passages by expected alignment similarity. It is not a guarantee
  that every returned interpretation exactly equals the query. The legacy
  functional mode has an exact-reading acceptance requirement.
- **Fuzzy functional:** enter Roman numerals and allow approximate alignments.
  Candidate windows may contain up to two fewer or two more chord events.

Roman numerals describe degrees relative to a key: I is the tonic, ii is a minor
second-degree chord, V is the dominant. `7`, `maj7`, `bVI`, and `V7/V` describe
chord quality, altered degrees or a secondary dominant. Research path queries
accept 2–8 events. Broader legacy queries support longer sequences.

## Three research models

| Model | Representation | Treatment of uncertainty |
|---|---|---|
| Context paths · research v2 | Several complete key/function sequences across a passage, conditioned on the full chart | Original model probabilities weight each path's best alignment |
| Averaged keys · legacy baseline | Average event-level key probabilities, then interpret the whole passage under selected fixed keys | Mix fixed-key readings; ordered key changes are not preserved |
| Deterministic path · control | One Viterbi key sequence and leading function choices | Assign weight one to that chosen interpretation |

Deterministic does not mean one unchanging key: its selected path can change key.
The difference is one selected trajectory versus multiple plausible trajectories.
Averaging can make a passage that changes C→G look like a mixture of C and G
without preserving where the change occurred. Context paths preserve ordering.

### Key-path budget

A key path assigns a key to every event in the passage: for example C→C→C,
G→G→G or C→G→G. Budget 4 retains up to four key-path prefixes at each beam-search
step; 16 keeps more alternatives. It is not the number of possible keys, songs,
results or seconds. There are 24 key states, while their possible sequences grow
with passage length. Prefix pruning is approximate, not guaranteed globally best
joint-path selection.

Each key path may have multiple function readings. Consequently a budget of 4
can produce more than four joint key/function paths. Function branching has its
own backend budget. Larger budgets usually cost more computation and can reduce
omitted mass; meaningful rank changes are not guaranteed. The legacy model does
not use this key-path beam, and deterministic scoring still uses one selected path.

## Filters and preferences

| Control | Meaning |
|---|---|
| Section | Require all events of a match to belong to the requested normalized section kind |
| Position: Anywhere | No boundary restriction |
| Position: Section start / ending | Require the match to start/end within the selected boundary distance |
| Position: Inside section | Both boundary distances must exceed that distance |
| Position: Near boundary | At least one boundary distance must be within that distance |
| Genre | Require matching stored genre metadata |
| Local key | Filter using the method's retained key interpretations; not a claim about the recording's global key |
| From / To year | Filter stored release years; missing years do not satisfy a required range |
| Required relation | Require the detected feature to occur within the matched window at the model's confidence threshold |
| Tie-break relation | Prefer matches with that feature as a tie-breaker; this does not add a new percentage to the displayed score |
| Boundary distance (events) | How many chord events away from the boundary are permitted, 0–16; zero means the exact boundary |
| Preferred position / section | Soft score contributions; other matches remain eligible |
| Legacy alignment tolerance | Only shown in legacy fuzzy mode, where it affects acceptance |
| Allow crossing sections | Permit a window to span section boundaries, subject to any separate hard section requirement |
| Match every chorus | Keep songs whose every annotated chorus has a qualifying match among evaluated candidates |

Required evidence choices are secondary dominant, secondary-dominant chain,
borrowed chord, dominant resolution, plagal motion, modulation and half cadence.
These are rule/model-generated candidates, not expert-certified analyses.
Secondary dominants temporarily point toward another chord; a chain links these
motions; borrowed chords suggest a parallel-key reading; dominant resolution
resembles V→I; plagal motion resembles IV→I; half cadence is a candidate ending
on V. Chord-only evidence cannot establish all rhythmic or voice-leading details.

Hard filters remove results. Preferences affect ranking. Start with all advanced
filters empty; add one at a time. More filters can eliminate useful demonstrations.
The every-chorus condition operates on a bounded candidate search, so a missed
candidate can also exclude a song.

## Reading search results

- **20 passages shown:** up to 20 returned passages, not necessarily 20 unique
  songs. A song can have several matching sections or chart variants.
- **500 candidates:** candidate starts considered before final ranking, not the
  size of the entire corpus. The default ceiling is 500.
- **12221 ms:** approximately 12.2 seconds of search processing, not passage length.
- **Candidate limit reached:** eligible candidates were truncated. Other corpus
  matches may have been omitted; this is separate from omitted interpretation mass.
- **Events 16–17:** one-based chord-event positions in the chart, not beats/seconds.
- **Chords / Roman numerals:** observed labels versus the leading displayed reading.
  That reading is one contribution, not the full expected score.

### Match scores

With no preferences, the v2 score is the sum of each retained path's model
probability times its alignment similarity. For example, hypothetical paths with
probabilities .6/.3, similarities 1/.5, and omitted mass .1 give a retained score
of .75. The complete expected score is between .75 and .85. These are model bounds,
not confidence intervals over human relevance.

Soft section/boundary preferences can modify the displayed overall score; inspect
Score contributions. Each row shows value × normalized weight = contribution.
The contributions sum to the displayed overall score. Legacy scoring combines
functional and chord evidence, plus active preferences. Deterministic scoring
uses the selected path rather than a weighted uncertainty mixture.

A score of 1.000 does not mean 100% human relevance or certain musical truth.
The revised interface displays scores to six decimals and model mass to four percentage decimals.
Very small residuals use less-than/greater-than notation instead of false zero or certainty. Compare scores within the method
and settings that produced them; a larger number from a different scoring model
does not establish better retrieval quality.

### Three different kinds of percentage

1. **Local-key probability:** model support for a key at an event or under the
   legacy passage summary. It has not been calibrated against human confidence.
2. **Conditional function weight:** given a particular key, how its function
   alternatives are weighted. G can be V in C, IV in D and I in G, each with
   conditional weight 100%. That does not make all three keys 100% probable.
3. **Retained mass:** how much of the relevant model distribution was kept.
   V2 reports joint key/function mass; legacy reports retained averaged-key mass.
   Deterministic mass 100% is a consequence of its point-mass control definition,
   not proof it captured the original uncertain posterior.

In Alternative context paths, inspect retained/omitted mass, bounds, original
probability, ranking weight, similarity and contribution. Match/insert/delete/
substitute operations describe alignment edits and their costs, not edits to the
source chart. Stored evidence provides precise decimals, source and configuration
IDs, context labels and candidate-set certificates. Such certificates refer only
to evaluated candidates, not every passage in the corpus.

### Unresolved judgments

The misleading fallback badge has been removed from search results. V2 results
show path evidence directly; missing legacy key fields no longer imply ambiguity.
In Benchmark lab, unresolved means a reviewer cannot supply a defensible relevance
grade. It remains null rather than becoming grade zero. Grade zero means a
reviewer could judge the passage and found it irrelevant.

## Song explorer

Search by title, open a song, then click individual chord-event buttons. The
chart is divided into annotated sections. The key under each chord is the chosen
HMM path's state. The key table shows up to five nonzero probabilities out of 24 states,
so the shown values need not sum to 100%.

Functional alternatives are conditional readings of the selected chord. Each key now displays its model probability separately; redundant 100% single-function
weights have been removed. Multiple function alternatives retain their conditional weights. Tonic is a home role, dominant a tendency
toward resolution, and predominant a broad preparatory role assigned by the rules.

Harmonic relation candidates are grouped by relation type and event range.
Individual hypotheses and weights remain in technical details. The main list
does not present tiny rounded weights as 0% relations or imply verified cadences. Source annotations preserve imported evidence separately from inference.

## Data & jobs

This page manages the computation that makes search possible.

- **Load synthetic demo:** adds 120 constructed research songs and a demonstration
  benchmark. Useful for isolated repeatable software checks; unnecessary for a
  real-catalog presentation. It is not independent scientific evidence and can
  activate a different research analysis. Prefer a separate demo environment.
- **Adapter:** selects how JSONL, Chordonomicon, Billboard or Isophonics input is
  parsed. It does not download arbitrary inputs by itself.
- **Path within the data folder:** a server/container path such as
  `imports/my-corpus.jsonl`, corresponding to host `data/imports/`; not a browser
  file-upload field.
- **Source license:** records reuse/attribution information; does not grant rights.
- **Queue import:** schedules ingestion rather than requiring the browser to stay open.
- **Datasets / fingerprint / validation report:** source identity and parsing results.
- **Analyze & index corpus:** computes tonal/functional evidence and lookup indexes.
  Do not rerun for each search. Full-corpus analysis can be expensive.
- **Analysis versions / Activate:** retain earlier computed versions and choose a
  ready research version. A failed analysis must not replace a usable one.
- **Background jobs:** queued, running, completed, failed or cancelled tasks. The
  cancel button requests cooperative stopping, not immediate termination.

Catalog job kinds: download gets the pinned source, import stores its records,
metadata resolves titles/artists, and analyze indexes eligible songs and publishes
snapshots. Metadata/index jobs repeat in batches, so percentages can reset and
100% for a batch does not mean the whole catalog is finished. Inspect outputs,
coverage counts, timestamps and errors. Research comparison jobs also appear here.

## Benchmark lab

A benchmark is a collection of queries with judged candidate passages. It is not
merely the catalog of songs. Create a clearly labelled presentation/practice
benchmark when demonstrating the workflow; practice ratings are not expert data.

Create an annotator profile with qualifications. Create a benchmark and add queries:

- **Progression / Query model:** define the musical request and interpretation method.
- **Category / reviewed subtype:** e.g. clear control or a reviewer-established
  ambiguity type. Do not label a passage ambiguous solely because a model is unsure.
- **Source/query family:** group dependent examples, covers and transpositions to
  avoid spreading related examples between tuning and evaluation.
- **Research phase:** pilot tests feasibility; train develops methods; validation
  selects settings; test is held out. V2 comparisons currently reject test queries.
- **Source song ID:** pins the chart context and its hash; suggestions show named
  analyzed songs. This provides provenance, not a relevance answer.

Build candidate pool gathers passages from several retrieval modes. It does not
assign human truth. Independent mode hides method scores and other reviewers'
answers. Relevance grades: 2 supported, 1 partial, 0 not relevant; unresolved stays
ungraded. Optional correctness/clarity/usefulness ratings use 1–5 and concern
explanations; leave them blank during blinded relevance review.

Review mode reveals history and enables adjudication. Select source judgments
from at least two distinct reviewers for the same passage. Editing a query creates
a new benchmark revision; judged pools cannot silently be rebuilt. JSONL export
contains query records/context/pools, not a complete database backup. Use the
blinded packet export for reviewers because ordinary records can contain scores.

## Experiments

### Context-path comparison: current v2 development workflow

1. Select a benchmark. Protocol checks identify missing context, families, subtypes,
   invalid phase/query forms and declared split overlap.
2. Candidate-pool readiness means review material exists. Independent-review
   completion counts qualified-profile double reviews and resolved adjudications.
   Self-reported qualifications do not verify expertise or real independence.
3. Download blinded packet to review offline, or use Benchmark lab.
4. Complete responses and reviewer minutes, choose the correct profile and import.
   The material hash must still match; invalid batches are rejected atomically.
5. Choose 1–50 explicit development song IDs, or Use source songs. This is the
   comparison corpus, not the entire catalog. Choose the path budget and queue.
6. The worker pins analysis and benchmark/label identities and compares seven
   methods using one common candidate-start pool. Changing labels/material while
   queued or running requires a new comparison.
7. Download its JSON report. nDCG@10 measures whether high human grades appear
   near the top relative to the judged pool's ideal order. Unavailable is expected
   without resolved top-ten judgments; it does not mean a zero-performing model.
   Judged at 10 counts resolved labels among the returned top ten.

Seven controls: averaged-key mixture, deterministic path, context-path expectation,
uniform alignment costs, maximum-over-paths, equal path weights and shuffled path
weights. Diagnostics isolate aspects of the method; they do not substitute for the
strong prior-work comparators still required by the proposal.

### Legacy experiment panel below it

- **Benchmark / Configuration:** choose saved queries and model parameters.
- **Split:** train, validation or test; validation is for tuning.
- **Include eight ablations:** remove/change components such as uncertainty,
  locality, functions, quality, structural preferences or edit costs. Hard filters
  remain requirements rather than being silently discarded.
- **Run comparison:** legacy B1–B6/proposed comparisons; the web run uses six queries
  per split. B1 is absolute, B2 interval, B3 global key, B4 deterministic local,
  B5 uniform edit and B6 manual settings. “Proposed” here is the older model.
- **Freeze for final test:** pins relevant identities for legacy test evaluation;
  it does not make unfinished v2 held-out testing available.
- **Explicit test rerun:** records deliberate reuse of a test set.
- **Automatic parameter optimization / trials:** Optuna tries alternative settings
  on validation data. Three trials are a smoke test, not a finished tuning study.
  This is parameter search, not neural-network training or proof of novelty.
- **Measured results / exports:** metrics, timings, configuration/manifests and
  reports. Statistical intervals across judged queries are different from omitted-
  mass bounds on one model score.
- **Optimization studies:** trial history and selected settings.

Browser workflow check benchmarks contain constructed software scenarios. Their
successful execution is not independent human relevance evidence.

## A professor demonstration with concrete cases

Start in Harmonic search with all advanced filters cleared and no preferences.
Read-only live model and budget checks are in `artifacts/studio-demonstration/`.
Other cases below specify settings and expected behavior, rather than guaranteed
recording titles.

| Case | Settings | What to demonstrate |
|---|---|---|
| A: exact pattern | Literal; `G7 C`; any section/position | Returned windows preserve G7 then C |
| B: transposition | Transposed; `G7 C`; same filters | Other-key dominant-seventh→major patterns may match; no function proof |
| C: contextual interpretation | Functional; `V7 I`; Context paths; budget 4; chorus; section ending | Inspect interpretations, context, alignment and mass |
| D: deterministic comparison | Same as C; Deterministic path | One selected interpretation with forced weight one; not certainty |
| E: old representation | Same as C; Averaged keys | Fixed-key mixture and legacy key-hypothesis evidence |
| F: budget tradeoff | Same as C; compare budgets 4 and 16 on the same passage | More retained model mass and narrower omitted-score interval |
| G: hard structural filter | Same query; switch exact ending to start | Returned event positions must obey the new requirement; zero results is possible |
| H: approximate alignment | Fuzzy functional; `ii7 V7 Imaj7`; any section/position; budget 4 | Inspect substitutions/insertion/deletion and nearby window lengths; not all edits guaranteed |
| I: conditional functions | Open a song and click G | G's role changes with assumed key; conditional weight differs from key probability |
| J: review/evaluation plumbing | Clearly labelled practice benchmark; pilot; source song and family; pool; reviewer profiles | Show independent grading, unresolved handling, review packet and comparison; do not call practice labels expert truth |

Live case C returned **I Want to Go Home — Johnny Cash**, `G7 C`, chorus_1,
events 16–17. At check time the candidate ceiling of 500 was reached. Hard-path
results included **Give Me More, More, More (Of Your Kisses) — Lefty Frizzell**;
legacy results included **Whatta Man — Salt-N-Pepa**. These are observed examples,
not guaranteed permanent ranks or evidence that one method is better.

The Johnny Cash passage gave:

| Budget | Retained joint paths | Raw score | Retained mass | Omitted mass | Full expected-score bounds |
|---|---:|---:|---:|---:|---|
| 4 | 6 | 0.999500616 | 99.9565% | 0.0435% | [0.999500616, 0.999935565] |
| 16 | 22 | 0.999695729 | 99.9827% | 0.0173% | [0.999695729, 0.999868249] |

The old interface rounded both scores to 1.000 and both masses to 100%. The
revised cards show 0.999501 versus 0.999696, and the evidence shows precise mass. This is a clear computational
example with little ambiguity, not a strong uncertainty-benefit example.

Interactive model switching can also change candidate generation, capped pools,
and tie ordering; the growing catalog can change between searches. Use the
Research pilot's shared-pool comparison for a controlled ranking experiment.

For the presentation, say: “The software retrieves and explains passages under
alternative tonal interpretations. This demonstrates the implemented mechanism.
Independent judgments and stronger comparisons are still needed to establish
whether the mechanism improves musical relevance.”

## Simplified interface revision

The search hero, presets, record shelf, decorative chapter numbers, fake account
row and duplicate status text have been removed. Search mode and model controls
appear only where effective. Search details show elapsed seconds and candidate
starts; capped-search warnings remain visible. Detailed paths, score contributions
and raw provenance are expandable. Deterministic controls do not display forced
point-mass weight as posterior coverage. Result details preserve their analysis ID.

Data & jobs prioritizes running/queued work and failures. Completed history,
imports, analysis versions and fixtures are expandable. Legacy experiments and
optimization remain under “Legacy experiments and tuning”. Comparisons default
to the selected benchmark's source songs; custom IDs are an optional scope setting.
The removed legacy pattern selector is still available through the backend/CLI.
