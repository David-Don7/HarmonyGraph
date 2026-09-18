import json
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from harmonygraph.analysis import analyze
from harmonygraph.api import create_app
from harmonygraph.contracts import AnalysisConfig, SearchRequest
from harmonygraph.db import AnalysisRun, Job, Song
from harmonygraph.ingestion import ingest
from harmonygraph.jobs import claim_job
from harmonygraph.retrieval import search


def test_import_idempotent(session, corpus):
    imported, _, path = corpus
    second = ingest(session, path)
    assert second["imported"] == 0 and second["skipped"] == 12
    assert session.scalar(select(func.count()).select_from(Song)) == 12


def test_transposed_all_roots_literal_one(session, corpus):
    common = dict(progression="C G Am F", section="chorus", limit=100)
    transposed = search(session, SearchRequest(**common, mode="transposed"))
    literal = search(session, SearchRequest(**common, mode="literal"))
    assert len({r.song_id for r in transposed.results}) == 12
    assert len({r.song_id for r in literal.results}) == 1


def test_functional_boundary_explanations(session, corpus):
    response = search(session, SearchRequest(progression="V7 I", boundary="end", section="chorus", limit=100))
    assert len(response.results) == 24
    for result in response.results:
        assert result.evidence["position"]["from_end"] == 0
        assert result.score == pytest.approx(sum(c["contribution"] for c in result.components.values()))
        assert result.evidence["event_ids"]
        assert result.analysis_id == corpus[1]
        assert result.interpretation == ["V7", "I"]


def test_every_chorus_and_filters(session, corpus):
    response = search(
        session, SearchRequest(progression="V7 I", every_chorus=True, section="chorus", genre="fixture", limit=100)
    )
    assert len(response.results) == 24
    assert not search(session, SearchRequest(progression="V7 I", genre="absent")).results


def test_cache_and_failed_analysis_preserve_active(session, corpus, monkeypatch):
    run = corpus[1]
    assert analyze(session) == run

    def fail(*args):
        raise RuntimeError("index failed")

    monkeypatch.setattr("harmonygraph.analysis.process_song", fail)
    with pytest.raises(RuntimeError):
        analyze(session, AnalysisConfig(window=9))
    assert session.get(AnalysisRun, run).active
    assert session.scalar(select(AnalysisRun).where(AnalysisRun.status == "failed")) is not None


def test_durable_job_claim_cancel_recover(session):
    old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    job = Job(kind="analyze", status="running", owner="dead", updated_at=old)
    session.add(job)
    session.commit()
    assert claim_job(session, "new") == job.id
    assert claim_job(session, "second") is None
    cancelled = Job(kind="demo", cancel_requested=True)
    session.add(cancelled)
    session.commit()
    assert claim_job(session, "new") is None
    session.refresh(cancelled)
    assert cancelled.status == "cancelled"


def test_api_annotation_independence_and_exports(engine, session, corpus):
    client = TestClient(create_app(engine))
    assert client.get("/api/v1/health").status_code == 200
    assert client.post("/api/v1/search", json={"progression": "nonsense"}).status_code == 422
    a = client.post("/api/v1/annotators", json={"name": "One"}).json()
    b = client.post("/api/v1/annotators", json={"name": "Two"}).json()
    bench = client.post("/api/v1/benchmarks", json={"name": "Test benchmark"}).json()
    song = session.scalar(select(Song))
    query = client.post(
        f"/api/v1/benchmarks/{bench['id']}/queries",
        json={
            "category": "cadence",
            "source_song_id": song.id,
            "request": {"progression": "V7 I", "section": "chorus"},
        },
    ).json()
    pool = client.post(f"/api/v1/benchmark-queries/{query['id']}/pool", json={}).json()
    assert pool
    body = {"query_id": query["id"], "passage_id": pool[0]["passage_id"], "annotator_id": a["id"], "relevance": 2}
    assert client.post("/api/v1/judgments", json=body).status_code == 201
    assert client.get(f"/api/v1/benchmark-queries/{query['id']}/judgments?annotator_id={b['id']}").json() == []
    assert (
        len(client.get(f"/api/v1/benchmark-queries/{query['id']}/judgments?annotator_id={b['id']}&review=true").json())
        == 1
    )
    assert client.get(f"/api/v1/benchmarks/{bench['id']}/export").status_code == 200
    assert client.get(f"/api/v1/songs/{song.id}").json()["events"]
    edited = client.post(
        f"/api/v1/benchmark-queries/{query['id']}",
        json={"category": "revised", "source_song_id": song.id, "request": {"progression": "I V"}},
    ).json()
    assert edited["benchmark_id"] != bench["id"]
    assert edited["previous_benchmark_id"] == bench["id"]
    assert edited["id"] != query["id"] and edited["pool"] == []
    original = client.get(f"/api/v1/benchmarks/{bench['id']}/queries").json()[0]
    assert original["request"]["progression"] == "V7 I"
    assert client.get(f"/api/v1/benchmark-queries/{edited['id']}/judgments?annotator_id={a['id']}").json() == []
    assert len(client.get(f"/api/v1/benchmark-queries/{query['id']}/judgments?annotator_id={a['id']}").json()) == 1


def test_ingest_reports_bad_rows_without_dropping_valid(session, tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text(
        "{not json}\n"
        + json.dumps({"source_id": "good", "sections": [{"events": [{"label": "C"}, {"label": "unsupported"}]}]})
        + "\n"
    )
    report = ingest(session, path)
    assert report["invalid"] == 1 and report["imported"] == 1 and report["unknown_chords"] == 1


def test_job_api_returns_public_contract(engine):
    client = TestClient(create_app(engine))
    response = client.post("/api/v1/jobs", json={"kind": "analyze", "parameters": {}})
    assert response.status_code == 202
    job = response.json()
    assert job["status"] == "queued"
    assert "owner" not in job
    assert client.get("/api/v1/jobs").json()[0]["id"] == job["id"]
    assert client.post(f"/api/v1/jobs/{job['id']}/cancel", json={}).status_code == 200


def test_secondary_dominant_chain_retains_event_evidence(session, tmp_path):
    from harmonygraph.db import HarmonicRelation

    path = tmp_path / "chain.jsonl"
    path.write_text(
        json.dumps(
            {
                "source_id": "chain",
                "sections": [
                    {
                        "label": "chorus",
                        "events": [{"label": c} for c in ["C", "F", "G7", "C", "E7", "A7", "D7", "G7", "C"]],
                    }
                ],
            }
        )
    )
    ingest(session, path)
    run_id = analyze(session)
    chains = list(
        session.scalars(
            select(HarmonicRelation).where(
                HarmonicRelation.analysis_id == run_id, HarmonicRelation.kind == "secondary_dominant_chain"
            )
        )
    )
    assert len(chains) == 1
    assert (chains[0].start, chains[0].end) == (4, 8)
    assert len(chains[0].evidence["event_ids"]) == 5
    assert chains[0].evidence["roots"] == [4, 9, 2, 7, 0]
