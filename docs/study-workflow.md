# Preparing a HarmonyGraph research study

The software supports a bounded development comparison and independent annotation.
It does not establish that context paths improve human relevance. The governing
method and study gates remain in [the proposal](research-proposal-v2.md).

## Feasibility before the main study

Start with a 6–10-example chord-only packet. Record reviewer qualifications,
minutes spent, rubric problems, insufficient-context cases and disagreements.
The included old packet is ungraded; a fresh packet can be produced from explicit
analyzed songs with `harmonygraph research-v2-audit --song-id ID ... --examples 8`.
The source-order sections and model-suggested readings are not an independently
classified ambiguity benchmark. No reviewer is recruited or contacted by this app.

## Studio workflow

1. Open `/studio` → **Benchmark lab** and create a benchmark. Mark constructed
   examples as synthetic, including browser/software checks.
2. Add each query with 2–8 Roman numerals and **Context paths · research v2**.
   Select a real source song (the input suggests named analyzed songs), record its
   family and reviewed subtype, and choose pilot/train/validation. The complete
   chord context is snapshotted and hashed. Editing a query creates a new revision.
3. Build its candidate pool. Current pooling combines multiple retrieval modes;
   random/adversarial candidates, overlap deduplication and strong prior-work
   comparators still require the main-study protocol described below.
4. In **Experiments → Context-path comparison**, select the benchmark and inspect its
   protocol issues and annotation coverage. Download the blinded packet. It omits
   scores, model rankings, synthetic ground truth and other reviewers' answers.
5. Reviewers work independently on the same material. Each packet has blank
   response fields. Complete `responses` with relevance 0/1/2 and `status: judged`,
   or leave relevance null and set an unresolved/insufficient-context status.
   Record `reviewer.minutes`. Create the reviewer's profile and qualifications
   in Benchmark lab, then import the packet under that profile in Experiments.
   The packet's material hash must still match. Invalid batches are rejected
   atomically; earlier submissions remain in history. Reimporting adds history.
6. In Benchmark lab, enable review mode to inspect disagreements. Select source
   judgments from at least two different reviewers when saving an adjudication.
   Missing or unresolved labels remain ungraded. Qualifications are self-reported;
   the readiness report cannot verify expertise or actual independence.
7. Select 1–50 explicit development song IDs in Experiments, or use the source
   songs. Start with path budget 4. Queue the comparison. It evaluates seven
   controls on a common candidate-start pool and pins the ready analysis and
   benchmark/label hash at submission. A changed benchmark requires a new run.
8. Inspect progress and download the completed JSON report. Its manifest records
   corpus hashes, configuration, candidate starts, method settings and label policy.
   Query-level nDCG@10 is unavailable if returned top-ten passages lack resolved
   chord-only judgments. Scores with complete judged top tens are still relative
   to available ground truth, not proof of corpus-wide relevance recall.

Packet imports record independent responses only. Adjudicate separately. Reviewer
packets are data artifacts; the application does not infer human answers from
model scores. Explanation ratings should be collected separately from blinded
relevance judgments, with a controlled presentation protocol.

## Main-study requirements still pending

- Obtain qualified independent review and classify natural contextual examples
  before viewing comparative successes. Use the feasibility trial to decide
  whether a 24–30-query pilot is practical.
- Implement and validate the strong Hanna/HarmTrace and learned comparators,
  expected-local-cost alignment and global-key control listed in the proposal.
- Audit artist, cover, passage, transposition-template and cross-corpus leakage.
  The existing group fields catch declared overlap; they do not discover it.
- Build deduplicated cross-method pools with random and adversarial negatives.
  Measure judgment coverage and annotation burden across the planned strata.
- Freeze corpus, rubric, exclusions, candidates, tuning budget and statistical
  comparisons before held-out testing. V2 deliberately rejects test queries.
- Measure end-to-end latency, memory, context sensitivity and approximation tradeoffs
  on the chosen corpus. Small computational checks do not validate musical claims.

The older experiment/HPO panel remains available below Research pilot and is
explicitly labelled legacy. Its “proposed” configuration is not the v2 method.
No completed publication or research superiority is claimed by this workflow.
