import json
import pytest
from harmonygraph.analysis import analyze
from harmonygraph.db import Base, factory, make_engine
from harmonygraph.ingestion import ingest


@pytest.fixture
def engine(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine):
    with factory(engine)() as session:
        yield session


@pytest.fixture
def corpus(session, tmp_path):
    from harmonygraph.music import NAMES

    songs = []
    for shift in range(12):

        def events(pairs):
            return [{"label": NAMES[(root + shift) % 12] + suffix} for root, suffix in pairs]

        songs.append(
            {
                "source_id": str(shift),
                "title": f"Transposition {shift}",
                "artist": f"Artist {shift}",
                "genres": ["fixture"],
                "sections": [
                    {"label": "Verse 1", "events": events([(0, ""), (5, ""), (7, "7"), (0, "")] * 2)},
                    {"label": "Chorus 1", "events": events([(0, ""), (7, ""), (9, "m"), (5, ""), (7, "7"), (0, "")])},
                    {"label": "Chorus 2", "events": events([(0, ""), (7, ""), (9, "m"), (5, ""), (7, "7"), (0, "")])},
                ],
            }
        )
    path = tmp_path / "songs.jsonl"
    path.write_text("\n".join(json.dumps(s) for s in songs), encoding="utf-8")
    imported = ingest(session, path)
    run_id = analyze(session)
    return imported, run_id, path
