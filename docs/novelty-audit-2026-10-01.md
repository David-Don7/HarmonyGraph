# HarmonyGraph: novelty audit and research decision

Review date: 1 October 2026. Input: the supplied 27-section HarmonyGraph statement. This is a research-planning assessment, not an experimental result or a guarantee of publication.

## Decision

Keep the project, but narrow and revise the novelty claim. Functional harmonic search, theory-informed chord alignment, probabilistic key inference, multiple weighted hypotheses for music retrieval, and harmonic knowledge graphs all have substantial precedents. Their combination is useful engineering, but does not by itself establish a strong research contribution.

The strongest direction identified in this review is **context-sensitive passage retrieval that preserves coherent local-key paths and quantifies the consequences of approximation**, evaluated on an independently annotated benchmark designed to distinguish genuine ambiguity from analysis errors. Use section constraints and auditable explanations to make that method useful in the application.

I did not identify a work in the reviewed sources that evaluates this exact combination of task, path-level uncertainty, context-controlled benchmark, and approximation audit. That is a scoped search finding, not proof that no such work exists. The revised project is a defensible research proposal; its eventual paper value depends on the experiments.

Read [the revised proposal](research-proposal-v2.md) for the replacement problem statement, method, experiment gates, and application plan.

## Search coverage and limitations

Discovery used web searches with academic titles and topic combinations, followed by publisher, proceedings, author, institutional, and dataset pages. Sources actually consulted included ISMIR proceedings, a JCDL author manuscript, an IEEE ISM manuscript and NJIT bibliographic record, Scientific Data, Journal of Web Semantics, Springer/VLDB, ACL Anthology, arXiv, Utrecht/Oxford/Harvard repositories, Waterloo research pages, Fraunhofer, DDMAL, Isophonics, and the Chordonomicon maintainers' repository and dataset card. DBLP records helped check bibliographic identity; they do not substitute for technical evidence.

A direct Google Scholar query for chord-sequence retrieval failed to load. A Scholar-domain discovery query did not provide useful accessible results. Therefore this report does **not** claim a completed Google Scholar search. There was no authenticated search of Scopus, Web of Science, IEEE Xplore, or the entire ACM Digital Library. IEEE/ACM work was verified through accessible manuscripts and institutional records where available. Not all cited papers were read end to end: the evidence level is identified below. Abstract-level absence of a feature must not be interpreted as proof that the full paper lacks it.

No finite search can cover all verified research on the internet. Unindexed work, other languages, inaccessible texts, and new releases remain possible. Search-result crawl dates were not treated as publication dates. The 2026 items below were checked against their actual repository or proceedings records.

### Query log

The following are representative actual queries from this review, grouped by purpose. Broad searches produced many irrelevant signal-processing results because “harmonic retrieval” also describes sinusoid estimation.

| Search purpose | Queries issued |
|---|---|
| Initial landscape | `music harmonic progression retrieval probabilistic key uncertainty chord sequence search`; `Chordonomicon dataset harmony retrieval sections paper`; `harmonic similarity retrieval Roman numeral local key sequence alignment` |
| Closest retrieval methods | `"chord progression retrieval"`; `"chord" "retrieval" "probabilistic" ISMIR`; `"harmonic" "retrieval" "alignment" chord progression` |
| Functional and structural analysis | `HarmTrace harmony retrieval similarity de Haas 2013 structure`; `"HarmTrace: Improving Harmonic Similarity" ismir2011`; `"functional harmony" "ontology" Polifonia` |
| Uncertainty and counterexamples | `"harmonic" "retrieval" "posterior"`; `"chord" "retrieval" "lattice"`; `"chord" "retrieval" "calibration"`; `"functional harmony" "retrieval" "uncertainty"` |
| Recent work | `"chord retrieval" "2025"`; `"chord progression retrieval" "2026"`; `site:dl.acm.org "chord" "retrieval" 2025 2026` |
| Database contribution | `"probabilistic" "top-k" "database" Soliman Ilyas Chang 2007`; `"Top-k query processing in uncertain databases" site:cs.uwaterloo.ca` |
| Data suitability | `McGill Billboard Project chord analysis dataset tonic key structure annotations`; official Chordonomicon and Isophonics pages |

Backward reference checking in Hanna et al. and HarmTrace connected alignment, tonal-pitch distance, grammar models, and earlier retrieval work. This was a targeted review, not a systematic review with exhaustive screening counts or complete forward-citation coverage.

## Closest prior work and what it changes

These entries distinguish verified positive overlap from the proposed differentiation. A different dataset size or a new web interface alone does not resolve overlap.

| Work and evidence inspected | Established overlap | Consequence for HarmonyGraph |
|---|---|---|
| Noland & Sandler, **Key Estimation Using a Hidden Markov Model**, ISMIR 2006. [Proceedings PDF](https://archives.ismir.net/ismir2006/paper/000091.pdf), abstract/method opening. | A 24-state major/minor HMM with chord-transition observations and time-dependent key likelihoods. | A 24-key HMM and local key uncertainty are established components. |
| Hanna, Robine & Rocher, **An Alignment Based System for Chord Sequence Retrieval**, JCDL 2009. [Author manuscript](https://www.labri.fr/perso/mrobine/papers/robine-HRR.JCDL09.pdf), methods and results. | Approximate chord alignment; musical substitution costs; insertion/deletion; multiple local transpositions. | Mandatory strong baseline. “Existing search only matches strings or a global key” is contradicted. Distinguish local transposition from inferred tonal function. |
| De Haas et al., **Modeling Harmonic Similarity Using a Generative Grammar of Tonal Harmony**, ISMIR 2009. [Proceedings PDF](https://ismir2009.ismir.net/proceedings/OS7-2.pdf), abstract and opening. | Functional parse trees and structural harmonic similarity used in retrieval. | Structural harmonic reasoning is not new. Song-section labels are a different kind of structure, which must be stated explicitly. |
| De Haas et al., **HarmTrace: Improving Harmonic Similarity Estimation Using Functional Harmony Analysis**, ISMIR 2011. [Proceedings PDF](https://ismir2011.ismir.net/papers/PS1-5.pdf), abstract and Sections 2–3. | Functional annotations improve local-alignment similarity; evaluation on 5,028 chord sequences. The implemented grammar differs from the richer phrasing/modulation grammar discussed as background. | The most direct challenge to the original central claim. Compare a faithful implementation or clearly labelled adaptation; do not describe all prior functional systems as global Roman-numeral string matching. |
| Yu et al., **Recognition and Summarization of Chord Progressions and Their Application to Music Information Retrieval**, IEEE ISM 2012. [Manuscript](https://smcnus.org/wp-content/uploads/2013/09/chord-progression.pdf), abstract/introduction; [NJIT record](https://digitalcommons.njit.edu/fac_pubs/17954/). DOI: 10.1109/ISM.2012.10. | Locally probed n-best chord progressions, likelihood-weighted summaries, and retrieval over more than 70,000 audio tracks. | Do not claim first uncertainty-aware chord retrieval or first weighted-alternative retrieval. Proposed distinction: uncertainty about symbolic functional/key paths and passage-level query semantics, rather than audio-recognition hypotheses summarized into track histograms. |
| De Haas, Wiering & Veltkamp, **A geometrical distance measure for determining the similarity of musical harmony**, 2013. [Utrecht record](https://research-portal.uu.nl/en/publications/a-geometrical-distance-measure-for-determining-the-similarity-of--2); earlier [2008 proceedings](https://archives.ismir.net/ismir2008/2008_ISMIR_Proceedings.pdf). | Tonal Pitch Step Distance is an established harmonic retrieval approach. | Include a tonal-distance comparator if feasible. Do not equate uniform edit distance with the strongest prior music similarity. |
| Dylan Freedman, **Correlational Harmonic Metrics: Bridging Computational and Human Notions of Musical Harmony**, Harvard senior thesis, 2015. [Institutional record](https://dash.harvard.edu/entities/publication/73120378-eb2d-6bd4-e053-0100007fdf3b), indexed repository abstract; direct page/PDF loading failed. | Optimization of chord distances, gap costs, and normalization for harmonic comparisons and n-gram queries. | Supporting prior art against tuning novelty. This is a thesis, not a verified peer-reviewed conference/journal paper; full technical comparison remains limited. |
| Bittner et al., **A Novel Dataset for Time-Dependent Harmonic Similarity between Chord Sequences**, ISMIR 2021. [Fraunhofer record](https://publica.fraunhofer.de/entities/publication/ddafdb48-feb3-4d47-947d-532d50ba7d37), abstract; [dataset](https://www.idmt.fraunhofer.de/en/publications/datasets/chord-sequences.html). | Synthetic chord-sequence triplets and learned temporal similarity embeddings. | A harmonic similarity benchmark is not new in general. Distinguish expert-reviewed, natural-context, ambiguity-sensitive passage judgments from synthetic triplets. |
| Kantarelis et al., **Functional harmony ontology: Musical harmony analysis with Description Logics**, Journal of Web Semantics 75, 2023, article 100754. [Publisher page](https://www.sciencedirect.com/science/article/pii/S1570826822000385), abstract/introduction and section summaries. | OWL 2 RL functional-harmony reasoning and comparison with HarmTrace. | Functional inference, explicit theory rules, and semantic representation are established. An explanation panel alone is insufficient novelty. |
| **ChoCo: a Chord Corpus and a Data Transformation Workflow for Musical Harmony Knowledge Graphs**, Scientific Data, 2023. [Paper](https://www.nature.com/articles/s41597-023-02410-w), abstract and dataset description. | Integrated chord annotations, transformation workflow, ontology, and a large harmony knowledge graph. | Neither storing harmonic relations nor aggregating chord corpora is a new contribution by itself. Check source overlap before cross-corpus testing. |
| Kantarelis et al., **CHORDONOMICON**, 2024. [Paper record](https://arxiv.org/abs/2410.22046); [maintainer repository](https://github.com/spyroskantarelis/chordonomicon); [dataset card](https://huggingface.co/datasets/ailsntua/Chordonomicon). | Large chord-chart collection with structural parts and metadata. | Input resource, not evidence of accurate functions, local-key labels, or retrieval relevance. The paper count and later release count need not coincide. |
| Sim, Moranis & Devaney, **BeatlesFC: Harmonic function annotations of Isophonics' The Beatles dataset**. [arXiv record](https://arxiv.org/abs/2601.02099), abstract and publication comment. | Phrase-level tonic/predominant/dominant labels relating harmony to formal structure. | Useful potential reference data, subject to annotation and release audit. Record identifies ISMIR Late-Breaking Demo 2024 and arXiv posting in January 2026; these are distinct dates/statuses. |
| Anand et al., **FIGMA: Towards FIne-Grained Music retrievAl**, ACL 2026. [Proceedings record](https://aclanthology.org/2026.acl-long.2197/), abstract and metadata. | Audio-text retrieval with detailed attributes including key and chord progression. | Recent adjacent work; do not claim all current systems lack fine-grained musical queries. Its modality/task differs from symbolic function-constrained passage search. |
| Nercessian et al., **Perceptually Motivated Alignment and Interpolation of Pitch-Aligned Time-Frequency Representations**, September 2026. [arXiv record](https://arxiv.org/abs/2609.31971), abstract; record reports acceptance to DAFx26. | Perceptually weighted alignment without explicit key detection. | Include key-free matching in the comparison; key inference is not automatically beneficial. Full algorithmic comparison was not performed here. |
| Soliman, Ilyas & Chang, **Top-k Query Processing in Uncertain Databases**, ICDE 2007; subsequent **Probabilistic Top-k and Ranking-Aggregate Queries**, TODS 2008. [Author manuscript](https://cs.uwaterloo.ca/~ilyas/papers/SolimanICDE2007.pdf); [Waterloo record](https://cs.uwaterloo.ca/research/technical-reports/2006-technical-reports); [journal manuscript](https://cs.uwaterloo.ca/~ilyas/papers/Tods2008.pdf). Record/abstract-level review. | Possible-world semantics and ranking under uncertainty are established database topics. | Expected similarity, probability of matching, and probability of occupying a rank are different semantics. Do not claim a new general probabilistic database method. |

## Refinement history

1. **Original:** combine probabilistic analysis, sections, fuzzy matching, explanations, and automatic tuning. Rejected as a sufficient novelty argument because of the overlaps above.
2. **First narrowing:** preserve several harmonic interpretations during retrieval. Still insufficient: Yu et al. already retain and weight multiple chord hypotheses for retrieval, and probabilistic key inference predates this project.
3. **Recommended framing:** measure the retrieval value of coherent, context-conditioned key/function paths, with mass-preserving approximation and a benchmark that separates same-chords/different-context cases. This makes the uncertainty semantics and the scientific test explicit. The application is the experimental vehicle.

This is where refinement should stop before collecting evidence. Adding more features until a title sounds unique would weaken feasibility and make the source of any improvement harder to identify.

## Corrections to the supplied statement

| Original implication | Replacement |
|---|---|
| Existing systems largely cannot search higher-level harmonic meaning. | Established systems already search harmonic function and use theory-informed alignment. The open question here concerns ambiguity-sensitive passage retrieval and its measured reliability. |
| Top-k local keys solve within-passage modulation. | Multiple constant-key interpretations do not represent a changing key path. Evaluate coherent paths separately. |
| A normalized compatibility score is a confidence probability. | State the probabilistic model and evaluate calibration; use “model weight” for unsupported heuristic weights. |
| A single key per passage plus independent chord functions captures all uncertainty. | A passage can have correlated key/function interpretations across events. Separate ambiguity, chart noise, model misspecification, and approximation loss. |
| More retained hypotheses should improve retrieval. | They can improve recall, dilute relevant scores, or introduce spurious matches. This is a falsifiable hypothesis. |
| Adding chorus/end features proves structural understanding. | Explicit user constraints may be satisfied by a simple SQL filter. Give every applicable baseline those same filters. |
| Every chord function or cadence candidate can be resolved from chord labels. | Roman numeral, tonal function, and cadence are distinct claims. Preserve unresolved cases and limit conclusions to the information available. |
| Recall over pooled judgments is corpus-wide recall. | It is recall relative to the judged pool. Report pool coverage and audit candidate generation separately. |
| A positive comparison with literal/global-key baselines is enough. | Include HarmTrace-style functional alignment, local-transposition alignment, and a reasonable sequence-embedding comparator. |
| HPO improvement is a principal research hypothesis. | Use balanced tuning as methodology. Remove HPO from the title and primary hypotheses. |

## Data decisions

Chordonomicon is suitable for scale and naturally occurring chord charts. Its displayed schema contains section-marked chord strings and metadata, not complete local-key, function, duration, or relevance ground truth. The current dataset card declares CC-BY-NC-4.0, whereas the code repository displays Apache-2.0; do not substitute the code license for the dataset terms. Pin the release, preserve attribution and source records, and verify the exact deployment/distribution terms before publication. [Dataset card](https://huggingface.co/datasets/ailsntua/Chordonomicon), [repository](https://github.com/spyroskantarelis/chordonomicon).

McGill Billboard's complete annotations contain chords, structure, timing, opening tonic and possible subsequent tonic changes, including unresolved tonic markers. They do not automatically provide the full 24-class key posterior targets or passage relevance judgments needed here. Its official release documentation distinguishes chart slots from distinct songs. Use complete annotations rather than a chord-only export when evaluating structural context. [DDMAL documentation](https://ddmal.ca/research/The_McGill_Billboard_Project_%28Chord_Analysis_Dataset%29/).

Isophonics documents inconsistent structural labels and potentially omitted key changes, especially for the Beatles. Consequently, absence of an annotated change is not reliable evidence that no modulation occurred. Audit a bounded subset before reporting key-boundary recall. [Isophonics documentation](https://isophonics.net/content/reference-annotations).

BeatlesFC offers a relevant function-annotation lead, but its categories and phrase-level scope must be aligned with the chosen task. It cannot replace newly collected passage-relevance judgments. [BeatlesFC](https://arxiv.org/abs/2601.02099).

## Existing application: evidence and research gap

The workspace already contains a substantial application. README and project reports describe ingestion, indexed search, a research studio, benchmark annotation, and experiments. This review inspected documentation and selected retrieval code; it did not rerun the application or independently reproduce earlier runtime/import reports.

In `harmonygraph/retrieval.py`, `passage_readings` averages per-event key marginals across the passage, selects keys, and builds function beams under each selected fixed key. This is a useful baseline, but an average of event marginals is not the posterior probability that the whole passage uses that key. It also discards the ordering of a modulation trajectory. The revised path model is therefore a substantive proposed extension, not a capability already demonstrated.

The current implementation exposes retained key/interpretation mass and warns that calibration is unestablished. Preserve those distinctions. A best alignment explanation must not be presented as if it explained the complete expected score across all alternatives.

Existing synthetic software fixtures and catalog import/performance reports are not expert retrieval evidence. The paper scaffold correctly leaves real-corpus relevance and human explanation results pending. The research roadmap should concentrate on those gaps and stronger comparisons, rather than rebuilding the user interface.

## Research readiness

The topic is suitable for a serious music-information-retrieval research project if annotation access and evaluation time are available. A general database research claim needs an additional demonstrated contribution in query semantics, indexing, or execution—not merely PostgreSQL tables. Neither topic suitability nor novelty checking guarantees venue acceptance.

Proceed with the bounded pilot in the revised proposal. Freeze claims after reviewing the pilot and before final testing. If coherent paths show little benefit, report that result and its conditions; do not repeatedly redesign on the held-out test set until something wins.
