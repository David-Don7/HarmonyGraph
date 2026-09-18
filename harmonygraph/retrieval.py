from __future__ import annotations

import time
from collections import Counter, defaultdict, OrderedDict
from threading import RLock
from types import SimpleNamespace
import numpy as np
from sqlalchemy import select
from .contracts import AnalysisConfig, SearchRequest, SearchResponse, SearchResult
from .db import (
    AnalysisRun,
    Artist,
    ChordDefinition,
    ChordEvent,
    FunctionalInterpretation,
    Genre,
    HarmonicRelation,
    ModelConfiguration,
    PatternIndex,
    RetrievalQuery,
    RetrievalResult,
    Section,
    Song,
    SongAnalysis,
    SongGenre,
    record,
)
from .music import Chord, alignment, key_index, key_name, parse_chord, roman_features, tokenize

# Bounded immutable snapshots, keyed by database engine and immutable analysis version.
# This improves warm requests without loading a large corpus into process memory.
_evidence_cache = OrderedDict()
_evidence_lock = RLock()
_cached_events = 0


def active_run(session, analysis_id=None):
    run = (
        session.get(AnalysisRun, analysis_id)
        if analysis_id
        else session.scalar(select(AnalysisRun).where(AnalysisRun.active.is_(True)))
    )
    if not run or run.status != "ready":
        raise ValueError("No ready analysis. Import a dataset and run analysis first.")
    return run


def song_filter(statement, request):
    if request.dataset_ids:
        statement = statement.where(Song.dataset_id.in_(request.dataset_ids))
    if request.song_ids:
        statement = statement.where(Song.id.in_(request.song_ids))
    if request.genre:
        statement = statement.where(
            Song.id.in_(select(SongGenre.song_id).join(Genre).where(Genre.name == request.genre))
        )
    if request.year_from is not None:
        statement = statement.where(Song.year >= request.year_from)
    if request.year_to is not None:
        statement = statement.where(Song.year <= request.year_to)
    return statement


def query_tokens(request):
    if request.pattern != "progression":
        return [], []
    tokens = tokenize(request.progression)
    if not 1 <= len(tokens) <= 32:
        raise ValueError("Queries must contain 1–32 chord events")
    if request.mode in {"literal", "transposed"}:
        chords = [parse_chord(token, strict=True) for token in tokens]
        if any(c.status != "known" for c in chords):
            raise ValueError("Search queries must contain pitched chords")
        return tokens, chords
    for token in tokens:
        roman_features(token)
    return tokens, []


def candidates(session, run, request, config, tokens, query_chords):
    votes = Counter()
    truncated = False
    if request.pattern != "progression":
        stmt = (
            select(HarmonicRelation.song_id, HarmonicRelation.start)
            .join(Song)
            .where(HarmonicRelation.analysis_id == run.id, HarmonicRelation.kind == request.pattern)
        )
        rows = list(
            session.execute(
                song_filter(stmt, request)
                .order_by(HarmonicRelation.confidence.desc())
                .limit(config.candidate_limit + 1)
            )
        )
        return [(sid, start) for sid, start in rows[: config.candidate_limit]], len(rows) > config.candidate_limit
    if request.mode == "literal":
        lookups = [("literal", c.token, i) for i, c in enumerate(query_chords)]
        lookups += [
            ("literal_ngram", "|".join(c.token for c in query_chords[i : i + length]), i)
            for length in (2, 3)
            for i in range(len(tokens) - length + 1)
        ]
    elif request.mode == "transposed":
        lookups = [
            ("transposed", f"{(b.root - a.root) % 12}:{a.shape}:{b.shape}", i)
            for i, (a, b) in enumerate(zip(query_chords, query_chords[1:]))
        ]
        if not lookups:
            lookups = [("shape", query_chords[0].shape, 0)]
    else:
        lookups = [("functional", token, i) for i, token in enumerate(tokens)]
        lookups += [
            ("functional_ngram", "|".join(tokens[i : i + length]), i)
            for length in (2, 3)
            for i in range(len(tokens) - length + 1)
        ]
        if not config.functions:
            lookups = [("quality", roman_features(token)["quality"], i) for i, token in enumerate(tokens)]
        elif not config.qualities:
            lookups = [("degree", str(roman_features(token)["root"]), i) for i, token in enumerate(tokens)]
        if request.mode == "fuzzy":
            # Broaden seeds for quality variants; subsequent alignment evaluates their musical cost.
            for i, token in enumerate(tokens):
                feat = roman_features(token)
                base = token.split("/")[0].removesuffix(feat["suffix"]) if feat["suffix"] else token.split("/")[0]
                lookups.extend(("functional", value, i) for value in {base, base + "7", base + "maj7"})
    for mode, token, offset in set(lookups):
        stmt = (
            select(PatternIndex.song_id, PatternIndex.position)
            .join(Song)
            .where(PatternIndex.analysis_id == run.id, PatternIndex.mode == mode, PatternIndex.token == token)
        )
        if request.section or not request.cross_sections:
            stmt = stmt.join(Section, PatternIndex.section_id == Section.id)
        if request.section:
            stmt = stmt.where(Section.kind == request.section)
        if not request.cross_sections:
            drift = 2 if request.mode == "fuzzy" else 0
            proposed_start = PatternIndex.position - offset
            proposed_end = proposed_start + len(tokens) - 1
            stmt = stmt.where(proposed_start >= Section.start - drift, proposed_end <= Section.end + drift * 2)
            if request.boundary == "start":
                stmt = stmt.where(proposed_start <= Section.start + request.boundary_distance + drift)
            elif request.boundary == "end":
                stmt = stmt.where(proposed_end >= Section.end - request.boundary_distance - drift * 2)
        rows = list(
            session.execute(
                song_filter(stmt, request)
                .order_by(PatternIndex.song_id, PatternIndex.position)
                .limit(config.candidate_limit * 4 + 1)
            )
        )
        truncated |= len(rows) > config.candidate_limit * 4
        for song_id, position in rows[: config.candidate_limit * 4]:
            drift = range(-2, 3) if request.mode == "fuzzy" else [0]
            for shift in drift:
                start = position - offset + shift
                if start >= 0:
                    votes[song_id, start] += (3 if mode.endswith("ngram") else 1) / (1 + abs(shift))
    ordered = sorted(votes, key=lambda candidate: (-votes[candidate], candidate))
    return ordered[: config.candidate_limit], truncated or len(ordered) > config.candidate_limit


def boundary_ok(request, start, end, first, last):
    distances = {"start": start - first.start, "end": last.end - end}
    if request.boundary == "start":
        return distances["start"] <= request.boundary_distance
    if request.boundary == "end":
        return distances["end"] <= request.boundary_distance
    if request.boundary == "interior":
        return min(distances.values()) > request.boundary_distance
    if request.boundary == "adjacent":
        return min(distances.values()) <= request.boundary_distance
    return True


def load_song_evidence(session, song_id, run_id):
    global _cached_events
    cache_key = (session.get_bind(), run_id, song_id)
    with _evidence_lock:
        if cache_key in _evidence_cache:
            _evidence_cache.move_to_end(cache_key)
            return _evidence_cache[cache_key]
    song = session.get(Song, song_id)
    rows = list(
        session.execute(
            select(ChordEvent, ChordDefinition)
            .join(ChordDefinition)
            .where(ChordEvent.song_id == song_id)
            .order_by(ChordEvent.ordinal)
        )
    )
    events = [row[0] for row in rows]
    chords = [Chord(**row[1].canonical) for row in rows]
    sections = {section.id: section for section in session.scalars(select(Section).where(Section.song_id == song_id))}
    analysis = session.get(SongAnalysis, (run_id, song_id))
    alternatives = defaultdict(lambda: defaultdict(list))
    for interpretation in session.scalars(
        select(FunctionalInterpretation)
        .join(ChordEvent, FunctionalInterpretation.event_id == ChordEvent.id)
        .where(ChordEvent.song_id == song_id, FunctionalInterpretation.analysis_id == run_id)
    ):
        alternatives[interpretation.event_id][interpretation.key_index].append(interpretation.data)
    relations = list(
        session.scalars(
            select(HarmonicRelation).where(HarmonicRelation.song_id == song_id, HarmonicRelation.analysis_id == run_id)
        )
    )
    artist = session.get(Artist, song.artist_id) if song.artist_id else None

    def snapshot(row):
        return SimpleNamespace(**record(row)) if row is not None else None

    value = (
        snapshot(song),
        [snapshot(e) for e in events],
        chords,
        {identifier: snapshot(section) for identifier, section in sections.items()},
        snapshot(analysis),
        alternatives,
        [snapshot(r) for r in relations],
        snapshot(artist),
    )
    if analysis is not None and len(events) <= 10000:
        with _evidence_lock:
            if cache_key not in _evidence_cache:
                _evidence_cache[cache_key] = value
                _cached_events += len(events)
            while len(_evidence_cache) > 256 or _cached_events > 50000:
                _, oldest = _evidence_cache.popitem(last=False)
                _cached_events -= len(oldest[1])
    return value


def search(session, request: SearchRequest, persist=False, override=None, candidate_override=None, return_all=False):
    started = time.perf_counter()
    run = active_run(session, request.analysis_id)
    config = override or AnalysisConfig(**session.get(ModelConfiguration, run.configuration_id).parameters)
    tokens, query_chords = query_tokens(request)
    wanted_key = key_index(request.key) if request.key else None
    seeds, truncated = (
        candidates(session, run, request, config, tokens, query_chords)
        if candidate_override is None
        else (candidate_override, False)
    )
    generated = time.perf_counter()
    results = []
    cache = {}
    for song_id, start in seeds:
        if song_id not in cache:
            cache[song_id] = load_song_evidence(session, song_id, run.id)
        song, events, chords, sections, analysis, alternatives, relations, artist = cache[song_id]
        if analysis is None or start >= len(events):
            continue
        lengths = range(max(1, len(tokens) - 2), len(tokens) + 3) if request.mode == "fuzzy" else [len(tokens)]
        if request.pattern != "progression":
            lengths = [2]
        for length in lengths:
            end = start + length - 1
            if end >= len(events):
                continue
            first, last = sections[events[start].section_id], sections[events[end].section_id]
            if first.id != last.id and not request.cross_sections and request.pattern == "progression":
                continue
            if request.section and any(sections[e.section_id].kind != request.section for e in events[start : end + 1]):
                continue
            if not boundary_ok(request, start, end, first, last):
                continue
            selected_relations = [r for r in relations if r.start >= start and r.end <= end]
            features = {r.kind for r in selected_relations if r.confidence >= config.confidence_threshold}
            if not set(request.required_features).issubset(features):
                continue
            posterior = np.asarray(analysis.posterior[start : end + 1]).mean(axis=0)
            keys = np.argsort(posterior)[::-1][: config.top_k if config.uncertainty else 1]
            if wanted_key is not None and wanted_key not in keys:
                continue
            hypotheses = []
            best_sequence, best_trace, best_contribution = [], [], -1
            expected_function = 0.0
            exact_function = False
            for key in keys:
                probability = float(posterior[key]) if config.uncertainty else 1.0
                # A bounded beam retains functional alternatives rather than collapsing each event independently.
                beam = [([], 1.0)]
                for event in events[start : end + 1]:
                    options = alternatives[event.id].get(int(key), [{"roman": "?", "weight": 1.0}])
                    expanded = [
                        (sequence + [option["roman"]], weight * option["weight"])
                        for sequence, weight in beam
                        for option in options
                    ]
                    beam = sorted(expanded, key=lambda item: -item[1])[:16]
                conditional = 0.0
                key_best = {"sequence": [], "similarity": 0.0, "weight": 0.0}
                for sequence, interpretation_weight in beam:
                    if request.mode in {"functional", "fuzzy"} and request.pattern == "progression":
                        similarity, trace = alignment(tokens, sequence, config)
                        exact_function |= sequence == tokens or (
                            (not config.functions or not config.qualities)
                            and len(sequence) == len(tokens)
                            and similarity >= 1 - 1e-10
                        )
                    else:
                        similarity, trace = 0.0, []
                    conditional += interpretation_weight * similarity
                    contribution = probability * interpretation_weight * similarity
                    if contribution > best_contribution:
                        best_contribution, best_sequence, best_trace = contribution, sequence, trace
                    if similarity * interpretation_weight > key_best["similarity"] * key_best["weight"]:
                        key_best = {"sequence": sequence, "similarity": similarity, "weight": interpretation_weight}
                expected_function += probability * conditional
                hypotheses.append(
                    {
                        "key": key_name(int(key)),
                        "key_index": int(key),
                        "probability": float(posterior[key]),
                        "functional_similarity": conditional,
                        "best_interpretation": key_best,
                        "interpretation_mass": sum(weight for _, weight in beam),
                    }
                )
            segment = chords[start : end + 1]
            chord_score = 0.0
            if request.pattern != "progression":
                matches = [r for r in selected_relations if r.kind == request.pattern]
                if not matches:
                    continue
                expected_function = max(r.confidence for r in matches)
                chord_score = 1.0
            elif request.mode == "literal":
                if [c.token for c in segment] != [c.token for c in query_chords]:
                    continue
                chord_score = expected_function = 1.0
                best_trace = [
                    {"operation": "match", "query_index": i, "target_index": i, "cost": 0.0} for i in range(length)
                ]
            elif request.mode == "transposed":
                if any(c.status != "known" for c in segment):
                    continue
                offsets = {(c.root - q.root) % 12 for c, q in zip(segment, query_chords)}
                if len(offsets) != 1 or any(c.shape != q.shape for c, q in zip(segment, query_chords)):
                    continue
                chord_score = expected_function = 1.0
                best_trace = [
                    {"operation": "match", "query_index": i, "target_index": i, "cost": 0.0} for i in range(length)
                ]
            else:
                if request.mode == "functional" and not exact_function:
                    continue
                # Tolerance applies to the best alignment, independently of posterior confidence.
                best_similarity = max((h["best_interpretation"]["similarity"] for h in hypotheses), default=0)
                if request.mode == "fuzzy" and 1 - best_similarity > request.tolerance:
                    continue
                matched = [op for op in best_trace if op["operation"] in {"match", "substitute"}]
                quality_matches = 0
                for op in matched:
                    a = roman_features(tokens[op["query_index"]])
                    c = segment[op["target_index"]]
                    quality_matches += not config.qualities or a["quality"] == c.quality
                chord_score = quality_matches / max(len(tokens), length)
            retained_mass = float(posterior[keys].sum())
            # Sc is also inside the key expectation in the specified ranking equation.
            expected_chord = chord_score * (
                retained_mass if config.uncertainty and request.mode in {"functional", "fuzzy"} else 1.0
            )
            weights = {
                "functional": config.functional_weight,
                "chord": config.chord_weight,
                "section": config.section_weight if config.sections and request.preferred_section else 0.0,
                "boundary": config.boundary_weight if config.boundaries and request.preferred_boundary else 0.0,
            }
            if request.mode in {"literal", "transposed"}:
                weights.update(functional=0.0, chord=1.0)
            total_weight = sum(weights.values())
            weights = {k: v / total_weight for k, v in weights.items()}
            section_score = float(first.kind == request.preferred_section)
            distance = start - first.start if request.preferred_boundary == "start" else last.end - end
            boundary_score = 1 / (1 + distance)
            values = {
                "functional": expected_function,
                "chord": expected_chord,
                "section": section_score,
                "boundary": boundary_score,
            }
            components = {
                name: {"value": values[name], "weight": weight, "contribution": weight * values[name]}
                for name, weight in weights.items()
            }
            # Optional features are reported as evidence and deterministic tie-breakers, preserving the four-term equation.
            score = sum(component["contribution"] for component in components.values())
            evidence = {
                "event_ids": [e.id for e in events[start : end + 1]],
                "dataset_id": song.dataset_id,
                "source_id": song.source_id,
                "synthetic": song.synthetic,
                "section_id": first.id,
                "position": {"from_start": start - first.start, "from_end": last.end - end},
                "relations": [
                    {"id": r.id, "kind": r.kind, "confidence": r.confidence, "evidence": r.evidence}
                    for r in selected_relations
                ],
                "optional_features_matched": sorted(set(request.optional_features) & features),
                "configuration_id": run.configuration_id,
                "confidence_note": "Model posterior; calibration has not been established",
            }
            explanation = f"{length} chord events in {first.label}, {last.end - end} events before its ending. "
            explanation += f"Best supported reading: {' – '.join(best_sequence)}. "
            explanation += " + ".join(
                f"{name} {value['weight']:.3f} × {value['value']:.3f}"
                for name, value in components.items()
                if value["weight"]
            )
            explanation += f" = {score:.4f}. Retained key probability mass: {retained_mass:.3f}."
            results.append(
                SearchResult(
                    passage_id=f"{song.id}:{start}:{end}",
                    song_id=song.id,
                    title=song.title or f"Untitled · {song.source_id}",
                    artist=artist.name if artist else None,
                    section=first.label,
                    start=start,
                    end=end,
                    labels=[e.label for e in events[start : end + 1]],
                    score=score,
                    key_hypotheses=hypotheses,
                    retained_mass=retained_mass,
                    interpretation=best_sequence,
                    alignment=best_trace,
                    components=components,
                    evidence=evidence,
                    explanation=explanation,
                    analysis_id=run.id,
                )
            )
    if request.every_chorus:
        matched_sections = defaultdict(set)
        for result in results:
            section = cache[result.song_id][3][result.evidence["section_id"]]
            if section.kind == "chorus":
                matched_sections[result.song_id].add(section.id)
        valid_songs = {
            sid
            for sid, evidence in cache.items()
            if (choruses := {s.id for s in evidence[3].values() if s.kind == "chorus"})
            and choruses.issubset(matched_sections[sid])
        }
        results = [r for r in results if r.song_id in valid_songs]
    results.sort(key=lambda r: (-r.score, -len(r.evidence["optional_features_matched"]), r.song_id, r.start, r.end))
    unique = {result.passage_id: result for result in reversed(results)}
    results = sorted(
        unique.values(),
        key=lambda r: (-r.score, -len(r.evidence["optional_features_matched"]), r.song_id, r.start, r.end),
    )[: None if return_all else request.limit]
    finished = time.perf_counter()
    if persist:
        query = RetrievalQuery(request=request.model_dump(), analysis_id=run.id)
        session.add(query)
        session.flush()
        session.add_all(
            [
                RetrievalResult(query_id=query.id, rank=i + 1, data=result.model_dump())
                for i, result in enumerate(results)
            ]
        )
        session.commit()
    return SearchResponse(
        results=results,
        analysis_id=run.id,
        candidate_count=len(seeds),
        candidate_limit_reached=truncated,
        timings={
            "candidate_ms": (generated - started) * 1000,
            "rerank_ms": (finished - generated) * 1000,
            "total_ms": (finished - started) * 1000,
        },
    )
