"""Reproducible bounded audit of the already-downloaded publisher CSV, offline.

Run from the repository root with the project's Python. Leaves the public catalog
untouched. Titles are unavailable unless supplied by the source; none are invented.
"""
import csv
import json
from pathlib import Path

from sqlalchemy import select

from harmonygraph.analysis import analyze
from harmonygraph.catalog import EXPECTED_SHA256, REVISION
from harmonygraph.db import Base, Song, factory, make_engine
from harmonygraph.ingestion import file_hash, ingest
from harmonygraph.research_v2 import bounded_audit, export_packet


def main():
    source = Path("data/chordonomicon/chordonomicon_v2.csv")
    if file_hash(source) != EXPECTED_SHA256:
        raise ValueError("Publisher CSV checksum differs from the pinned release")
    root = Path("artifacts/research-v2/local-audit")
    root.mkdir(parents=True, exist_ok=True)
    sample = root / "source-sample.csv"
    with source.open(encoding="utf-8-sig", newline="") as handle, sample.open("w", encoding="utf-8", newline="") as out:
        reader = csv.DictReader(handle)
        writer = csv.DictWriter(out, fieldnames=reader.fieldnames)
        writer.writeheader()
        selected = 0
        for row in reader:
            event_count = len([t for t in row["chords"].split() if not t.startswith("<")])
            if 6 <= event_count <= 80:
                writer.writerow(row)
                selected += 1
                if selected == 8:
                    break
    engine = make_engine(f"sqlite:///{(root / 'audit.db').as_posix()}")
    Base.metadata.create_all(engine)
    with factory(engine)() as session:
        imported = ingest(session, sample, source="chordonomicon", name=f"Chordonomicon {REVISION}: first 8 charts with 6–80 events", license="CC-BY-NC-4.0")
        ids = list(session.scalars(select(Song.id).order_by(Song.source_id)))
        analysis_id = analyze(session, song_ids=ids)
        audit, packet = bounded_audit(session, ids, analysis_id=analysis_id)
        audit["publisher_release"] = {"revision": REVISION, "sha256": EXPECTED_SHA256,
                                      "selection": "First 8 source records with 6–80 events; full chart context retained",
                                      "metadata": "No network resolution; missing titles/artists remain unavailable"}
        audit["import"] = imported
        print(json.dumps({"directory": export_packet(root, audit, packet), "coverage": audit["coverage"],
                          "candidate_audit": audit["candidate_audit"]}, indent=2))


if __name__ == "__main__":
    main()
