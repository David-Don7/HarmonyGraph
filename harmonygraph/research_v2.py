"""Bounded, inspectable research-v2 development workflow. No automatic study claims."""

from __future__ import annotations

import json
import platform
import time
from collections import Counter
from pathlib import Path

import numpy as np
from sqlalchemy import select

from .contracts import AnalysisConfig, SearchRequest, fingerprint
from .db import BenchmarkQuery, Dataset, ModelConfiguration, RelevanceJudgment
from .metrics import retrieval_metrics
from .paths import VERSION, context_messages, passage_score
from .retrieval import active_run, candidates, load_evidence_batch, search

METHODS = (
    "legacy_mixture",
    "hard_path",
    "path_expectation",
    "uniform_path",
    "max_path",
    "equal_paths",
    "shuffled_paths",
)
READINESS = {
    "method": VERSION,
    "primary_task": "Explicit 2–8 Roman numerals, chord-only context, expected best alignment per path",
    "gates": {
        "data": "Bounded audit and packet available; expert feasibility pending",
        "method": "Exact tiny-case software checks required; musical validity unestablished",
        "pilot": "Independent annotation and burden measurement pending",
        "study": "Frozen held-out evaluation pending",
        "paper": "No superiority or first-system claim",
    },
    "comparators": {
        "controlled": list(METHODS),
        "pending": [
            "Hanna 2009 local-transposition reproduction/adaptation",
            "HarmTrace 2011 faithful adaptation",
            "train-only chord-sequence embedding",
            "expected-local-cost alignment",
            "global-key path control",
        ],
    },
    "limitations": [
        "24 major/minor states do not cover every musical idiom",
        "Function weights are theory assumptions, not calibrated human probabilities",
        "Bounded candidate generation may omit relevant passages",
        "Strong prior-work comparators must run before comparative research claims",
    ],
}


def blinded_pool(query):
    """Explicit allowlist: never send scores, ranks, methods or inferred confidence."""
    items = []
    for item in sorted(query.pool or [], key=lambda r: fingerprint([query.id, r["passage_id"]])):
        items.append(
            {
                key: item.get(key)
                for key in ("passage_id", "song_id", "title", "artist", "section", "start", "end", "labels")
            }
        )
        items[-1]["context"] = (item.get("evidence") or {}).get("context_labels", [])
    return {
        "query_id": query.id,
        "request": query.request,
        "protocol": query.protocol,
        "candidates": items,
        "scores_hidden": True,
    }


def freeze_context(session, source_song_id, protocol):
    """Snapshot the same complete chord chart available to inference, without labels."""
    if not source_song_id:
        return dict(protocol)
    from .db import ChordEvent, Section, Song

    song = session.get(Song, source_song_id)
    if song is None:
        raise ValueError("Query source song does not exist")
    events = list(session.scalars(select(ChordEvent).where(ChordEvent.song_id == song.id).order_by(ChordEvent.ordinal)))
    sections = {sec.id: sec.label for sec in session.scalars(select(Section).where(Section.song_id == song.id))}
    context = {
        "song_id": song.id,
        "source_id": song.source_id,
        "content_hash": song.content_hash,
        "labels": [e.label for e in events],
        "sections": [sections[e.section_id] for e in events],
        "evidence_basis": "chord-only",
    }
    return {**protocol, "context": context, "context_hash": fingerprint(context)}


def validate_protocols(queries):
    groups = {}
    for q in queries:
        protocol = q.protocol or {}
        split = protocol.get("split")
        for kind in ("family", "cover_family", "source_passage", "cross_corpus_group"):
            value = protocol.get(kind)
            if value and split:
                group = groups.setdefault((kind, value), set())
                group.add(split)
                if len(group) > 1:
                    raise ValueError(f"Split leakage in {kind}: {value}")
        if protocol.get("context") and fingerprint(protocol["context"]) != protocol.get("context_hash"):
            raise ValueError("Frozen query context hash does not match its content")


def clustered_comparison(left, right, families, seed=42, iterations=2000):
    """Paired query-mean difference, resampling whole dependent families."""
    groups = {}
    for a, b, family in zip(left, right, families, strict=True):
        if a is not None and b is not None:
            groups.setdefault(family, []).append(a - b)
    if not groups:
        return {"mean": None, "low": None, "high": None, "clusters": 0}
    values = list(groups.values())
    rng = np.random.default_rng(seed)
    draws = [
        np.mean([v for i in rng.integers(0, len(values), len(values)) for v in values[i]]) for _ in range(iterations)
    ]
    return {
        "mean": float(np.mean([v for group in values for v in group])),
        "low": float(np.quantile(draws, 0.025)),
        "high": float(np.quantile(draws, 0.975)),
        "clusters": len(values),
        "unit": "source/query family",
        "iterations": iterations,
    }


def labels(session, query, annotator=None):
    """Adjudicated chord-only judgments primary; individual rater sensitivity optional."""
    stmt = select(RelevanceJudgment).where(RelevanceJudgment.query_id == query.id)
    stmt = (
        stmt.where(RelevanceJudgment.annotator_id == annotator, RelevanceJudgment.adjudicated.is_(False))
        if annotator
        else stmt.where(RelevanceJudgment.adjudicated.is_(True))
    )
    latest = {}
    for row in session.scalars(stmt.order_by(RelevanceJudgment.created_at, RelevanceJudgment.id)):
        if (row.ratings or {}).get("evidence_basis", "chord-only") == "chord-only":
            latest[row.passage_id] = row.relevance
    return {p: grade for p, grade in latest.items() if grade is not None}


def controlled_run(session, benchmark_id, song_ids, *, analysis_id=None, path_budget=32, annotator=None):
    """Development-only comparison; one union pool, one analysis/config, same hard filters.

    Held-out work deliberately requires a separate frozen study rather than silently
    reusing the legacy runner's weaker protocol. No synthetic judgments are inferred.
    """
    if not song_ids or len(song_ids) > 50:
        raise ValueError("Choose 1–50 explicit development songs")
    queries = list(
        session.scalars(
            select(BenchmarkQuery).where(BenchmarkQuery.benchmark_id == benchmark_id).order_by(BenchmarkQuery.id)
        )
    )
    if not queries or len(queries) > 30:
        raise ValueError("Choose a bounded benchmark of 1–30 development queries")
    validate_protocols(queries)
    for q in queries:
        protocol = q.protocol or {}
        if protocol.get("split") not in {"pilot", "train", "validation"}:
            raise ValueError(
                "Each query must explicitly declare a development split; held-out test is not enabled here"
            )
        if (
            not protocol.get("family")
            or not protocol.get("subtype")
            or not protocol.get("context_hash")
            or not protocol.get("context")
        ):
            raise ValueError("Freeze query family, prelabelled subtype and context_hash before comparison")
    run = active_run(session, analysis_id)
    config = AnalysisConfig(**session.get(ModelConfiguration, run.configuration_id).parameters)
    evidence = load_evidence_batch(session, song_ids, run.id)
    output = {method: [] for method in METHODS}
    shared = {}
    for q in queries:
        request = SearchRequest(
            **{
                **q.request,
                "ranking": "path_expectation",
                "song_ids": song_ids,
                "analysis_id": run.id,
                "path_budget": path_budget,
            }
        )
        from .retrieval import query_tokens

        tokens, chords = query_tokens(request)
        seeds, truncated = candidates(session, run, request, config, tokens, chords)
        shared[q.id] = {"seeds": [list(seed) for seed in seeds], "truncated": truncated, "hash": fingerprint(seeds)}
        truth = labels(session, q, annotator)
        for method in METHODS:
            cfg = (
                config.model_copy(update={"theory_costs": False, "insertion": 1.0, "deletion": 1.0})
                if method == "uniform_path"
                else config
            )
            req = request.model_copy(update={"ranking": "path_expectation" if method == "uniform_path" else method})
            response = search(
                session, req, override=cfg, candidate_override=seeds, evidence_context=evidence, ranking_only=True
            )
            metrics = (
                retrieval_metrics([r.passage_id for r in response.results], truth)
                if truth
                else {"ndcg@10": None, "reason": "No resolved chord-only judgments for this label policy"}
            )
            output[method].append(
                {
                    "query_id": q.id,
                    "family": q.protocol["family"],
                    "subtype": q.protocol["subtype"],
                    "metrics": metrics,
                    "timings": response.timings,
                    "passages": [r.passage_id for r in response.results],
                }
            )
    from .research import benchmark_hash

    manifest = {
        "version": VERSION,
        "analysis_id": run.id,
        "configuration_hash": fingerprint(config.model_dump()),
        "benchmark_hash": benchmark_hash(session, benchmark_id),
        "song_ids": sorted(song_ids),
        "content_hashes": sorted((sid, e[0].content_hash) for sid, e in evidence.items()),
        "candidate_pools": shared,
        "methods": list(METHODS),
        "path_budget": path_budget,
        "label_policy": f"annotator:{annotator}" if annotator else "adjudicated-chord-only",
        "normalization": "max(query length, passage length)",
        "gain": [0, 1, 3],
        "phase": "development-only; no held-out test claim",
        "environment": platform.platform(),
    }
    comparisons = {
        method: clustered_comparison(
            [r["metrics"].get("ndcg@10") for r in output["path_expectation"]],
            [r["metrics"].get("ndcg@10") for r in output[method]],
            [q.protocol["family"] for q in queries],
        )
        for method in METHODS
        if method != "path_expectation"
    }
    return {
        "manifest": manifest,
        "manifest_hash": fingerprint(manifest),
        "methods": output,
        "paired_clustered_comparisons": comparisons,
        "readiness": READINESS,
    }


def bounded_audit(session, song_ids, *, analysis_id=None, example_count=8, budgets=(4, 16, 64)):
    """A fixed-model computational audit and blinded feasibility packet, not labels.

    Samples sections by source order before looking at scores; does not call these
    passages ambiguous, relevant or expert verified. Writes no catalog state.
    """
    if not 1 <= len(song_ids) <= 20 or not 6 <= example_count <= 10:
        raise ValueError("Audit requires 1–20 explicit songs and a 6–10-example packet")
    run = active_run(session, analysis_id)
    config = AnalysisConfig(**session.get(ModelConfiguration, run.configuration_id).parameters)
    evidence = load_evidence_batch(session, song_ids, run.id)
    if len(evidence) != len(set(song_ids)) or any(e[4] is None for e in evidence.values()):
        raise ValueError("Every audit song must have this analysis")
    unknown, counts, datasets, examples, measurements = Counter(), Counter(), {}, [], []
    messages = {}
    for sid in sorted(evidence, key=lambda sid: evidence[sid][0].source_id):
        song, events, chords, sections, _, _, _, artist = evidence[sid]
        source = session.get(Dataset, song.dataset_id)
        datasets[source.id] = {
            "name": source.name,
            "source": source.source,
            "fingerprint": source.fingerprint,
            "license": source.license,
        }
        counts["synthetic_songs" if song.synthetic else "real_songs"] += 1
        counts["events"] += len(events)
        for e, c in zip(events, chords):
            counts[c.status] += 1
            if c.status != "known":
                unknown[e.label] += 1
        messages[sid] = context_messages(chords, events, config)
        # One natural section opening per song, then fill from remaining sections.
    sections_to_review = []
    ordered_ids = sorted(evidence, key=lambda sid: evidence[sid][0].source_id)
    for slot in range(max(len(evidence[sid][3]) for sid in ordered_ids)):
        for sid in ordered_ids:
            sections = sorted(evidence[sid][3].values(), key=lambda sec: sec.start)
            if slot < len(sections) and sections[slot].end - sections[slot].start >= 1:
                sections_to_review.append((sid, sections[slot]))
    for sid, section in sections_to_review[:example_count]:
        song, events, chords, sections, _, _, _, artist = evidence[sid]
        start, end = section.start, min(section.start + 2, section.end)
        # Fixed query independent of each example's inferred interpretation.
        query = "ii V I"
        req = SearchRequest(
            progression=query, mode="functional", ranking="path_expectation", song_ids=song_ids, analysis_id=run.id
        )
        curves = []
        for budget in budgets:
            req = req.model_copy(update={"path_budget": budget})
            began = time.perf_counter()
            result = passage_score(query.split(), chords, events, start, end, config, req, messages[sid])
            curves.append(
                {
                    "budget": budget,
                    "ms": (time.perf_counter() - began) * 1000,
                    "mass": result["retained_mass"],
                    "score": result["score"],
                    "bounds": result["expected_similarity_bounds"],
                    "joint_paths": len(result["paths"]),
                }
            )
        pid = f"{sid}:{start}:{end}"
        context = {
            "labels": [e.label for e in events],
            "sections": [sections[e.section_id].label for e in events],
            "source_id": song.source_id,
            "dataset_id": song.dataset_id,
            "content_hash": song.content_hash,
        }
        examples.append(
            {
                "example_id": len(examples) + 1,
                "passage_id": pid,
                "query": query,
                "title": song.title,
                "artist": artist.name if artist else None,
                "start": start,
                "end": end,
                "synthetic": song.synthetic,
                "constructed_context_swap": False,
                "context": context,
                "context_hash": fingerprint(context),
                "evidence_basis": "chord-only",
                "candidate_interpretations": sorted({tuple(p["functions"]) for p in result["paths"][:8]}),
                "subtype": "unclassified natural context; reviewer assignment pending",
                "rating": {
                    "relevance": None,
                    "status": "unresolved",
                    "supported_interpretations": [],
                    "section_correct": None,
                    "notes": "",
                },
            }
        )
        measurements.append({"passage_id": pid, "curves": curves})
    if len(examples) < example_count:
        raise ValueError("Not enough natural sections for a 6–10-example packet; include more analyzed songs")
    req = SearchRequest(
        progression="ii V I",
        mode="functional",
        ranking="path_expectation",
        song_ids=song_ids,
        analysis_id=run.id,
        path_budget=min(budgets),
    )
    exhaustive_seeds = [(sid, e.ordinal) for sid in ordered_ids for e in evidence[sid][1]]
    indexed = search(session, req, evidence_context=evidence, return_all=True)
    exhaustive = search(session, req, candidate_override=exhaustive_seeds, evidence_context=evidence, return_all=True)
    oracle = {r.passage_id for r in exhaustive.results[:10]}
    indexed_ids = {r.passage_id for r in indexed.results}
    manifest = {
        "version": VERSION,
        "analysis_id": run.id,
        "configuration": config.model_dump(),
        "datasets": datasets,
        "songs": sorted((sid, e[0].content_hash) for sid, e in evidence.items()),
        "selection": "Source-order section openings; not a representative or ambiguity-labelled sample",
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "concurrency": 1,
            "cache": "in-process evidence cache; sequential budget calls",
        },
    }
    packet = {
        "rubric": {
            "2": "Supports the requested functions in this chord-only context",
            "1": "Partial functional support or approximate match",
            "0": "Does not support the requested functions",
            "unresolved": "Insufficient context, unsupported idiom or unresolved interpretation; leave grade null",
        },
        "instructions": "Work independently. Alternative readings are model suggestions, not labels. Record qualifications, review time and supported interpretations. Do not infer missing rhythm or melody.",
        "examples": examples,
        "manifest_hash": fingerprint(manifest),
        "independent_review": "pending",
    }
    audit = {
        "manifest": manifest,
        "manifest_hash": fingerprint(manifest),
        "coverage": dict(counts),
        "unknown_labels": dict(unknown),
        "approximation_curves": measurements,
        "candidate_audit": {
            "query": req.model_dump(),
            "exhaustive_starts": len(exhaustive_seeds),
            "indexed_starts": indexed.candidate_count,
            "candidate_limit_reached": indexed.candidate_limit_reached,
            "recall_of_exhaustive_model_top10": len(oracle & indexed_ids) / len(oracle) if oracle else None,
            "scope": "These explicit songs, fixed beam and exact-length windows; not human relevance recall",
        },
        "human_relevance": None,
        "explanation_usefulness": None,
        "readiness": READINESS,
    }
    return audit, packet


def export_packet(directory, audit, packet):
    root = Path(directory) / audit["manifest_hash"][:16]
    root.mkdir(parents=True, exist_ok=True)
    for name, data in (("audit.json", audit), ("annotation-packet.json", packet)):
        (root / name).write_text(json.dumps(data, indent=2), encoding="utf-8")
    lines = [
        "# HarmonyGraph chord-only review packet",
        "",
        packet["instructions"],
        "",
        "Independent reviewer: __________  Qualifications: __________  Minutes: __________",
        "",
        "Grades: 2 = supported; 1 = partial; 0 = unsupported match. Insufficient/unsupported-idiom/unresolved: leave grade blank.",
        "",
    ]
    for example in packet["examples"]:
        lines += [
            f"## Example {example['example_id']}: {example['title'] or 'Title unavailable'}",
            "",
            f"Query: {example['query']}. Inspect events {example['start'] + 1}–{example['end'] + 1}.",
            "",
            " | ".join(f"{i + 1}: {c}" for i, c in enumerate(example["context"]["labels"])),
            "",
            "Candidate readings (unvalidated): "
            + "; ".join(" – ".join(p) for p in example["candidate_interpretations"]),
            "",
            "Grade / unresolved status: ____ Supported interpretations: ____ Section correct: ____ Notes: ____",
            "",
        ]
    (root / "annotation-packet.md").write_text("\n".join(lines), encoding="utf-8")
    return str(root.resolve())
