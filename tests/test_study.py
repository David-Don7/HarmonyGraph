import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from harmonygraph.api import create_app
from harmonygraph.db import Annotator, Benchmark, BenchmarkQuery, RelevanceJudgment, Song
from harmonygraph.jobs import dispatch
from harmonygraph.research_v2 import freeze_context
from harmonygraph.study import ReviewSubmission, comparison_parameters, import_reviews, readiness, review_packet


@pytest.fixture
def study(session, corpus):
    song = session.scalar(select(Song).where(Song.source_id == "0"))
    benchmark = Benchmark(name="Study test", synthetic=True)
    session.add(benchmark)
    session.flush()
    query = BenchmarkQuery(
        benchmark_id=benchmark.id, source_song_id=song.id, category="control",
        request={"progression": "V7 I", "ranking": "path_expectation", "song_ids": [song.id], "path_budget": 1},
        protocol=freeze_context(session, song.id, {"family": "source-0", "split": "pilot", "subtype": "control"}),
        pool=[{"passage_id": f"{song.id}:12:13", "song_id": song.id, "title": song.title,
               "labels": ["G7", "C"], "score": 0.9, "evidence": {"context_labels": ["C", "G7", "C"]}}],
    )
    session.add(query)
    session.commit()
    return benchmark, query, song


def test_readiness_is_not_a_scientific_completion_claim(session, study):
    benchmark, query, _ = study
    report = readiness(session, benchmark.id)
    assert report["protocol_ready"] and report["annotation_ready"]
    assert not report["review_complete"] and not report["held_out_ready"]
    query.protocol = {**query.protocol, "split": "test"}
    session.commit()
    assert not readiness(session, benchmark.id)["protocol_ready"]
    with pytest.raises(ValueError, match="development split"):
        comparison_parameters(session, {"benchmark_id": benchmark.id, "song_ids": [study[2].id]})


def test_review_packet_is_blinded_and_import_is_atomic(session, study):
    benchmark, query, _ = study
    reviewer = Annotator(name="Test reviewer", qualifications="Software fixture, not expert evidence")
    session.add(reviewer)
    session.commit()
    packet = review_packet(session, benchmark.id)
    assert '"score":' not in json.dumps(packet)
    assert "path_expectation" not in json.dumps(packet)
    responses = [{**packet["responses"][0], "relevance": 2, "status": "judged"}]
    body = {"annotator_id": reviewer.id, "material_hash": packet["material_hash"], "responses": responses}
    with pytest.raises(ValueError, match="distinct passage"):
        import_reviews(session, benchmark.id, ReviewSubmission(**{**body, "responses": responses * 2}))
    assert session.scalar(select(func.count()).select_from(RelevanceJudgment)) == 0
    assert import_reviews(session, benchmark.id, ReviewSubmission(**body))["imported"] == 1
    assert readiness(session, benchmark.id)["queries"][0]["double_reviewed"] == 0
    query.pool = query.pool + [{**query.pool[0], "passage_id": "changed-pool"}]
    session.commit()
    with pytest.raises(ValueError, match="material changed"):
        import_reviews(session, benchmark.id, ReviewSubmission(**body))


def test_comparison_pins_analysis_and_rejects_stale_benchmark(session, study, corpus):
    benchmark, query, song = study
    parameters = comparison_parameters(session, {"benchmark_id": benchmark.id, "song_ids": [song.id]})
    assert parameters["analysis_id"] == corpus[1]
    assert parameters["benchmark_hash"]
    with pytest.raises(ValueError, match="chosen ready analysis"):
        comparison_parameters(session, {"benchmark_id": benchmark.id, "song_ids": ["missing"]})
    query.protocol = {**query.protocol, "family": "changed"}
    session.commit()
    with pytest.raises(ValueError, match="changed after"):
        dispatch(session, "research_v2_compare", parameters, lambda _: None)


def test_api_requires_adjudication_sources_and_exports_only_finished_jobs(engine, session, study):
    benchmark, query, _ = study
    client = TestClient(create_app(engine))
    reviewers = [client.post("/api/v1/annotators", json={"name": n, "qualifications": "Test fixture"}).json()
                 for n in ("First", "Second", "Adjudicator")]
    payload = {"query_id": query.id, "passage_id": query.pool[0]["passage_id"],
               "annotator_id": reviewers[2]["id"], "relevance": 2, "adjudicated": True}
    assert client.post("/api/v1/judgments", json=payload).status_code == 422
    sources = [client.post("/api/v1/judgments", json={**payload, "annotator_id": r["id"], "adjudicated": False}).json()
               for r in reviewers[:2]]
    response = client.post("/api/v1/judgments", json={**payload, "adjudication_sources": [r["id"] for r in sources]})
    assert response.status_code == 201
    result = client.get(f"/api/v1/benchmarks/{benchmark.id}/readiness").json()
    assert result["review_complete"] and not result["held_out_ready"]
    queued = client.post("/api/v1/jobs", json={"kind": "research_v2_compare", "parameters": {
        "benchmark_id": benchmark.id, "song_ids": [study[2].id],
    }})
    assert queued.status_code == 202
    assert client.get(f"/api/v1/jobs/{queued.json()['id']}/export").status_code == 422
    assert client.get(f"/api/v1/benchmarks/{benchmark.id}/review-packet").headers["content-disposition"]


def test_partial_labels_do_not_become_zero_relevance(session, study):
    from harmonygraph.research_v2 import controlled_run

    benchmark, query, song = study
    reviewer = Annotator(name="Adjudicator fixture")
    session.add(reviewer)
    session.flush()
    session.add(RelevanceJudgment(query_id=query.id, passage_id="unranked-passage", annotator_id=reviewer.id,
                                 relevance=2, adjudicated=True, ratings={"evidence_basis": "chord-only"}))
    session.commit()
    result = controlled_run(session, benchmark.id, [song.id], path_budget=1)
    for rows in result["methods"].values():
        assert rows[0]["metrics"]["ndcg@10"] is None
        assert rows[0]["metrics"]["returned_at_10"] > 0
