import math
import pytest
from sqlalchemy import select
from harmonygraph.contracts import SearchRequest
from harmonygraph.db import Benchmark, BenchmarkQuery, Song
from harmonygraph.metrics import (
    agreement,
    bootstrap,
    boundary_metrics,
    paired_comparison,
    retrieval_metrics,
    uncertainty_metrics,
)
from harmonygraph.research import evaluate, freeze, grouped_splits, optimize


def test_hand_calculated_retrieval():
    m = retrieval_metrics(["a", "unknown", "b"], {"a": 2, "b": 1, "negative": 0})
    assert m["precision@5"] == 0.4
    assert m["pooled_recall@10"] == 1
    assert m["mrr"] == 1
    assert m["map"] == pytest.approx((1 + 2 / 3) / 2)
    assert m["ndcg@10"] == pytest.approx((3 + 1 / 2) / (3 + 1 / math.log2(3)))
    assert m["judgment_coverage"] == pytest.approx(2 / 3)
    assert m["unjudged_count"] == 1
    assert retrieval_metrics([], {})["ndcg@10"] is None


def test_calibration_and_bootstrap():
    m = uncertainty_metrics([[0.8, 0.2], [0.1, 0.9]], [0, 1], 1)
    assert m["local_key_accuracy"] == 1
    assert m["brier"] == pytest.approx(0.05)
    assert bootstrap([1, 2, 3], 42) == bootstrap([1, 2, 3], 42)
    assert paired_comparison([1, 1], [0, 0])["difference_95ci"]["low"] == 1
    assert boundary_metrics([2, 8], [3, 8])["f1"] == 1


def test_agreement_preserves_disagreement():
    result = agreement({"a": {"one": 0, "two": 0}, "b": {"one": 1, "two": 2}, "c": {"one": 2, "two": 2}})
    assert result["overlapping_items"] == 3
    assert 0 < result["cohen_kappa"] < 1
    assert result["krippendorff_alpha_nominal"] is not None


def make_benchmark(session):
    b = Benchmark(name="Tests", synthetic=True)
    session.add(b)
    session.flush()
    for song in session.scalars(select(Song)):
        session.add(
            BenchmarkQuery(
                benchmark_id=b.id,
                category="cadence",
                source_song_id=song.id,
                request=SearchRequest(progression="V7 I", section="chorus", boundary="end").model_dump(),
                synthetic_judgments={f"{song.id}:12:13": 2, f"{song.id}:18:19": 2},
            )
        )
    session.commit()
    return b.id


def test_grouped_split_reproducibility_and_test_guard(session, corpus):
    first, assignments = grouped_splits(session)
    assert first == grouped_splits(session)[0]
    for group in {a["group_id"] for a in assignments}:
        assert len({a["split"] for a in assignments if a["group_id"] == group}) == 1
    bid = make_benchmark(session)
    with pytest.raises(ValueError, match="Freeze"):
        evaluate(session, bid, ["proposed"], "test", 1)
    freeze(session, bid)
    result = evaluate(session, bid, ["proposed"], "test", 1)
    assert result["variants"]["proposed"]["summary"]["ndcg@10"]["mean"] is not None
    with pytest.raises(ValueError, match="already evaluated"):
        evaluate(session, bid, ["proposed"], "test", 1)


def test_optimization_persists_trials(session, corpus):
    bid = make_benchmark(session)
    result = optimize(session, bid, trials=1, study_key="seeded-first")
    resumed = optimize(session, bid, trials=1, study_key="seeded-first")
    repeated = optimize(session, bid, trials=1, study_key="seeded-repeat")
    assert resumed["study_id"] == result["study_id"]
    assert resumed["trials"] == 1
    assert repeated["best_parameters"] == result["best_parameters"]
    assert repeated["best_value"] == result["best_value"]
    assert result["trials"] == 1
    assert 0 <= result["best_value"] <= 1
