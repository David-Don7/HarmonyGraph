from sqlalchemy import event, select

from harmonygraph.db import Song
from harmonygraph.retrieval import load_evidence_batch, load_song_evidence, _evidence_cache
from harmonygraph.consumer import practice_chord


def test_bulk_evidence_uses_constant_round_trips_and_preserves_contents(session, corpus):
    _, run_id, _ = corpus
    ids = list(session.scalars(select(Song.id)))
    _evidence_cache.clear()
    statements = []

    def capture(conn, cursor, statement, params, context, many):
        statements.append(statement)

    event.listen(session.get_bind(), "before_cursor_execute", capture)
    try:
        result = load_evidence_batch(session, ids, run_id)
        assert len(result) == 12
        assert len(statements) == 7
        assert all(len(evidence[1]) == 20 for evidence in result.values())
        assert all(evidence[4].analysis_id == run_id for evidence in result.values())
        assert all(evidence[5] for evidence in result.values())
        statements.clear()
        assert load_song_evidence(session, ids[0], run_id) == result[ids[0]]
        assert not statements
    finally:
        event.remove(session.get_bind(), "before_cursor_execute", capture)


def test_practice_voicings_respect_spelling_bass_and_omissions():
    assert practice_chord("Fs").notes == practice_chord("F#").notes
    assert practice_chord("C/E").notes[0] == 52
    assert {n % 12 for n in practice_chord("Cm7no3d").notes} == {0, 7, 10}
    assert practice_chord("N").notes == []
    assert practice_chord("N").status == "no_chord"
    assert practice_chord("not-a-chord").notes == []
    assert practice_chord("not-a-chord").status == "unknown"


def test_cached_hmm_matches_preoptimization_golden_and_keeps_duration_weights():
    import numpy as np
    from harmonygraph.music import infer_keys, parse_chord
    from harmonygraph.contracts import AnalysisConfig

    chords = [parse_chord(c) for c in "C G7 C N Am E7 Am".split()]
    sections = [0, 0, 0, 1, 1, 1, 1]
    durations = [1, 2, None, None, 3, 0.5, 1]
    posterior, path = infer_keys(chords, sections, durations, AnalysisConfig())
    assert path == [21] * 7
    np.testing.assert_allclose(
        posterior[[0, 3, 6], 21], [0.8620941189411078, 0.9563928169372178, 0.9626293191727426], rtol=1e-12
    )
    np.testing.assert_allclose(posterior.sum(axis=1), 1)
    other, _ = infer_keys(chords, sections, [1] * 7, AnalysisConfig())
    assert not np.allclose(posterior, other)
    again, _ = infer_keys(chords, sections, durations, AnalysisConfig())
    np.testing.assert_array_equal(posterior, again)


def test_productive_catalog_batches_continue_immediately_but_empty_batches_back_off(engine, session):
    from datetime import datetime, timezone
    from unittest.mock import patch
    from harmonygraph.db import Job, factory
    from harmonygraph.jobs import run_job

    for count in (20, 0):
        job = Job(kind="catalog_analyze", status="running", owner="test")
        session.add(job)
        session.commit()
        with patch("harmonygraph.jobs.dispatch", return_value={"continue": True, "indexed_this_batch": count}):
            run_job(factory(engine), job.id, "test")
        session.refresh(job)
        assert job.status == "queued"
        delay = (datetime.fromisoformat(job.updated_at) - datetime.now(timezone.utc)).total_seconds()
        assert (delay <= 0) if count else (delay > 50)


def test_catalog_connection_failures_retry_boundedly_and_keep_cancellation(engine, session):
    from unittest.mock import patch
    from sqlalchemy.exc import OperationalError
    from harmonygraph.db import Job, factory
    from harmonygraph.jobs import run_job

    job = Job(kind="catalog_analyze", status="running", owner="test")
    session.add(job)
    session.commit()
    failure = OperationalError("insert", {}, RuntimeError("connection interrupted"))
    for attempt in range(4):
        job.status, job.owner = "running", "test"
        session.commit()
        with patch("harmonygraph.jobs.dispatch", side_effect=failure):
            run_job(factory(engine), job.id, "test")
        session.refresh(job)
        assert job.status == ("queued" if attempt < 3 else "failed")
        assert job.parameters["_transient_retries"] == min(attempt + 1, 3)
    job.status, job.owner, job.cancel_requested = "running", "test", True
    session.commit()
    with patch("harmonygraph.jobs.dispatch", side_effect=failure):
        run_job(factory(engine), job.id, "test")
    session.refresh(job)
    assert job.status == "cancelled"
