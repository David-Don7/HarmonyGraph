from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from sqlalchemy import select
from .contracts import SongInput, fingerprint
from .db import Artist, ChordDefinition, ChordEvent, Dataset, Genre, Section, Song, SongGenre, SourceAnnotation
from .music import parse_chord


def section_kind(label):
    text = label.lower().replace("_", " ")
    for kind in ["pre-chorus", "chorus", "verse", "bridge", "intro", "outro", "solo", "instrumental"]:
        if kind in text:
            return kind
    return "unknown"


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_records(path):
    with Path(path).open(encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            if line.strip():
                try:
                    yield line_number, json.loads(line), None
                except ValueError as error:
                    yield line_number, None, str(error)


def chordonomicon_records(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not {"id", "chords"}.issubset(reader.fieldnames or []):
            raise ValueError("Chordonomicon CSV requires id and chords columns")
        for number, row in enumerate(reader, 2):
            sections = []
            for token in re.findall(r"<[^>]+>|\S+", row.get("chords", "")):
                if token.startswith("<"):
                    sections.append({"label": token[1:-1], "events": []})
                else:
                    if not sections:
                        sections.append({"label": "unknown", "events": []})
                    sections[-1]["events"].append({"label": token})
            genres = re.findall(r"'([^']+)'", row.get("genres", ""))
            if not genres:
                genres = [row[key] for key in ("main_genre", "genre") if row.get(key)]
            year = row.get("release_year") or row.get("decade")
            try:
                yield (
                    number,
                    {
                        "source_id": row["id"],
                        "title": row.get("title") or None,
                        "artist": row.get("artist_id") or row.get("artist"),
                        "genres": list(dict.fromkeys(genres)),
                        "year": int(float(year)) if year and year.lower() != "nan" else None,
                        "sections": [s for s in sections if s["events"]],
                        "annotations": {"source_row": row},
                    },
                    None,
                )
            except ValueError as error:
                yield number, None, str(error)


def billboard_song(path, metadata):
    annotations = {
        "headers": {},
        "tonic_changes": [],
        "timing_note": "Bar timing interpolated within annotated phrases",
    }
    lines = []
    with path.open(encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if line.startswith("#"):
                if ":" in line:
                    key, value = line[1:].split(":", 1)
                    key, value = key.strip(), value.strip()
                    if key == "tonic":
                        annotations["tonic_changes"].append({"before_phrase": len(lines), "value": value})
                    annotations["headers"].setdefault(key, value)
                    if key == "metre":
                        annotations["current_metre"] = value
                continue
            m = re.match(r"^(\d+(?:\.\d+)?)\s+(.*)", line)
            if m:
                lines.append((float(m[1]), m[2], annotations.get("current_metre", "4/4")))
    sections = []
    last = None
    for index, (start, body, metre) in enumerate(lines):
        stop = lines[index + 1][0] if index + 1 < len(lines) else None
        if "|" not in body:
            continue
        prefix, *bars = body.split("|")
        label_match = re.search(r"(?:^|,)\s*(verse|chorus|bridge|intro|outro|solo|pre-chorus)[^,]*", prefix, re.I)
        label = label_match[0].lstrip(", ") if label_match else prefix.strip(", ") or "unknown"
        repetition = re.search(r"x\s*(\d+)\s*(?:->)?\s*$", bars[-1]) if bars else None
        repeats = int(repetition[1]) if repetition else 1
        bars = [bar for bar in bars if bar.strip() and not re.fullmatch(r"\s*(?:x\s*\d+)?\s*(?:->)?\s*", bar)]
        parsed = []
        for bar in bars:
            mm = re.search(r"\((\d+/\d+)\)", bar)
            beats = int((mm[1] if mm else metre).split("/")[0])
            bar = re.sub(r"\([^)]*\)", "", bar)
            tokens = [t for t in bar.split() if t not in {"->"}]
            tokens = [t for t in tokens if not re.fullmatch(r"x\d+", t)]
            if not tokens:
                continue
            for token in tokens:
                label_chord = last if token == "." else token
                label_chord = label_chord or "X"
                parsed.append((label_chord, beats / len(tokens)))
                last = label_chord
        parsed *= repeats
        total = sum(d for _, d in parsed)
        cursor = start
        events = []
        for label_chord, beats in parsed:
            seconds = (stop - start) * beats / total if stop is not None and total else None
            events.append(
                {
                    "label": label_chord,
                    "onset": cursor if seconds is not None else None,
                    "duration": seconds if seconds is not None else beats,
                    "timing_unit": "seconds" if seconds is not None else "beats",
                }
            )
            cursor += seconds or 0
        if events:
            sections.append({"label": label, "events": events})
    return {
        "source_id": path.parent.name,
        "title": metadata.get("title") or annotations["headers"].get("title"),
        "artist": metadata.get("artist") or annotations["headers"].get("artist"),
        "sections": sections,
        "annotations": annotations,
    }


def billboard_records(path):
    root = Path(path)
    metadata = {}
    for index in root.glob("*index.csv"):
        with index.open(encoding="utf-8-sig") as handle:
            metadata = {r["id"].zfill(4): r for r in csv.DictReader(handle)}
    for number, song_path in enumerate(sorted(root.rglob("salami_chords.txt")), 1):
        try:
            yield number, billboard_song(song_path, metadata.get(song_path.parent.name.zfill(4), {})), None
        except (ValueError, IndexError) as error:
            yield number, None, f"{song_path.name}: {error}"


def lab(path):
    records = []
    with path.open(encoding="utf-8-sig") as handle:
        for line in handle:
            if line.strip() and not line.startswith("#"):
                onset, end, label = line.strip().split(maxsplit=2)
                start, stop = float(onset), float(end)
                if stop < start:
                    raise ValueError("Annotation offset precedes onset")
                records.append((start, stop, label))
    return records


def isophonics_records(path):
    """JSON manifest entries specify chord/key/section lab paths relative to the manifest."""
    path = Path(path)
    manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    for number, item in enumerate(manifest["songs"], 1):
        try:

            def resolve(name):
                resolved = (path.parent / item[name]).resolve()
                if not resolved.is_relative_to(path.parent.resolve()):
                    raise ValueError("Manifest paths must stay inside the dataset directory")
                return resolved

            chords = lab(resolve("chords"))
            structures = lab(resolve("sections")) if item.get("sections") else []
            keys = lab(resolve("keys")) if item.get("keys") else []
            groups = []
            previous = None
            for onset, end, label in chords:
                section_index = next((i for i, (a, b, _) in enumerate(structures) if a <= onset < b), -1)
                if previous != section_index:
                    groups.append(
                        {"label": structures[section_index][2] if section_index >= 0 else "unknown", "events": []}
                    )
                    previous = section_index
                groups[-1]["events"].append(
                    {"label": label, "onset": onset, "duration": end - onset, "timing_unit": "seconds"}
                )
            yield (
                number,
                {
                    "source_id": item["id"],
                    "title": item.get("title"),
                    "artist": item.get("artist"),
                    "sections": groups,
                    "annotations": {"keys": keys, "sections": structures},
                },
                None,
            )
        except (KeyError, ValueError, OSError) as error:
            yield number, None, str(error)


READERS = {
    "jsonl": canonical_records,
    "chordonomicon": chordonomicon_records,
    "billboard": billboard_records,
    "isophonics": isophonics_records,
}


def source_fingerprint(path, source):
    path = Path(path)
    if source == "billboard":
        return fingerprint([(str(p.relative_to(path)), file_hash(p)) for p in sorted(path.rglob("*")) if p.is_file()])
    if source == "isophonics":
        manifest = json.loads(path.read_text(encoding="utf-8-sig"))
        inputs = [path]
        for song in manifest["songs"]:
            for kind in ("chords", "keys", "sections"):
                if song.get(kind):
                    target = (path.parent / song[kind]).resolve()
                    if not target.is_relative_to(path.parent.resolve()):
                        raise ValueError("Manifest path outside dataset")
                    inputs.append(target)
        return fingerprint([(p.name, file_hash(p)) for p in inputs])
    return file_hash(path)


def ingest(session, path, source="jsonl", name=None, license="unspecified", progress=lambda p: None):
    if source not in READERS:
        raise ValueError(f"Unknown adapter {source}")
    digest = fingerprint({"content": source_fingerprint(path, source), "adapter": source, "version": 1})
    dataset = session.scalar(select(Dataset).where(Dataset.fingerprint == digest))
    if dataset is None:
        dataset = Dataset(id=digest, name=name or Path(path).stem, fingerprint=digest, source=source, license=license)
        session.add(dataset)
        session.commit()
    report = {"imported": 0, "skipped": 0, "invalid": 0, "unknown_chords": 0, "errors": []}
    for number, record, error in READERS[source](path):
        try:
            if error:
                raise ValueError(error)
            song = SongInput.model_validate(record)
            if session.scalar(select(Song.id).where(Song.dataset_id == dataset.id, Song.source_id == song.source_id)):
                report["skipped"] += 1
                continue
            with session.begin_nested():
                artist = None
                if song.artist:
                    artist = session.scalar(select(Artist).where(Artist.name == song.artist))
                    if artist is None:
                        artist = Artist(name=song.artist)
                        session.add(artist)
                        session.flush()
                row = Song(
                    id=fingerprint([digest, song.source_id]),
                    dataset_id=dataset.id,
                    source_id=song.source_id,
                    title=song.title,
                    artist_id=artist.id if artist else None,
                    year=song.year,
                    duplicate_group=song.duplicate_group,
                    content_hash=fingerprint([[parse_chord(e.label).token for e in s.events] for s in song.sections]),
                    synthetic=song.synthetic,
                )
                session.add(row)
                session.flush()
                for genre_name in set(song.genres):
                    genre = session.scalar(select(Genre).where(Genre.name == genre_name))
                    if genre is None:
                        genre = Genre(name=genre_name)
                        session.add(genre)
                        session.flush()
                    session.add(SongGenre(song_id=row.id, genre_id=genre.id))
                ordinal = 0
                for index, section in enumerate(song.sections):
                    stored = Section(
                        song_id=row.id,
                        ordinal=index,
                        label=section.label,
                        kind=section_kind(section.label),
                        start=ordinal,
                        end=ordinal + len(section.events) - 1,
                    )
                    session.add(stored)
                    session.flush()
                    for event in section.events:
                        chord = parse_chord(event.label)
                        report["unknown_chords"] += chord.status == "unknown"
                        chord_id = fingerprint(chord.data())
                        if session.get(ChordDefinition, chord_id) is None:
                            session.add(ChordDefinition(id=chord_id, canonical=chord.data()))
                            session.flush()
                        session.add(
                            ChordEvent(
                                song_id=row.id,
                                section_id=stored.id,
                                chord_id=chord_id,
                                ordinal=ordinal,
                                label=event.label,
                                onset=event.onset,
                                duration=event.duration,
                                timing_unit=event.timing_unit,
                            )
                        )
                        ordinal += 1
                session.add(
                    SourceAnnotation(
                        song_id=row.id,
                        data={"annotations": song.annotations, "original": song.model_dump(), "source_line": number},
                    )
                )
                if song.synthetic:
                    dataset.synthetic = True
            report["imported"] += 1
        except (ValueError, TypeError) as exc:
            report["invalid"] += 1
            if len(report["errors"]) < 100:
                report["errors"].append({"line": number, "error": str(exc)})
        if number % 50 == 0:
            dataset.report = report.copy()
            session.commit()
            progress(min(0.8, number / (number + 100)))
    dataset.report = report
    session.commit()
    progress(1)
    return {"dataset_id": dataset.id, **report}
