"""Optimization checks against the original exhaustive prefix-sort implementation."""
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.special import logsumexp
from sqlalchemy import event, select

from harmonygraph import paths
from harmonygraph.contracts import AnalysisConfig, SearchRequest
from harmonygraph.music import infer_keys, interpret, parse_chord
from harmonygraph.retrieval import search


def reference_keys(messages, start, end, budget):
    posterior, _, emissions, transitions, beta = messages
    beam = sorted([((k,), float(posterior[start, k])) for k in range(24)],
                  key=lambda item: (-item[1], item[0]))[:budget]
    for t in range(start + 1, end + 1):
        logp = transitions[t - 1] + emissions[t][None, :] + beta[t][None, :]
        conditional = np.exp(logp - logsumexp(logp, axis=1)[:, None])
        expanded = [(prefix + (k,), p * float(conditional[prefix[-1], k]))
                    for prefix, p in beam for k in range(24)]
        beam = sorted(expanded, key=lambda item: (-item[1], item[0]))[:budget]
    return beam


def reference_joint(chords, messages, start, end, key_budget=64, function_budget=16, hard=False):
    keys = reference_keys(messages, start, end, key_budget)
    if hard:
        keys = [(tuple(messages[1][start:end + 1]), 1.0)]
    retained = []
    for key_sequence, probability in keys:
        beam = [((), 1.0)]
        for offset, key in enumerate(key_sequence):
            t = start + offset
            options = interpret(chords[t], key, chords[t + 1] if t + 1 < len(chords) else None)
            if hard:
                options = [{**options[0], "weight": 1.0}]
            beam = sorted([(seq + (op["roman"],), w * op["weight"])
                           for seq, w in beam for op in options], key=lambda item: (-item[1], item[0]))[:function_budget]
        retained.extend({"keys": list(key_sequence), "functions": list(seq), "probability": probability * w}
                        for seq, w in beam)
    return sorted(retained, key=lambda p: (-p["probability"], p["keys"], p["functions"]))


def test_prefix_selection_preserves_exact_probabilities_and_ties():
    chords = [parse_chord(c) for c in "N C D7 G Am E7 Am".split()]
    messages = infer_keys(chords, [0] * 7, [1] * 7, AnalysisConfig(), return_messages=True)
    prepared = paths.PreparedContext(messages)
    for budget in (1, 4, 16, 64, 576):
        for start, end in ((0, 1), (1, 3), (5, 6)):
            assert paths.key_paths(prepared, start, end, budget) == reference_keys(messages, start, end, budget)
            assert paths.joint_paths(chords, prepared, start, end, budget) == reference_joint(
                chords, messages, start, end, budget)
    # Uniform evidence forces probability ties, including a beam cutoff tie.
    silent = infer_keys([parse_chord("N")] * 3, [0] * 3, [1] * 3, AnalysisConfig(), return_messages=True)
    assert paths.key_paths(paths.PreparedContext(silent), 0, 2, 16) == reference_keys(silent, 0, 2, 16)


def test_context_reuse_invalidation_and_memory_bound(monkeypatch):
    monkeypatch.setattr(paths, "_contexts", paths.OrderedDict())
    monkeypatch.setattr(paths, "_context_bytes", 0)
    chords = [parse_chord(c) for c in "C G7 C".split()]
    events = [SimpleNamespace(section_id=0, duration=1) for _ in chords]
    config = AnalysisConfig()
    first = paths.context_messages(chords, events, config)
    assert paths.context_messages(chords, events, config) is first
    # Query/alignment settings do not affect query-independent HMM messages.
    assert paths.context_messages(chords, events, config.model_copy(update={"substitution": 0.2})) is first
    for changes in ({"window": 4}, {"change_penalty": 0.5}, {"local_keys": False}):
        assert paths.context_messages(chords, events, config.model_copy(update=changes)) is not first
    events[0].duration = 2
    assert paths.context_messages(chords, events, config) is not first
    events[0].duration = 1
    events[1].section_id = 1
    assert paths.context_messages(chords, events, config) is not first
    events[1].section_id = 0
    chords[0] = parse_chord("Am")
    assert paths.context_messages(chords, events, config) is not first
    with pytest.raises(ValueError):
        first[0][0, 0] = 1
    with pytest.raises(ValueError):
        first.conditional(1)[0, 0] = 1
    monkeypatch.setattr(paths, "_CONTEXT_BYTES", len(chords) * 8192)
    paths.context_messages(chords, events, config.model_copy(update={"window": 10}))
    assert len(paths._contexts) == 1
    assert paths._context_bytes <= paths._CONTEXT_BYTES
    monkeypatch.setattr(paths, "_CONTEXT_BYTES", 1)
    assert paths.context_messages(chords, events, config) is not paths.context_messages(chords, events, config)


@pytest.mark.parametrize("ranking,mode", [("path_expectation", "functional"), ("path_expectation", "fuzzy"),
                                         ("hard_path", "functional"), ("equal_paths", "functional"),
                                         ("shuffled_paths", "functional"), ("max_path", "functional")])
def test_complete_search_payload_matches_original(session, corpus, monkeypatch, ranking, mode):
    request = SearchRequest(progression="V7 I", ranking=ranking, mode=mode, path_budget=4)
    optimized = search(session, request).model_dump(exclude={"timings"})
    monkeypatch.setattr(paths, "joint_paths", reference_joint)
    monkeypatch.setattr(paths, "context_messages", lambda chords, events, config: infer_keys(
        chords, [e.section_id for e in events], [e.duration for e in events], config, return_messages=True))
    original = search(session, request).model_dump(exclude={"timings"})
    assert optimized == original


def test_path_projection_skips_legacy_table_and_cannot_poison_legacy_cache(session, corpus):
    from harmonygraph.db import Song
    from harmonygraph.retrieval import load_evidence_batch

    ids = list(session.scalars(select(Song.id)))
    statements = []

    def capture(conn, cursor, statement, params, context, many):
        statements.append(statement)

    event.listen(session.get_bind(), "before_cursor_execute", capture)
    try:
        lean = load_evidence_batch(session, ids, corpus[1], include_interpretations=False)
        assert len(statements) == 6
        assert not any("functional_interpretations" in statement.lower() for statement in statements)
        assert not any(evidence[5] for evidence in lean.values())
        complete = load_evidence_batch(session, ids, corpus[1])
        assert all(evidence[5] for evidence in complete.values())
        assert lean[ids[0]][0].id == complete[ids[0]][0].id
    finally:
        event.remove(session.get_bind(), "before_cursor_execute", capture)
    shared = {}
    search(session, SearchRequest(progression="V7 I", ranking="path_expectation", path_budget=4),
           evidence_context=shared)
    legacy = SearchRequest(progression="V7 I", ranking="legacy_mixture")
    assert search(session, legacy, evidence_context=shared).results == search(session, legacy).results
