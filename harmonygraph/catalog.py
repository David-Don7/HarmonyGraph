"""Streaming publisher catalog and incremental, immutable search publication."""

from __future__ import annotations

import csv
import json
import os
import re
import ssl
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from functools import lru_cache
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import case, func, or_, select, update

from .contracts import AnalysisConfig, fingerprint
from .db import (
    AnalysisRun,
    Artist,
    CatalogArtifact,
    CatalogRecord,
    CatalogSnapshot,
    ChordDefinition,
    ChordEvent,
    Dataset,
    Genre,
    Job,
    ProviderMetadata,
    Section,
    Song,
    SongGenre,
    SourceAnnotation,
    now,
    uid,
)
from .ingestion import file_hash, section_kind
from .music import parse_chord

REVISION = "f3a8b678bd65639c01caa342921733f1db01be23"
SOURCE = "https://huggingface.co/datasets/ailsntua/Chordonomicon"
DOWNLOAD = f"{SOURCE}/resolve/{REVISION}/chordonomicon_v2.csv"
EXPECTED = 679807
EXPECTED_SHA256 = "9d2f4ccdc876a4e816712f128e4772b2af558c2a2923cce5be3a0364fbad9a8d"
_provider_lock = threading.Lock()
_next_provider_request = 0.0


def tls_context():
    return _tls_context(os.environ.get("HARMONY_CA_FILE"))


@lru_cache(maxsize=4)
def _tls_context(extra):
    context = ssl.create_default_context()
    if extra and Path(extra).is_file():
        context.load_verify_locations(extra)
    return context


def enqueue(session, kind, parameters=None):
    # A transaction-level advisory lock prevents duplicate local pipelines.
    if session.bind.dialect.name == "postgresql":
        from sqlalchemy import text

        session.execute(text("SELECT pg_advisory_xact_lock(8841901)"))
    existing = session.scalar(select(Job).where(Job.kind == kind, Job.status.in_(["queued", "running"])))
    if existing:
        return existing
    job = Job(kind=kind, parameters=parameters or {})
    session.add(job)
    session.flush()
    return job


def download(session, parameters, progress):
    root = Path(os.environ.get("DATA_ROOT", "data")) / "chordonomicon"
    root.mkdir(parents=True, exist_ok=True)
    path, partial = root / "chordonomicon_v2.csv", root / "chordonomicon_v2.csv.part"
    if not path.exists():
        offset = partial.stat().st_size if partial.exists() else 0
        request = urllib.request.Request(DOWNLOAD, headers={"Range": f"bytes={offset}-"} if offset else {})
        with urllib.request.urlopen(request, timeout=60, context=tls_context()) as response:
            append = offset > 0 and response.status == 206
            if not append:
                offset = 0
            total = offset + int(response.headers.get("Content-Length", 0))
            with partial.open("ab" if append else "wb") as target:
                while chunk := response.read(1024 * 1024):
                    target.write(chunk)
                    offset += len(chunk)
                    progress(min(0.99, offset / total) if total else 0.1)
        partial.replace(path)
    checksum = file_hash(path)
    if checksum != EXPECTED_SHA256:
        raise ValueError("The downloaded release does not match the publisher's pinned SHA-256 checksum")
    manifest = {"revision": REVISION, "source": SOURCE, "sha256": checksum, "bytes": path.stat().st_size}
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    enqueue(session, "catalog_import", {"path": "chordonomicon/chordonomicon_v2.csv", **manifest})
    session.commit()
    return manifest


def clean(value):
    return value.strip() if value and value.strip().lower() not in {"nan", "none", "null"} else None


def release_date(row):
    value = clean(row.get("release_date")) or clean(row.get("release_year"))
    if not value or not re.match(r"^\d{4}(?:-|$)", value):
        return None, None
    return int(value[:4]), "day" if len(value) >= 10 else "month" if len(value) >= 7 else "year"


def sections_from_row(row):
    sections = []
    for token in re.findall(r"<[^>]+>|\S+", row.get("chords", "")):
        if token.startswith("<"):
            sections.append({"label": token[1:-1], "events": []})
        else:
            if not sections:
                sections.append({"label": "unknown", "events": []})
            sections[-1]["events"].append(token)
    return [s for s in sections if s["events"]]


def import_catalog(session, path, parameters, progress):
    started = time.perf_counter()
    checksum = file_hash(path)
    if parameters.get("sha256") and checksum != parameters["sha256"]:
        raise ValueError("Downloaded CSV checksum differs from its manifest")
    dataset_id = fingerprint({"sha256": checksum, "revision": REVISION, "adapter": "catalog-v2"})
    dataset = session.get(Dataset, dataset_id)
    if not dataset:
        dataset = Dataset(
            id=dataset_id,
            name="Chordonomicon v2",
            fingerprint=dataset_id,
            source="chordonomicon",
            license="CC-BY-NC-4.0",
            synthetic=False,
            report={
                "checkpoint": 0,
                "invalid": 0,
                "errors": [],
                "sha256": checksum,
                "revision": REVISION,
                "source": SOURCE,
                "expected_records": EXPECTED,
            },
        )
        session.add(dataset)
        session.commit()
    report = dict(dataset.report)
    checkpoint = report.get("checkpoint", 0)
    batch = []
    seen = set()

    def flush(number):
        if batch:
            dialect = session.bind.dialect.name
            if dialect == "postgresql":
                from sqlalchemy.dialects.postgresql import insert
            else:
                from sqlalchemy.dialects.sqlite import insert
            session.execute(insert(CatalogRecord).on_conflict_do_nothing(), batch)
            batch.clear()
            seen.clear()
        report["checkpoint"] = number
        report["seconds_this_attempt"] = round(time.perf_counter() - started, 3)
        dataset.report = dict(report)
        session.commit()
        progress(min(0.99, number / EXPECTED))

    number = 0
    with Path(path).open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not {"id", "chords"}.issubset(reader.fieldnames or []):
            raise ValueError("CSV requires id and chords columns")
        for number, row in enumerate(reader, 1):
            if number <= checkpoint:
                continue
            if not row.get("id") or not row.get("chords") or None in row:
                report["invalid"] += 1
                if len(report["errors"]) < 100:
                    report["errors"].append({"line": number + 1, "error": "Missing id/chords or malformed CSV row"})
                continue
            identifier = fingerprint([dataset_id, row["id"]])
            if identifier not in seen:
                year, precision = release_date(row)
                track, artist = clean(row.get("spotify_song_id")), clean(row.get("spotify_artist_id"))
                batch.append(
                    {
                        "id": identifier,
                        "dataset_id": dataset_id,
                        "source_id": row["id"],
                        "raw": row,
                        "track_id": track,
                        "spotify_artist_id": artist,
                        "year": year,
                        "date_precision": precision,
                        "genre": clean(row.get("main_genre")),
                        "metadata_status": "pending" if track and artist else "missing",
                    }
                )
                seen.add(identifier)
            if number % 1000 == 0:
                flush(number)
    flush(number)
    report.update(
        {
            "complete": True,
            "source_records": number,
            "imported": session.scalar(
                select(func.count()).select_from(CatalogRecord).where(CatalogRecord.dataset_id == dataset_id)
            ),
        }
    )
    dataset.report = report
    enqueue(session, "catalog_metadata")
    enqueue(session, "catalog_analyze")
    session.commit()
    return {"dataset_id": dataset_id, **report}


def provider_metadata(session, kind, identifier, progress):
    global _next_provider_request
    cooldown = session.get(ProviderMetadata, "spotify:cooldown")
    if cooldown and cooldown.retry_at and cooldown.retry_at > now():
        return cooldown
    key = f"spotify:{kind}:{identifier}"
    cached = session.get(ProviderMetadata, key)
    if cached and (cached.status in {"resolved", "unavailable"} or (cached.retry_at and cached.retry_at > now())):
        return cached
    if not re.fullmatch(r"[A-Za-z0-9]{22}", identifier or ""):
        payload, status, retry_at = {"error": "Invalid provider identifier"}, "unavailable", None
    else:
        with _provider_lock:
            time.sleep(max(0.0, _next_provider_request - time.monotonic()))
            _next_provider_request = time.monotonic() + float(os.environ.get("METADATA_REQUEST_INTERVAL", ".25"))
        progress(0)  # cancellation/lease check, even while a provider is failing
        url = "https://open.spotify.com/oembed?" + urllib.parse.urlencode(
            {"url": f"https://open.spotify.com/{kind}/{identifier}"}
        )
        try:
            with urllib.request.urlopen(url, timeout=10, context=tls_context()) as response:
                payload = json.load(response)
            status, retry_at = ("resolved" if payload.get("title") else "unavailable"), None
            payload["source_url"] = url
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            code = getattr(error, "code", None)
            status = "unavailable" if code in (400, 404) else "retry"
            delay = 300
            if code == 429:
                try:
                    delay = max(60, int(error.headers.get("Retry-After", "300")))
                except ValueError:
                    pass
            retry_at = (
                (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat() if status == "retry" else None
            )
            payload = {"error": str(error), "source_url": url, "http_status": code}
            if code == 429:
                if session.bind.dialect.name == "postgresql":
                    from sqlalchemy.dialects.postgresql import insert
                else:
                    from sqlalchemy.dialects.sqlite import insert
                values = {
                    "id": "spotify:cooldown",
                    "status": "retry",
                    "payload": payload,
                    "retry_at": retry_at,
                    "fetched_at": now(),
                }
                session.execute(
                    insert(ProviderMetadata).values(**values).on_conflict_do_update(index_elements=["id"], set_=values)
                )
    if cached is None:
        cached = ProviderMetadata(id=key)
        session.add(cached)
    cached.status, cached.payload, cached.retry_at, cached.fetched_at = status, payload, retry_at, now()
    session.commit()
    return cached


def resolve_metadata(session, parameters, progress):
    completed = 0
    delayed = select(ProviderMetadata.id).where(ProviderMetadata.status == "retry", ProviderMetadata.retry_at > now())
    # Row-number ranks interleave genres/decades rather than exhausting the first genre.
    ranked = (
        select(
            CatalogRecord.id,
            func.row_number()
            .over(
                partition_by=(CatalogRecord.genre, func.floor(CatalogRecord.year / 10)),
                order_by=CatalogRecord.source_id,
            )
            .label("rank"),
        )
        .where(
            CatalogRecord.metadata_status == "pending",
            ("spotify:track:" + CatalogRecord.track_id).not_in(delayed),
            ("spotify:artist:" + CatalogRecord.spotify_artist_id).not_in(delayed),
        )
        .subquery()
    )
    ids = list(session.scalars(select(ranked.c.id).order_by(ranked.c.rank, ranked.c.id).limit(250)))
    from .db import factory

    records = [
        (r.id, r.track_id, r.spotify_artist_id)
        for r in session.scalars(select(CatalogRecord).where(CatalogRecord.id.in_(ids)))
    ]
    keys = list(dict.fromkeys(key for _, track, artist in records for key in [("track", track), ("artist", artist)]))
    results, finished = {}, set()
    sessions = factory(session.bind)

    def fetch(key):
        with sessions() as provider_session:
            value = provider_metadata(provider_session, *key, lambda _: progress(completed / max(len(ids), 1)))
            return key, (value.status, value.payload)

    # Consume cached identities in one read. Cached artists should not occupy
    # network slots or cause repeated per-identity round trips.
    cached = {
        p.id: p
        for p in session.scalars(
            select(ProviderMetadata).where(
                ProviderMetadata.id.in_([f"spotify:{kind}:{identifier}" for kind, identifier in keys]),
                ProviderMetadata.status.in_(["resolved", "unavailable"]),
            )
        )
    }
    for key in keys:
        value = cached.get(f"spotify:{key[0]}:{key[1]}")
        if value:
            results[key] = (value.status, value.payload)

    def apply_ready():
        nonlocal completed
        for identifier, track_id, artist_id in records:
            if identifier in finished or ("track", track_id) not in results or ("artist", artist_id) not in results:
                continue
            (track_status, track), (artist_status, artist) = (
                results["track", track_id],
                results["artist", artist_id],
            )
            if "retry" in {track_status, artist_status}:
                continue
            if track_status == artist_status == "resolved":
                session.execute(
                    update(CatalogRecord)
                    .where(CatalogRecord.track_id == track_id, CatalogRecord.spotify_artist_id == artist_id)
                    .values(
                        title=track["title"],
                        artist=artist["title"],
                        artwork=track.get("thumbnail_url"),
                        metadata_status="resolved",
                    )
                )
            else:
                session.execute(
                    update(CatalogRecord)
                    .where(CatalogRecord.id == identifier)
                    .values(metadata_status="unavailable", error="Spotify metadata unavailable")
                )
            finished.add(identifier)
            completed += 1
        session.commit()
        progress(completed / max(len(ids), 1))

    apply_ready()
    # Four continuously replenished slots avoid a slow response stalling the
    # other three. Request spacing and shared Retry-After cooldown still apply.
    remaining = iter(key for key in keys if key not in results)
    with ThreadPoolExecutor(max_workers=4) as pool:
        active = {pool.submit(fetch, key) for key in [next(remaining, None) for _ in range(4)] if key}
        throttled = False
        while active:
            done, active = wait(active, return_when=FIRST_COMPLETED)
            for future in done:
                key, value = future.result()
                results[key] = value
                throttled |= value[1].get("http_status") == 429
            apply_ready()
            if not throttled:
                for _ in done:
                    key = next(remaining, None)
                    if key:
                        active.add(pool.submit(fetch, key))
    pending = session.scalar(select(CatalogRecord.id).where(CatalogRecord.metadata_status == "pending").limit(1))
    return {"resolved_this_batch": completed, "continue": bool(pending)}


def materialize(session, row):
    if row.song_id:
        return row.song_id
    sections = sections_from_row(row.raw)
    if not sections:
        raise ValueError("No chord events in publisher record")
    artist_id = None
    if row.artist:
        artist = session.scalar(select(Artist).where(Artist.name == row.artist))
        if not artist:
            artist = Artist(id=uid(), name=row.artist)
            session.add(artist)
            session.flush()
        artist_id = artist.id
    song = Song(
        id=row.id,
        dataset_id=row.dataset_id,
        source_id=row.source_id,
        title=row.title,
        artist_id=artist_id,
        year=row.year,
        duplicate_group=row.track_id or row.id,
        content_hash=fingerprint(row.raw["chords"]),
        synthetic=False,
    )
    session.add(song)
    session.flush()
    definitions, events, section_rows = {}, [], []
    ordinal = 0
    for index, section in enumerate(sections):
        section_id = fingerprint([row.id, index])
        section_rows.append(
            {
                "id": section_id,
                "song_id": song.id,
                "ordinal": index,
                "label": section["label"],
                "kind": section_kind(section["label"]),
                "start": ordinal,
                "end": ordinal + len(section["events"]) - 1,
            }
        )
        for label in section["events"]:
            chord = parse_chord(label)
            chord_id = fingerprint(chord.data())
            definitions[chord_id] = {"id": chord_id, "canonical": chord.data()}
            events.append(
                {
                    "id": fingerprint([song.id, ordinal]),
                    "song_id": song.id,
                    "section_id": section_id,
                    "chord_id": chord_id,
                    "ordinal": ordinal,
                    "label": label,
                    "timing_unit": "unknown",
                }
            )
            ordinal += 1
    if session.bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    session.execute(insert(ChordDefinition).on_conflict_do_nothing(), list(definitions.values()))
    session.execute(Section.__table__.insert(), section_rows)
    session.execute(ChordEvent.__table__.insert(), events)
    genres = re.findall(r"'([^']+)'", row.raw.get("genres", "")) or ([row.genre] if row.genre else [])
    for name in set(genres + ([row.genre] if row.genre else [])):
        genre = session.scalar(select(Genre).where(Genre.name == name))
        if not genre:
            genre = Genre(id=uid(), name=name)
            session.add(genre)
            session.flush()
        session.add(SongGenre(song_id=song.id, genre_id=genre.id))
    session.add(
        SourceAnnotation(
            song_id=song.id,
            data={
                "source_row": row.raw,
                "revision": REVISION,
                "metadata_provider": "Spotify oEmbed",
                "chart_source": SOURCE,
            },
        )
    )
    row.song_id = song.id
    session.flush()
    return song.id


def analyze_batch(session, parameters, progress):
    from .analysis import process_song, save_config

    if session.bind.dialect.name == "postgresql":
        from sqlalchemy import text

        budget = float(os.environ.get("CATALOG_DATABASE_BUDGET_GB", "20"))
        used = session.scalar(text("SELECT pg_database_size(current_database())"))
        if budget > 0 and used >= budget * 1024**3:
            raise ValueError(
                f"Database reached the configured {budget:g} GiB processing budget. Free or move storage, increase CATALOG_DATABASE_BUDGET_GB, and resume catalog index. Published songs remain available."
            )
    config = AnalysisConfig(**parameters.get("config", {}))
    config_id = save_config(session, config, "Real catalog")
    dataset_ids = list(
        session.scalars(select(Dataset.id).where(Dataset.source == "chordonomicon", Dataset.synthetic.is_(False)))
    )
    digest = fingerprint({"datasets": sorted(dataset_ids), "configuration": config_id, "catalog": 2})
    run = session.scalar(select(AnalysisRun).where(AnalysisRun.corpus_hash == digest))
    if not run:
        run = AnalysisRun(
            configuration_id=config_id,
            corpus_hash=digest,
            status="ready",
            active=False,
            report={"catalog": True, "publication": "immutable snapshot watermarks"},
        )
        session.add(run)
        session.commit()
    analyzed = select(CatalogArtifact.record_id).where(CatalogArtifact.configuration_id == config_id)
    pending = session.scalar(select(CatalogRecord.id).where(CatalogRecord.metadata_status == "pending").limit(1))
    eligible = select(CatalogRecord).where(
        CatalogRecord.dataset_id.in_(dataset_ids),
        CatalogRecord.id.not_in(analyzed),
        or_(CatalogRecord.error.is_(None), CatalogRecord.error == "Spotify metadata unavailable"),
    )
    if pending:
        eligible = eligible.where(CatalogRecord.metadata_status == "resolved")
    rows = list(
        session.scalars(
            eligible.order_by(case((CatalogRecord.metadata_status == "resolved", 0), else_=1), CatalogRecord.id).limit(
                20
            )
        )
    )
    previous = session.scalar(
        select(CatalogSnapshot).where(CatalogSnapshot.analysis_id == run.id).order_by(CatalogSnapshot.sequence.desc())
    )
    sequence = (
        session.scalar(select(func.max(CatalogArtifact.sequence)).where(CatalogArtifact.analysis_id == run.id)) or 0
    )
    successful = 0
    started = time.perf_counter()
    for row in rows:
        try:
            with session.begin_nested():
                song_id = materialize(session, row)
                process_song(session, song_id, run.id, config)
                sequence += 1
                session.add(
                    CatalogArtifact(
                        record_id=row.id,
                        configuration_id=config_id,
                        analysis_id=run.id,
                        content_hash=fingerprint(row.raw["chords"]),
                        sequence=sequence,
                    )
                )
            session.commit()
            successful += 1
        except (ValueError, IndexError) as error:
            session.rollback()
            sequence = (
                session.scalar(select(func.max(CatalogArtifact.sequence)).where(CatalogArtifact.analysis_id == run.id))
                or 0
            )
            row = session.get(CatalogRecord, row.id)
            row.error = str(error)
            session.commit()
        progress(successful / max(len(rows), 1))
    # Include committed artifacts from an interrupted attempt as well.
    sequence = (
        session.scalar(select(func.max(CatalogArtifact.sequence)).where(CatalogArtifact.analysis_id == run.id)) or 0
    )
    if sequence > (previous.sequence if previous else 0):
        snapshot_id = fingerprint([run.id, sequence])
        session.execute(update(CatalogSnapshot).values(active=False))
        session.add(CatalogSnapshot(id=snapshot_id, analysis_id=run.id, sequence=sequence, songs=sequence, active=True))
        session.commit()
    return {
        "indexed_this_batch": successful,
        "indexed": sequence,
        "seconds": time.perf_counter() - started,
        "continue": bool(rows)
        or bool(session.scalar(select(CatalogRecord.id).where(CatalogRecord.metadata_status == "pending").limit(1))),
    }


def dispatch_catalog(session, kind, parameters, progress):
    if kind == "catalog_download":
        return download(session, parameters, progress)
    if kind == "catalog_import":
        from .jobs import input_path

        return import_catalog(session, input_path(parameters["path"]), parameters, progress)
    if kind == "catalog_metadata":
        return resolve_metadata(session, parameters, progress)
    if kind == "catalog_analyze":
        return analyze_batch(session, parameters, progress)
    raise ValueError("Unknown catalog job")
