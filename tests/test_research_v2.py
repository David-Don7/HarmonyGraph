from itertools import product
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.special import logsumexp
from sqlalchemy import select

from harmonygraph.contracts import AnalysisConfig, JudgmentInput, SearchRequest
from harmonygraph.db import Song, Benchmark, BenchmarkQuery, Annotator, RelevanceJudgment
from harmonygraph.music import infer_keys, parse_chord
from harmonygraph.paths import joint_paths, key_paths, score_paths
from harmonygraph.research_v2 import blinded_pool, clustered_comparison, labels, bounded_audit
from harmonygraph.retrieval import search


def test_joint_key_probabilities_equal_exact_enumeration_with_outside_context():
    chords = [parse_chord(c) for c in ["C", "D7", "G"]]
    messages = infer_keys(chords, [0, 0, 1], [1] * 3, AnalysisConfig(), return_messages=True)
    _, _, emission, transitions, _ = messages
    logs = {
        path: -np.log(24)
        + sum(emission[i, k] for i, k in enumerate(path))
        + sum(transitions[i][path[i], path[i + 1]] for i in range(2))
        for path in product(range(24), repeat=3)
    }
    normalizer = logsumexp(list(logs.values()))
    marginal = {}
    for path, weight in logs.items():
        marginal[path[1:]] = marginal.get(path[1:], 0) + np.exp(weight - normalizer)
    retained = dict(key_paths(messages, 1, 2, 576))
    assert sum(retained.values()) == pytest.approx(1)
    assert retained == pytest.approx(marginal)
    assert any(path[0] != path[1] and p > 0 for path, p in retained.items())


def test_exact_joint_function_mass_bounds_and_score_reconstruction():
    chords = [parse_chord(c) for c in ["D7", "G"]]
    cfg = AnalysisConfig()
    messages = infer_keys(chords, [0, 0], [1, 1], cfg, return_messages=True)
    exact = joint_paths(chords, messages, 0, 1, 576, 16)
    assert sum(p["probability"] for p in exact) == pytest.approx(1)
    assert len({(tuple(p["keys"]), tuple(p["functions"])) for p in exact}) == len(exact)
    oracle = score_paths(["V7", "I"], exact, cfg)
    for budget in [1, 4, 24, 100]:
        pruned = joint_paths(chords, messages, 0, 1, budget, 1)
        score = score_paths(["V7", "I"], pruned, cfg)
        lo, hi = score["expected_similarity_bounds"]
        assert lo - 1e-12 <= oracle["score"] <= hi + 1e-12
        assert score["score"] == pytest.approx(sum(p["contribution"] for p in score["paths"]))
        assert score["omitted_mass"] == pytest.approx(1 - sum(p["probability"] for p in pruned))
        for path in pruned:
            original = next(p for p in exact if p["keys"] == path["keys"] and p["functions"] == path["functions"])
            assert path["probability"] == pytest.approx(original["probability"])


def test_research_query_validation():
    for query in ["I", "I " * 9, "C G"]:
        with pytest.raises(ValueError):
            SearchRequest(progression=query, ranking="path_expectation")
    with pytest.raises(ValueError):
        JudgmentInput(query_id="q", passage_id="p", annotator_id="a", status="unresolved", relevance=0)
    assert JudgmentInput(query_id="q", passage_id="p", annotator_id="a", status="unresolved").relevance is None


def test_paths_search_constraints_and_evidence(session, corpus):
    request = SearchRequest(
        progression="V7 I", ranking="path_expectation", section="chorus", boundary="end", path_budget=4
    )
    results = search(session, request).results
    assert results
    for result in results:
        assert result.evidence["position"]["from_end"] == 0
        assert result.score == pytest.approx(sum(c["contribution"] for c in result.components.values()))
        evidence = result.evidence["paths"]
        assert evidence["semantics"] == "path_expectation"
        assert evidence["expected_similarity_bounds"][0] == pytest.approx(result.score)
        assert len(evidence["paths"][0]["keys"]) == 2
        assert len(result.evidence["context_labels"]) == 20
        assert "candidate" in evidence["certificate_scope"]


def test_blinding_and_clustered_uncertainty():
    query = SimpleNamespace(
        id="q",
        request={"progression": "ii V I"},
        protocol={},
        pool=[
            {
                "passage_id": "s:0:2",
                "score": 0.9,
                "rank": 1,
                "explanation": "secret",
                "evidence": {"pooling_modes": ["proposed"], "context_labels": ["C", "G"]},
            }
        ],
    )
    blind = blinded_pool(query)
    assert not {"score", "explanation", "rank", "evidence"} & blind["candidates"][0].keys()
    assert blind["candidates"][0]["context"] == ["C", "G"]
    report = clustered_comparison([1, 1, 0, 0], [0, 0, 0, 0], ["a", "a", "b", "b"])
    assert report["clusters"] == 2
    assert report["mean"] == 0.5
    assert report == clustered_comparison([1, 1, 0, 0], [0, 0, 0, 0], ["a", "a", "b", "b"])


def test_unresolved_adjudication_never_becomes_negative(session):
    b = Benchmark(name="test")
    a = Annotator(name="reviewer", qualifications="test fixture")
    session.add_all([b, a])
    session.flush()
    q = BenchmarkQuery(benchmark_id=b.id, request={"progression": "V I"}, pool=[])
    session.add(q)
    session.flush()
    session.add(
        RelevanceJudgment(
            query_id=q.id,
            passage_id="p",
            annotator_id=a.id,
            relevance=None,
            adjudicated=True,
            ratings={"status": "unresolved"},
        )
    )
    session.commit()
    assert labels(session, q) == {}


def test_bounded_packet_never_labels_model_output_as_human_truth(session, corpus):
    ids = list(session.scalars(select(Song.id).order_by(Song.id).limit(6)))
    audit, packet = bounded_audit(session, ids, example_count=6, budgets=(1, 2))
    assert len(packet["examples"]) == 6
    assert audit["human_relevance"] is None
    assert packet["independent_review"] == "pending"
    assert all(e["rating"]["relevance"] is None for e in packet["examples"])
    assert all("score" not in e for e in packet["examples"])


def test_frozen_context_and_family_leakage(session, corpus):
    from harmonygraph.research_v2 import freeze_context, validate_protocols

    song = session.scalar(select(Song))
    protocol = freeze_context(session, song.id, {"family": "same-example", "split": "pilot"})
    assert len(protocol["context"]["labels"]) == 20
    validate_protocols([SimpleNamespace(protocol=protocol)])
    with pytest.raises(ValueError, match="leakage"):
        validate_protocols(
            [SimpleNamespace(protocol=protocol), SimpleNamespace(protocol={**protocol, "split": "test"})]
        )
    with pytest.raises(ValueError, match="hash"):
        validate_protocols([SimpleNamespace(protocol={**protocol, "context_hash": "changed"})])


def test_tonic_only_reference_does_not_invent_mode(session, corpus):
    from harmonygraph.db import SourceAnnotation
    from harmonygraph.validation import harmonic_evaluation

    song = session.scalar(select(Song))
    source = session.scalar(select(SourceAnnotation).where(SourceAnnotation.song_id == song.id))
    source.data = {"annotations": {"event_tonics": {"0": "C", "1": "?"}}}
    session.commit()
    report = harmonic_evaluation(session, corpus[1], [song.id], 3)
    assert report["tonic_uncertainty"]["available"]
    assert not report["uncertainty"]["available"]


def test_controlled_runner_shared_pool_and_heldout_guard(session, corpus):
    from harmonygraph.research_v2 import controlled_run, freeze_context

    song = session.scalar(select(Song).where(Song.source_id == "0"))
    benchmark = Benchmark(name="V2 development")
    session.add(benchmark)
    session.flush()
    query = BenchmarkQuery(
        benchmark_id=benchmark.id,
        source_song_id=song.id,
        category="clear-control",
        request={"progression": "V7 I", "section": "chorus", "boundary": "end"},
        protocol=freeze_context(
            session, song.id, {"split": "pilot", "family": "example-1", "subtype": "clear-control"}
        ),
    )
    session.add(query)
    session.commit()
    report = controlled_run(session, benchmark.id, [song.id], path_budget=2)
    assert len(report["methods"]) == 7
    for rows in report["methods"].values():
        assert rows[0]["metrics"]["ndcg@10"] is None
        assert all(p.endswith((":12:13", ":18:19")) for p in rows[0]["passages"])
    query.protocol = {**query.protocol, "split": "test"}
    session.commit()
    with pytest.raises(ValueError, match="held-out"):
        controlled_run(session, benchmark.id, [song.id], path_budget=2)
