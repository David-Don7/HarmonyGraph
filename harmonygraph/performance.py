"""Explicit offline candidate-recall and scaling audits, never used on ordinary API requests."""

import os
import platform
import tracemalloc
from pathlib import Path
import numpy as np
from sqlalchemy import func, select, text
from .contracts import AnalysisConfig, SearchRequest
from .db import ChordEvent, ModelConfiguration, PatternIndex, Song
from .retrieval import active_run, candidates, query_tokens, search


def candidate_audit(session, request, max_songs=200):
    run = active_run(session, request.analysis_id)
    config = AnalysisConfig(**session.get(ModelConfiguration, run.configuration_id).parameters)
    from .retrieval import song_filter

    ids = list(session.scalars(song_filter(select(Song.id).order_by(Song.id), request).limit(max_songs + 1)))
    if len(ids) > max_songs:
        raise ValueError(f"Exhaustive audit limited to {max_songs} songs. Restrict dataset_ids or song_ids explicitly.")
    tokens, chords = query_tokens(request)
    indexed, truncated = candidates(session, run, request, config, tokens, chords)
    exhaustive = list(
        session.execute(
            select(ChordEvent.song_id, ChordEvent.ordinal)
            .where(ChordEvent.song_id.in_(ids))
            .order_by(ChordEvent.song_id, ChordEvent.ordinal)
        ).tuples()
    )
    oracle = search(session, request, candidate_override=exhaustive, return_all=True)
    matched_starts = {(r.song_id, r.start) for r in oracle.results}
    return {
        "songs": len(ids),
        "exhaustive_matched_passages": len(oracle.results),
        "relevant_starts": len(matched_starts),
        "candidate_start_recall": len(matched_starts & set(indexed)) / len(matched_starts) if matched_starts else None,
        "candidate_limit_reached": truncated,
        "analysis_id": run.id,
        "definition": "Fraction of exhaustive matcher-accepted start positions present in indexed candidate generation; not human relevance recall.",
    }


def benchmark_performance(session, repeats=10, song_counts=(12, 60, 120)):
    run = active_run(session)
    ids = list(session.scalars(select(Song.id).order_by(Song.id)))
    query_templates = [
        SearchRequest(progression="V7 I", section="chorus", boundary="end"),
        SearchRequest(progression="C G Am F", mode="transposed", section="chorus"),
        SearchRequest(progression="I V vi IV", mode="fuzzy", section="chorus"),
    ]
    measurements = []
    for count in song_counts:
        count = min(count, len(ids))
        requests = [q.model_copy(update={"song_ids": ids[:count], "analysis_id": run.id}) for q in query_templates]
        for q in requests:
            search(session, q)
        for q in requests:
            timings = [search(session, q).timings for _ in range(repeats)]
            measurements.append(
                {
                    "songs": count,
                    "mode": q.mode,
                    "query": q.progression,
                    "median_ms": float(np.median([t["total_ms"] for t in timings])),
                    "p95_ms": float(np.quantile([t["total_ms"] for t in timings], 0.95)),
                    "candidate_median_ms": float(np.median([t["candidate_ms"] for t in timings])),
                    "rerank_median_ms": float(np.median([t["rerank_ms"] for t in timings])),
                    "serial_queries_per_second": 1000 / float(np.mean([t["total_ms"] for t in timings])),
                }
            )
    tracemalloc.start()
    search(session, query_templates[-1])
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    if session.get_bind().dialect.name == "postgresql":
        size = session.scalar(text("SELECT pg_database_size(current_database())"))
    else:
        database = session.get_bind().url.database
        size = Path(database).stat().st_size if database and Path(database).exists() else None
    return {
        "analysis_id": run.id,
        "measurements": measurements,
        "repeats": repeats,
        "database_bytes": size,
        "python_allocation_peak_bytes": peak,
        "index_rows": session.scalar(
            select(func.count()).select_from(PatternIndex).where(PatternIndex.analysis_id == run.id)
        ),
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "logical_cpus": os.cpu_count(),
        },
        "note": "Warm serial queries. Python peak allocations measured in a separate fuzzy query, outside latency timing. Process RSS is not measured.",
    }
