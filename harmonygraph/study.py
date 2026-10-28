"""Preparation checks and blinded exports for a development study, never invented labels."""

from sqlalchemy import select
from pydantic import BaseModel, ConfigDict, Field

from .contracts import JudgmentInput, SearchRequest, fingerprint
from .db import Annotator, Benchmark, BenchmarkQuery, RelevanceJudgment
from .research_v2 import READINESS, blinded_pool, labels, validate_protocols


class ReviewSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    annotator_id: str
    material_hash: str
    responses: list[dict] = Field(min_length=1, max_length=3000)
    minutes: float | None = Field(default=None, ge=0, le=10000)


def import_reviews(session, benchmark_id, submission):
    if session.get(Annotator, submission.annotator_id) is None:
        raise ValueError("Choose an existing annotator profile")
    packet = review_packet(session, benchmark_id)
    if submission.material_hash != packet["material_hash"]:
        raise ValueError("Review material changed; download the current packet before submitting")
    allowed = {(q["query_id"], p["passage_id"]) for q in packet["queries"] for p in q["candidates"]}
    seen, rows = set(), []
    for response in submission.responses:
        body = JudgmentInput.model_validate({**response, "annotator_id": submission.annotator_id})
        key = (body.query_id, body.passage_id)
        if key not in allowed or key in seen:
            raise ValueError("Every response must reference a distinct passage in this review packet")
        if body.adjudicated or body.evidence_basis != "chord-only":
            raise ValueError("Packet imports accept independent chord-only review; adjudicate in Benchmark lab")
        seen.add(key)
        rows.append(RelevanceJudgment(
            query_id=body.query_id, passage_id=body.passage_id, annotator_id=body.annotator_id,
            relevance=body.relevance, notes=body.notes, adjudicated=False,
            ratings={**body.model_dump(exclude={"query_id", "passage_id", "annotator_id", "relevance", "notes", "adjudicated"}),
                     "material_hash": submission.material_hash, "review_minutes": submission.minutes},
        ))
    session.add_all(rows)
    session.commit()
    return {"imported": len(rows), "material_hash": submission.material_hash}


def comparison_parameters(session, parameters):
    from .db import SongAnalysis
    from .research import benchmark_hash
    from .retrieval import active_run

    class Parameters(BaseModel):
        model_config = ConfigDict(extra="forbid")
        benchmark_id: str
        song_ids: list[str] = Field(min_length=1, max_length=50)
        analysis_id: str | None = None
        path_budget: int = Field(default=4, ge=1, le=256)

    parsed = Parameters.model_validate(parameters)
    report = readiness(session, parsed.benchmark_id)
    if not report["protocol_ready"]:
        raise ValueError("Complete the research protocol before comparison: " + "; ".join(
            report["issues"] + [f"{r['progression']}: {issue}" for r in report["queries"] for issue in r["issues"]]
        ))
    run = active_run(session, parsed.analysis_id)
    ids = sorted(set(parsed.song_ids))
    analyzed = set(session.scalars(select(SongAnalysis.song_id).where(
        SongAnalysis.analysis_id == run.id, SongAnalysis.song_id.in_(ids)
    )))
    if analyzed != set(ids):
        raise ValueError("All selected songs must belong to the chosen ready analysis")
    return {**parsed.model_dump(), "song_ids": ids, "analysis_id": run.id,
            "benchmark_hash": benchmark_hash(session, parsed.benchmark_id)}


def queries_for(session, benchmark_id):
    if session.get(Benchmark, benchmark_id) is None:
        raise ValueError("Benchmark does not exist")
    return list(session.scalars(
        select(BenchmarkQuery).where(BenchmarkQuery.benchmark_id == benchmark_id).order_by(BenchmarkQuery.id)
    ))


def readiness(session, benchmark_id):
    benchmark = session.get(Benchmark, benchmark_id)
    queries = queries_for(session, benchmark_id)
    issues = []
    if not queries:
        issues.append("Add at least one query with a source song and frozen chord context.")
    if len(queries) > 30:
        issues.append("The development comparison supports at most 30 queries.")
    try:
        validate_protocols(queries)
    except ValueError as error:
        issues.append(str(error))
    rows = []
    profiles = {a.id: a for a in session.scalars(select(Annotator))}
    for query in queries:
        protocol = query.protocol or {}
        problems = []
        if protocol.get("split") not in {"pilot", "train", "validation"}:
            problems.append("Declare a development split: pilot, train or validation.")
        for field in ("family", "subtype", "context", "context_hash"):
            if not protocol.get(field):
                problems.append(f"Missing {field.replace('_', ' ')}.")
        try:
            SearchRequest(**{**query.request, "ranking": "path_expectation"})
        except ValueError:
            problems.append("Research queries require 2–8 Roman numerals in functional or fuzzy mode.")
        pool_ids = {p["passage_id"] for p in query.pool or []}
        latest = {}
        for judgment in session.scalars(select(RelevanceJudgment).where(
            RelevanceJudgment.query_id == query.id
        ).order_by(RelevanceJudgment.created_at, RelevanceJudgment.id)):
            if not judgment.adjudicated and (judgment.ratings or {}).get("evidence_basis", "chord-only") == "chord-only":
                latest[(judgment.passage_id, judgment.annotator_id)] = judgment
        qualified = {}
        for (passage, annotator), judgment in latest.items():
            if judgment.relevance is not None and profiles.get(annotator) and profiles[annotator].qualifications.strip():
                qualified.setdefault(passage, set()).add(annotator)
        double_reviewed = sum(len(qualified.get(p, set())) >= 2 for p in pool_ids)
        adjudicated = len(pool_ids & labels(session, query).keys())
        rows.append({
            "query_id": query.id, "progression": query.request.get("progression", ""),
            "split": protocol.get("split"), "family": protocol.get("family"),
            "subtype": protocol.get("subtype"), "pool_size": len(pool_ids),
            "double_reviewed": double_reviewed, "adjudicated": adjudicated,
            "issues": problems,
        })
    protocol_ready = bool(queries) and not issues and not any(row["issues"] for row in rows)
    annotation_ready = protocol_ready and all(row["pool_size"] > 0 for row in rows)
    review_complete = annotation_ready and all(
        row["double_reviewed"] == row["pool_size"] == row["adjudicated"] for row in rows
    )
    return {
        "benchmark_id": benchmark_id, "name": benchmark.name, "synthetic": benchmark.synthetic,
        "protocol_ready": protocol_ready, "annotation_ready": annotation_ready,
        "review_complete": review_complete, "held_out_ready": False,
        "issues": issues, "queries": rows, "research": READINESS,
        "notice": "Development readiness only. Qualifications are self-reported; independent musical validity and strong comparators remain study gates.",
    }


def review_packet(session, benchmark_id):
    queries = queries_for(session, benchmark_id)
    # A hash of the blinded material pins exactly what a reviewer saw. No model
    # rankings, scores, synthetic truth, or other reviewers' answers are exported.
    material = [{
        "query_id": q.id, "request": {k: v for k, v in q.request.items() if k in {
            "progression", "mode", "pattern", "section", "boundary", "boundary_distance", "cross_sections",
        }},
        "source_context": (q.protocol or {}).get("context"),
        "context_hash": (q.protocol or {}).get("context_hash"),
        "candidates": blinded_pool(q)["candidates"],
    } for q in queries]
    return {
        "schema": "harmonygraph-blinded-review-v1", "benchmark_id": benchmark_id,
        "material_hash": fingerprint(material), "queries": material,
        "rubric": {"2": "Supported functional match", "1": "Partial match", "0": "Unsupported match",
                   "unresolved": "Leave relevance null when context or idiom is insufficient."},
        "instructions": "Judge using chords and section context only. Work independently. Record qualifications and time spent. Model scores and other reviewers' answers are hidden.",
        "reviewer": {"name": "", "qualifications": "", "minutes": None},
        "responses": [{"query_id": q["query_id"], "passage_id": p["passage_id"],
                       "relevance": None, "status": "unresolved", "notes": ""}
                      for q in material for p in q["candidates"]],
    }
