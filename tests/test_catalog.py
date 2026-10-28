import csv
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from harmonygraph.api import create_app
from harmonygraph.catalog import import_catalog, analyze_batch, provider_metadata, resolve_metadata, release_date
from harmonygraph.consumer import ConsumerSearchRequest, consumer_search, browse
from harmonygraph.db import CatalogRecord, CatalogSnapshot, CatalogArtifact, ChordEvent, ProviderMetadata
from harmonygraph.music import parse_chord


@pytest.fixture
def catalog(session, tmp_path):
    path = tmp_path / "real-format.csv"
    with path.open("w", newline="") as output:
        writer = csv.DictWriter(
            output, fieldnames=["id", "chords", "release_date", "spotify_song_id", "spotify_artist_id", "main_genre"]
        )
        writer.writeheader()
        for i in range(3):
            writer.writerow(
                {
                    "id": str(i),
                    "chords": "<verse_1> Csmin Fsmin Gs Csmin <chorus_1> C G Am F G7 C",
                    "release_date": "2003-01-01",
                    "spotify_song_id": "2ffJZ2r8HxI5DHcmf3BO6c" if i < 2 else "1111111111111111111111",
                    "spotify_artist_id": "694QW15WkebjcrWgQHzRYF",
                    "main_genre": "rock",
                }
            )
    result = import_catalog(session, path, {}, lambda _: None)
    rows = list(session.scalars(select(CatalogRecord).order_by(CatalogRecord.id)))
    for row in rows:
        row.title, row.artist, row.metadata_status = "Fixture title", "Fixture artist", "resolved"
    session.commit()
    return path, result, rows


def test_publisher_notation_and_date_precision():
    assert parse_chord("Fs").token == parse_chord("F#").token
    assert parse_chord("Csmin").token == parse_chord("C#m").token
    assert parse_chord("A/Cs").bass == 1
    assert parse_chord("Csus4").quality == "sus4"
    assert parse_chord("Cm7no3d").intervals == [0, 7, 10]
    assert parse_chord("C7no3d").intervals == [0, 7, 10]
    assert parse_chord("not a chord").status == "unknown"
    assert release_date({"release_date": "2003"}) == (2003, "year")
    assert release_date({"decade": "1990"}) == (None, None)


def test_stream_import_idempotent_and_resume(session, catalog):
    path, result, rows = catalog
    assert result["source_records"] == 3
    assert session.scalar(select(func.count()).select_from(ChordEvent)) == 0
    assert import_catalog(session, path, {}, lambda _: None)["imported"] == 3
    assert session.scalar(select(func.count()).select_from(CatalogRecord)) == 3
    assert len(browse(session).items) == 2
    assert browse(session, q="artist").items
    assert not browse(session, q="%absent").items


def test_studio_uses_published_catalog_without_requiring_full_reanalysis(engine, session, catalog):
    from harmonygraph.analysis import process_song
    from harmonygraph.catalog import materialize
    from harmonygraph.contracts import AnalysisConfig, SearchRequest
    from harmonygraph.retrieval import active_run, search

    _, _, rows = catalog
    rows[2].metadata_status = "pending"
    session.commit()
    analyze_batch(session, {}, lambda _: None)
    snapshot = session.scalar(select(CatalogSnapshot).where(CatalogSnapshot.active.is_(True)))
    run = active_run(session)
    assert run.id == snapshot.analysis_id and not run.active
    # A committed analysis outside the publication watermark must not leak into
    # Studio's default search while the next catalog batch is being prepared.
    rows[2].metadata_status = "resolved"
    song_id = materialize(session, rows[2])
    process_song(session, song_id, run.id, AnalysisConfig())
    session.commit()
    response = search(session, SearchRequest(progression="C G", mode="literal"))
    assert response.results
    assert song_id not in {r.song_id for r in response.results}
    client = TestClient(create_app(engine))
    assert client.get("/api/v1/overview").json()["analysis"]["id"] == run.id


def test_atomic_publication_and_snapshot_isolation(session, catalog):
    _, _, rows = catalog
    rows[2].metadata_status = "pending"
    session.commit()
    analyze_batch(session, {}, lambda _: None)
    old = session.scalar(select(CatalogSnapshot).where(CatalogSnapshot.active.is_(True)))
    assert old.songs == 2
    rows[2].metadata_status = "resolved"
    session.commit()
    # An indexing failure cannot activate a new snapshot.
    with patch("harmonygraph.analysis.process_song", side_effect=RuntimeError("index failed")):
        with pytest.raises(RuntimeError):
            analyze_batch(session, {}, lambda _: None)
    session.rollback()
    assert session.get(CatalogSnapshot, old.id).active
    analyze_batch(session, {}, lambda _: None)
    newer = session.scalar(select(CatalogSnapshot).where(CatalogSnapshot.active.is_(True)))
    assert newer.id != old.id
    assert old.sequence == 2 and newer.sequence == 3
    analyze_batch(session, {}, lambda _: None)
    assert session.scalar(select(func.count()).select_from(CatalogArtifact)) == 3
    body = ConsumerSearchRequest(progression="C G Am F", mode="transposed", catalog_snapshot=old.id)
    response = consumer_search(session, body)
    assert response.results
    old_ids = {r.id for r in rows[:2]}
    assert all(r.song.id in old_ids for r in response.results)
    for result in response.results:
        assert result.score == pytest.approx(sum(c["contribution"] for c in result.query_contributions))


@pytest.mark.parametrize(
    "mode,notation,progression",
    [
        ("literal", "chords", "C G Am F"),
        ("transposed", "chords", "D A Bm G"),
        ("functional", "roman", "I V vi IV"),
        ("fuzzy", "chords", "C G Am F"),
    ],
)
def test_all_consumer_modes(session, catalog, mode, notation, progression):
    analyze_batch(session, {}, lambda _: None)
    response = consumer_search(session, ConsumerSearchRequest(progression=progression, mode=mode, notation=notation))
    assert response.results
    assert len({r.song.track_id for r in response.results}) == len(response.results)
    assert sum(q["weight"] for q in response.query_interpretations) == pytest.approx(1)


def test_consumer_excludes_research_songs(engine, session, corpus, catalog):
    client = TestClient(create_app(engine))
    assert client.get("/api/v1/catalog/coverage").json()["imported_records"] == 3
    research_song = client.get("/api/v1/songs").json()[0]["id"]
    assert client.get(f"/api/v1/catalog/songs/{research_song}").status_code == 404
    assert client.get("/api/v1/catalog/songs").json()["items"][0]["title"] == "Fixture title"
    assert (
        client.post("/api/v1/catalog/search", json={"progression": "C G", "catalog_snapshot": "absent"}).status_code
        == 404
    )


def test_metadata_cache_and_unavailable_are_honest(session, catalog):
    _, _, rows = catalog
    with patch("urllib.request.urlopen") as network:
        bad = provider_metadata(session, "track", "invalid", lambda _: None)
        assert bad.status == "unavailable"
        network.assert_not_called()
    row = rows[0]
    row.metadata_status, row.title, row.artist = "pending", None, None
    session.add(ProviderMetadata(id=f"spotify:track:{row.track_id}", status="unavailable", payload={}))
    session.add(
        ProviderMetadata(
            id=f"spotify:artist:{row.spotify_artist_id}", status="resolved", payload={"title": "Fixture artist"}
        )
    )
    session.commit()
    with patch("urllib.request.urlopen") as network:
        resolve_metadata(session, {}, lambda _: None)
        network.assert_not_called()
    session.refresh(row)
    assert row.metadata_status == "unavailable" and row.title is None


def test_snapshot_split_manifest_does_not_follow_live_catalog(session, catalog):
    from harmonygraph.research import grouped_splits, snapshot_scope

    _, _, rows = catalog
    rows[-1].metadata_status = "pending"
    session.commit()
    analyze_batch(session, {}, lambda _: None)
    snapshot = session.scalar(select(CatalogSnapshot).where(CatalogSnapshot.active.is_(True)))
    before = grouped_splits(session, song_ids=snapshot_scope(session, snapshot.id))
    rows[-1].metadata_status = "resolved"
    session.commit()
    analyze_batch(session, {}, lambda _: None)
    after = grouped_splits(session, song_ids=snapshot_scope(session, snapshot.id))
    assert before == after


def test_graceful_shutdown_requeues_durable_job(engine, session):
    from harmonygraph.db import Job, factory
    from harmonygraph.jobs import run_job

    job = Job(kind="catalog_analyze", status="running", owner="test-worker")
    session.add(job)
    session.commit()
    with patch("harmonygraph.jobs.dispatch", side_effect=SystemExit(0)):
        with pytest.raises(SystemExit):
            run_job(factory(engine), job.id, "test-worker")
    session.refresh(job)
    assert job.status == "queued" and job.owner is None
