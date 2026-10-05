"""Consumer-only interfaces. Raw and synthetic research data cannot leak into these routes."""

from __future__ import annotations

import time
from typing import Literal
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import case, func, or_, select

from .catalog import SOURCE, sections_from_row
from .contracts import AnalysisConfig, SearchRequest, SearchResult
from .db import CatalogArtifact, CatalogRecord, CatalogSnapshot, Dataset, Song
from .music import infer_keys, interpret, key_name, parse_chord, tokenize
from .retrieval import search


class CatalogSong(BaseModel):
    id: str
    song_id: str | None
    track_id: str
    title: str
    artist: str
    artwork: str | None
    genre: str | None
    year: int | None
    date_precision: str | None
    spotify_url: str
    metadata_status: str
    searchable: bool = False


class CatalogPage(BaseModel):
    items: list[CatalogSong]
    next_cursor: str | None


class PracticeChord(BaseModel):
    notes: list[int]
    status: str


class CatalogSection(BaseModel):
    label: str
    events: list[str]
    start: int
    end: int
    practice: list[PracticeChord]


class CatalogDetail(CatalogSong):
    sections: list[CatalogSection]
    variants: list[dict[str, str]]
    source_id: str
    source: str
    license: str
    snapshot_id: str | None
    metadata_source: str


def practice_chord(label):
    chord = parse_chord(label)
    notes = [60 + chord.root + interval for interval in chord.intervals] if chord.status == "known" else []
    if notes:
        notes = sorted(set([48 + (chord.bass if chord.bass is not None else chord.root), *notes]))
    return PracticeChord(notes=notes, status=chord.status)


class ConsumerSearchRequest(SearchRequest):
    mode: Literal["literal", "transposed", "functional", "fuzzy"] = "transposed"
    notation: Literal["chords", "roman"] = "chords"


class CatalogMatch(BaseModel):
    song: CatalogSong
    match: SearchResult
    score: float
    query_contributions: list[dict]
    variants: list[dict]


class CatalogSearchResponse(BaseModel):
    results: list[CatalogMatch]
    snapshot_id: str | None
    candidate_limit_reached: bool
    candidate_count: int
    query_interpretations: list[dict]
    timings: dict[str, float]


def active_snapshot(session, identifier=None):
    return (
        session.get(CatalogSnapshot, identifier)
        if identifier
        else session.scalar(select(CatalogSnapshot).where(CatalogSnapshot.active.is_(True)))
    )


def visible():
    return (
        CatalogRecord.metadata_status == "resolved",
        CatalogRecord.title.is_not(None),
        CatalogRecord.artist.is_not(None),
    )


def song_card(row, ready=False):
    return CatalogSong(
        id=row.id,
        song_id=row.song_id,
        track_id=row.track_id,
        title=row.title,
        artist=row.artist,
        artwork=row.artwork,
        genre=row.genre,
        year=row.year,
        date_precision=row.date_precision,
        spotify_url=f"https://open.spotify.com/track/{row.track_id}",
        metadata_status=row.metadata_status,
        searchable=ready,
    )


def ready_ids(session, rows, snapshot):
    if not snapshot or not rows:
        return set()
    return set(
        session.scalars(
            select(CatalogArtifact.record_id).where(
                CatalogArtifact.record_id.in_([r.id for r in rows]),
                CatalogArtifact.analysis_id == snapshot.analysis_id,
                CatalogArtifact.sequence <= snapshot.sequence,
            )
        )
    )


def browse(session, q="", genre=None, decade=None, cursor=None, limit=24, ready=False):
    statement = select(func.min(CatalogRecord.id).label("id")).where(*visible())
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        statement = statement.where(
            or_(
                CatalogRecord.title.ilike(f"%{escaped}%", escape="\\"),
                CatalogRecord.artist.ilike(f"%{escaped}%", escape="\\"),
            )
        )
    if genre:
        statement = statement.where(CatalogRecord.genre == genre)
    if decade is not None:
        statement = statement.where(CatalogRecord.year >= decade, CatalogRecord.year < decade + 10)
    snapshot = active_snapshot(session)
    if ready:
        if not snapshot:
            return CatalogPage(items=[], next_cursor=None)
        statement = statement.where(
            CatalogRecord.id.in_(
                select(CatalogArtifact.record_id).where(
                    CatalogArtifact.analysis_id == snapshot.analysis_id, CatalogArtifact.sequence <= snapshot.sequence
                )
            )
        )
    grouped = statement.group_by(CatalogRecord.track_id).subquery()
    query = select(CatalogRecord).join(grouped, grouped.c.id == CatalogRecord.id)
    if cursor:
        query = query.where(CatalogRecord.id > cursor)
    rows = list(session.scalars(query.order_by(CatalogRecord.id).limit(limit + 1)))
    available = ready_ids(session, rows, snapshot)
    return CatalogPage(
        items=[song_card(r, r.id in available) for r in rows[:limit]],
        next_cursor=rows[limit - 1].id if len(rows) > limit else None,
    )


def consumer_search(session, body):
    started = time.perf_counter()
    snapshot = active_snapshot(session, body.catalog_snapshot)
    if body.catalog_snapshot and not snapshot:
        raise HTTPException(404, "Search snapshot not found")
    if not snapshot:
        return CatalogSearchResponse(
            results=[],
            snapshot_id=None,
            candidate_limit_reached=False,
            candidate_count=0,
            query_interpretations=[],
            timings={"total_ms": 0},
        )
    requests = [(body.progression, 1.0, None)]
    if body.mode in {"functional", "fuzzy"} and body.notation == "chords" and body.pattern == "progression":
        chords = [parse_chord(t, strict=True) for t in tokenize(body.progression)]
        if not 1 <= len(chords) <= 32 or any(c.status != "known" for c in chords):
            raise ValueError("Enter 1–32 supported pitched chords")
        posterior, _ = infer_keys(chords, [0] * len(chords), [None] * len(chords), AnalysisConfig())
        weights = posterior.mean(axis=0)
        keys = np.argsort(weights)[::-1][:3]
        # Query hypotheses retain their original mass, reported below; active weights are normalized.
        requests = [
            (
                " ".join(
                    interpret(c, int(k), chords[i + 1] if i + 1 < len(chords) else None)[0]["roman"]
                    for i, c in enumerate(chords)
                ),
                float(weights[k] / weights[keys].sum()),
                key_name(int(k)),
            )
            for k in keys
        ]
    request_data = body.model_dump(exclude={"notation"})
    request_data.update(analysis_id=snapshot.analysis_id, catalog_snapshot=snapshot.id, limit=100)
    grouped, candidate_count, truncated = {}, 0, False
    candidate_ms, rerank_ms = 0.0, 0.0
    evidence_context = {}
    interpretations = []
    for progression, probability, key in requests:
        interpretations.append({"progression": progression, "weight": probability, "key": key})
        response = search(
            session,
            SearchRequest(**{**request_data, "progression": progression}),
            return_all=True,
            evidence_context=evidence_context,
        )
        candidate_count += response.candidate_count
        candidate_ms += response.timings["candidate_ms"]
        rerank_ms += response.timings["rerank_ms"]
        truncated |= response.candidate_limit_reached
        # Only the best passage per track contributes once for a query hypothesis.
        by_track = {}
        ids = {r.song_id for r in response.results}
        rows = {
            r.song_id: r
            for r in session.scalars(select(CatalogRecord).where(CatalogRecord.song_id.in_(ids), *visible()))
        }
        for match in response.results:
            row = rows.get(match.song_id)
            if not row:
                continue
            if row.track_id not in by_track:
                by_track[row.track_id] = (row, match)
            entry = grouped.setdefault(
                row.track_id,
                {"song": song_card(row, True), "match": match, "score": 0.0, "query_contributions": [], "variants": []},
            )
            if not any(v["record_id"] == row.id for v in entry["variants"]):
                entry["variants"].append({"record_id": row.id, "song_id": row.song_id, "source_id": row.source_id})
        for track, (row, match) in by_track.items():
            entry = grouped[track]
            entry["score"] += probability * match.score
            entry["query_contributions"].append(
                {
                    "progression": progression,
                    "weight": probability,
                    "passage_score": match.score,
                    "contribution": probability * match.score,
                    "passage_id": match.passage_id,
                }
            )
            if match.score > entry["match"].score:
                entry["match"], entry["song"] = match, song_card(row, True)
    results = sorted(grouped.values(), key=lambda r: (-r["score"], r["song"].id))[: body.limit]
    return CatalogSearchResponse(
        results=results,
        snapshot_id=snapshot.id,
        candidate_limit_reached=truncated,
        candidate_count=candidate_count,
        query_interpretations=interpretations,
        timings={
            "total_ms": (time.perf_counter() - started) * 1000,
            "candidate_ms": candidate_ms,
            "rerank_ms": rerank_ms,
        },
    )


def router(db):
    routes = APIRouter(prefix="/api/v1/catalog", tags=["Music discovery"])
    cached = {"at": 0.0, "value": None}

    @routes.get("/coverage")
    def coverage(session=Depends(db)):
        if time.monotonic() - cached["at"] < 15 and cached["value"]:
            return cached["value"]
        total, resolved, tracks, missing = session.execute(
            select(
                func.count(),
                func.sum(case((CatalogRecord.metadata_status == "resolved", 1), else_=0)),
                func.count(func.distinct(CatalogRecord.track_id)),
                func.sum(case((CatalogRecord.metadata_status.in_(["missing", "unavailable"]), 1), else_=0)),
            ).select_from(CatalogRecord)
        ).one()
        named = session.scalar(select(func.count(func.distinct(CatalogRecord.track_id))).where(*visible()))
        snapshot = active_snapshot(session)
        searchable = (
            session.scalar(
                select(func.count(func.distinct(CatalogRecord.track_id)))
                .join(CatalogArtifact, CatalogArtifact.record_id == CatalogRecord.id)
                .where(
                    *visible(),
                    CatalogArtifact.analysis_id == snapshot.analysis_id,
                    CatalogArtifact.sequence <= snapshot.sequence,
                )
            )
            if snapshot
            else 0
        )
        datasets = list(
            session.scalars(select(Dataset).where(Dataset.source == "chordonomicon", Dataset.synthetic.is_(False)))
        )
        genres = list(
            session.scalars(
                select(CatalogRecord.genre)
                .where(*visible(), CatalogRecord.genre.is_not(None))
                .distinct()
                .order_by(CatalogRecord.genre)
            )
        )
        value = {
            "imported_records": total,
            "resolved_records": resolved or 0,
            "identified_tracks": tracks,
            "named_songs": named,
            "searchable_songs": searchable,
            "unresolved_records": total - (resolved or 0),
            "unavailable_records": missing or 0,
            "snapshot_id": snapshot.id if snapshot else None,
            "import_complete": bool(datasets) and all(d.report.get("complete") for d in datasets),
            "genres": genres,
            "source": SOURCE,
            "license": "CC-BY-NC-4.0",
        }
        cached.update(at=time.monotonic(), value=value)
        return value

    @routes.get("/songs", response_model=CatalogPage)
    def songs(
        q: str = "",
        genre: str | None = None,
        decade: int | None = None,
        cursor: str | None = None,
        limit: int = Query(24, ge=1, le=100),
        ready: bool = False,
        session=Depends(db),
    ):
        return browse(session, q, genre, decade, cursor, limit, ready)

    @routes.get("/collections")
    def collections(session=Depends(db)):
        groups = [
            {
                "id": "ready",
                "title": "Find your next chord connection",
                "subtitle": "Real songs, ready to explore",
                "songs": browse(session, limit=8, ready=True).items,
            }
        ]
        genres = list(
            session.scalars(
                select(CatalogRecord.genre)
                .where(*visible(), CatalogRecord.genre.is_not(None))
                .group_by(CatalogRecord.genre)
                .order_by(func.count().desc())
                .limit(3)
            )
        )
        for genre in genres:
            groups.append(
                {
                    "id": genre,
                    "title": f"A little more {genre}",
                    "subtitle": "Explore the catalog",
                    "genre": genre,
                    "songs": browse(session, genre=genre, limit=8).items,
                }
            )
        decade_value = (func.floor(CatalogRecord.year / 10) * 10).label("decade")
        decades = list(
            session.scalars(
                select(decade_value)
                .where(*visible(), CatalogRecord.year.is_not(None))
                .group_by(decade_value)
                .order_by(func.count().desc())
                .limit(1)
            )
        )
        for decade in decades:
            groups.append(
                {
                    "id": str(decade),
                    "title": f"Back to the {int(decade)}s",
                    "subtitle": "A different decade. A new connection.",
                    "decade": int(decade),
                    "songs": browse(session, decade=int(decade), limit=8).items,
                }
            )
        return groups

    @routes.get("/songs/{identifier}", response_model=CatalogDetail)
    def detail(identifier: str, snapshot_id: str | None = None, session=Depends(db)):
        row = session.scalar(select(CatalogRecord).where(CatalogRecord.id == identifier, *visible()))
        if not row or (row.song_id and session.get(Song, row.song_id).synthetic):
            raise HTTPException(404, "Song not available in the music catalog")
        snapshot = active_snapshot(session, snapshot_id)
        ready = bool(ready_ids(session, [row], snapshot))
        variants = list(
            session.scalars(
                select(CatalogRecord)
                .where(CatalogRecord.track_id == row.track_id, *visible())
                .order_by(CatalogRecord.id)
            )
        )
        sections = sections_from_row(row.raw)
        position = 0
        for section in sections:
            section["start"] = position
            position += len(section["events"])
            section["end"] = position - 1
            section["practice"] = [practice_chord(label) for label in section["events"]]
        return {
            **song_card(row, ready).model_dump(),
            "sections": sections,
            "variants": [{"id": v.id, "source_id": v.source_id} for v in variants],
            "source_id": row.source_id,
            "source": SOURCE,
            "license": "CC-BY-NC-4.0",
            "snapshot_id": snapshot.id if snapshot and ready else None,
            "metadata_source": "Spotify oEmbed; linked by the publisher's Spotify identifiers",
        }

    @routes.post("/search", response_model=CatalogSearchResponse)
    def find(body: ConsumerSearchRequest, session=Depends(db)):
        return consumer_search(session, body)

    return routes
