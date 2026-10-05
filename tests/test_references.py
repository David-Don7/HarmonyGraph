from sqlalchemy import select, inspect
from alembic import command
from alembic.config import Config
from harmonygraph.contracts import AnalysisConfig
from harmonygraph.db import Song, SourceAnnotation, BenchmarkQuery, make_engine
from harmonygraph.demo import generate, seed_benchmark
from harmonygraph.ingestion import ingest
from harmonygraph.music import alignment, parse_chord
from harmonygraph.research import grouped_splits
from harmonygraph.validation import harmonic_evaluation


def test_equivalent_harte_interval_set_and_half_diminished():
    assert parse_chord("Cm7").token == parse_chord("C:(1,b3,5,b7)").token
    assert parse_chord("B:hdim7").token == parse_chord("Bm7b5").token


def test_function_removal_actually_removes_degree_cost():
    score, _ = alignment(["I", "V"], ["IV", "I"], AnalysisConfig(functions=False))
    assert score == 1
    ordinary, _ = alignment(["I", "V"], ["IV", "I"], AnalysisConfig())
    assert ordinary < 1


def test_supplied_harmonic_references_are_evaluated(session, corpus):
    song = session.scalar(select(Song).where(Song.source_id == "0"))
    source = session.scalar(select(SourceAnnotation).where(SourceAnnotation.song_id == song.id))
    source.data = {
        **source.data,
        "annotations": {
            "event_keys": {"0": "C:maj"},
            "event_romans": {"0": ["I"]},
            "key_boundaries": [],
            "modulation_boundaries": [],
            "cadence_boundaries": [3, 7, 13, 19],
        },
    }
    session.commit()
    result = harmonic_evaluation(session, corpus[1], [song.id], 3)
    assert result["uncertainty"]["available"]
    assert result["reference_key_events"] == 1
    assert result["roman_accuracy"]["available"]
    assert result["roman_accuracy"]["accuracy"] == 1
    assert result["cadence_boundaries"]["available"]


def test_demo_variant_groups_and_exact_subpassage_labels(session, tmp_path):
    path = generate(tmp_path / "demo.jsonl")
    ingest(session, path)
    bid = seed_benchmark(session)
    _, assignments = grouped_splits(session)
    assignment = {a["song_id"]: a for a in assignments}
    songs = list(session.scalars(select(Song)))
    pop = [s for s in songs if s.duplicate_group == "demo-pop-cycle"]
    assert len(pop) == 36
    assert len({assignment[s.id]["split"] for s in pop}) == 1
    repeat = next(s for s in songs if s.source_id == "demo-repetition-0")
    query = session.scalar(
        select(BenchmarkQuery).where(BenchmarkQuery.benchmark_id == bid, BenchmarkQuery.source_song_id == repeat.id)
    )
    assert query.synthetic_judgments[f"{repeat.id}:9:12"] == 2
    assert query.synthetic_judgments[f"{repeat.id}:8:12"] == 2
    assert len(list(session.scalars(select(BenchmarkQuery).where(BenchmarkQuery.benchmark_id == bid)))) == 120


def test_immutable_migration_up_and_down(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'migrations.db'}")
    config = Config("alembic.ini")
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        assert "pattern_indexes" in inspect(connection).get_table_names()
        command.downgrade(config, "base")
        assert "songs" not in inspect(connection).get_table_names()
    engine.dispose()


def test_optuna_migration_namespace_is_separate(tmp_path):
    import optuna
    from sqlalchemy import text

    engine = make_engine(f"sqlite:///{tmp_path / 'optuna-migration.db'}")
    config = Config("alembic.ini")
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    optuna.storages.RDBStorage(url=engine.url.render_as_string(hide_password=False))
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM harmonygraph_schema_version")) == "0004"
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) != "0001"
    engine.dispose()
