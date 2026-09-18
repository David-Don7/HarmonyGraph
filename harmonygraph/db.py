from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker


def uid():
    return str(uuid.uuid4())


def now():
    return datetime.now(timezone.utc).isoformat()


class Base(DeclarativeBase):
    pass


class Dataset(Base):
    __tablename__ = "datasets"
    id = Column(String, primary_key=True, default=uid)
    name = Column(String, nullable=False)
    fingerprint = Column(String, unique=True, nullable=False)
    source = Column(String, nullable=False)
    license = Column(String, default="unspecified")
    synthetic = Column(Boolean, default=False)
    report = Column(JSON, default=dict)
    created_at = Column(String, default=now)


class Artist(Base):
    __tablename__ = "artists"
    id = Column(String, primary_key=True, default=uid)
    name = Column(String, unique=True, nullable=False)


class Song(Base):
    __tablename__ = "songs"
    id = Column(String, primary_key=True, default=uid)
    dataset_id = Column(ForeignKey("datasets.id"), nullable=False, index=True)
    source_id = Column(String, nullable=False)
    title = Column(String)
    artist_id = Column(ForeignKey("artists.id"), index=True)
    year = Column(Integer, index=True)
    duplicate_group = Column(String, index=True)
    content_hash = Column(String, nullable=False, index=True)
    synthetic = Column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("dataset_id", "source_id"),)


class Genre(Base):
    __tablename__ = "genres"
    id = Column(String, primary_key=True, default=uid)
    name = Column(String, unique=True)


class SongGenre(Base):
    __tablename__ = "song_genres"
    song_id = Column(ForeignKey("songs.id"), primary_key=True)
    genre_id = Column(ForeignKey("genres.id"), primary_key=True)


class Section(Base):
    __tablename__ = "sections"
    id = Column(String, primary_key=True, default=uid)
    song_id = Column(ForeignKey("songs.id"), nullable=False, index=True)
    ordinal = Column(Integer, nullable=False)
    label = Column(String, nullable=False)
    kind = Column(String, index=True)
    start = Column(Integer, nullable=False)
    end = Column(Integer, nullable=False)
    __table_args__ = (UniqueConstraint("song_id", "ordinal"),)


class ChordDefinition(Base):
    __tablename__ = "chord_definitions"
    id = Column(String, primary_key=True)
    canonical = Column(JSON, nullable=False)


class ChordEvent(Base):
    __tablename__ = "chord_events"
    id = Column(String, primary_key=True, default=uid)
    song_id = Column(ForeignKey("songs.id"), nullable=False, index=True)
    section_id = Column(ForeignKey("sections.id"), nullable=False, index=True)
    chord_id = Column(ForeignKey("chord_definitions.id"), nullable=False)
    ordinal = Column(Integer, nullable=False)
    label = Column(String, nullable=False)
    onset = Column(Float)
    duration = Column(Float)
    timing_unit = Column(String)
    __table_args__ = (UniqueConstraint("song_id", "ordinal"),)


class SourceAnnotation(Base):
    __tablename__ = "source_annotations"
    id = Column(String, primary_key=True, default=uid)
    song_id = Column(ForeignKey("songs.id"), nullable=False, index=True)
    data = Column(JSON, nullable=False)


class ModelConfiguration(Base):
    __tablename__ = "model_configurations"
    id = Column(String, primary_key=True)
    name = Column(String)
    parameters = Column(JSON, nullable=False)
    frozen = Column(Boolean, default=False)
    freeze_manifest = Column(JSON, default=dict)
    created_at = Column(String, default=now)


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    id = Column(String, primary_key=True, default=uid)
    configuration_id = Column(ForeignKey("model_configurations.id"), nullable=False)
    corpus_hash = Column(String, nullable=False)
    status = Column(String, default="building")
    active = Column(Boolean, default=False)
    created_at = Column(String, default=now)
    report = Column(JSON, default=dict)


class SongAnalysis(Base):
    __tablename__ = "song_analyses"
    analysis_id = Column(ForeignKey("analysis_runs.id"), primary_key=True)
    song_id = Column(ForeignKey("songs.id"), primary_key=True)
    posterior = Column(JSON, nullable=False)
    path = Column(JSON, nullable=False)


class LocalKeyHypothesis(Base):
    __tablename__ = "local_key_hypotheses"
    id = Column(String, primary_key=True, default=uid)
    analysis_id = Column(ForeignKey("analysis_runs.id"), nullable=False, index=True)
    event_id = Column(ForeignKey("chord_events.id"), nullable=False, index=True)
    key_index = Column(Integer, nullable=False)
    confidence = Column(Float, nullable=False)


class FunctionalInterpretation(Base):
    __tablename__ = "functional_interpretations"
    id = Column(String, primary_key=True, default=uid)
    hypothesis_id = Column(ForeignKey("local_key_hypotheses.id"), nullable=False, index=True)
    event_id = Column(ForeignKey("chord_events.id"), nullable=False, index=True)
    analysis_id = Column(ForeignKey("analysis_runs.id"), nullable=False, index=True)
    key_index = Column(Integer, nullable=False)
    roman = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    data = Column(JSON, nullable=False)


class HarmonicRelation(Base):
    __tablename__ = "harmonic_relations"
    id = Column(String, primary_key=True, default=uid)
    analysis_id = Column(ForeignKey("analysis_runs.id"), nullable=False, index=True)
    song_id = Column(ForeignKey("songs.id"), nullable=False, index=True)
    kind = Column(String, nullable=False, index=True)
    start = Column(Integer, nullable=False)
    end = Column(Integer, nullable=False)
    confidence = Column(Float, nullable=False)
    evidence = Column(JSON, nullable=False)


class PatternIndex(Base):
    __tablename__ = "pattern_indexes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_id = Column(ForeignKey("analysis_runs.id"), nullable=False)
    song_id = Column(ForeignKey("songs.id"), nullable=False)
    section_id = Column(ForeignKey("sections.id"), nullable=False)
    mode = Column(String, nullable=False)
    token = Column(String, nullable=False)
    position = Column(Integer, nullable=False)
    __table_args__ = (Index("ix_pattern_lookup", "analysis_id", "mode", "token", "song_id", "position"),)


class RetrievalQuery(Base):
    __tablename__ = "retrieval_queries"
    id = Column(String, primary_key=True, default=uid)
    request = Column(JSON, nullable=False)
    analysis_id = Column(ForeignKey("analysis_runs.id"), nullable=False)
    created_at = Column(String, default=now)


class RetrievalResult(Base):
    __tablename__ = "retrieval_results"
    id = Column(String, primary_key=True, default=uid)
    query_id = Column(ForeignKey("retrieval_queries.id"), nullable=False, index=True)
    rank = Column(Integer)
    data = Column(JSON, nullable=False)


class Annotator(Base):
    __tablename__ = "annotators"
    id = Column(String, primary_key=True, default=uid)
    name = Column(String, nullable=False, unique=True)


class Benchmark(Base):
    __tablename__ = "benchmarks"
    id = Column(String, primary_key=True, default=uid)
    name = Column(String, nullable=False)
    synthetic = Column(Boolean, default=False)
    created_at = Column(String, default=now)


class BenchmarkQuery(Base):
    __tablename__ = "benchmark_queries"
    id = Column(String, primary_key=True, default=uid)
    benchmark_id = Column(ForeignKey("benchmarks.id"), nullable=False, index=True)
    category = Column(String)
    request = Column(JSON, nullable=False)
    source_song_id = Column(ForeignKey("songs.id"))
    pool = Column(JSON, default=list)
    synthetic_judgments = Column(JSON, default=dict)


class RelevanceJudgment(Base):
    __tablename__ = "relevance_judgments"
    id = Column(String, primary_key=True, default=uid)
    query_id = Column(ForeignKey("benchmark_queries.id"), nullable=False, index=True)
    passage_id = Column(String, nullable=False)
    annotator_id = Column(ForeignKey("annotators.id"), nullable=False)
    relevance = Column(Integer, nullable=False)
    ratings = Column(JSON, default=dict)
    notes = Column(Text)
    adjudicated = Column(Boolean, default=False)
    created_at = Column(String, default=now)


class SplitAssignment(Base):
    __tablename__ = "split_assignments"
    manifest = Column(String, primary_key=True)
    song_id = Column(ForeignKey("songs.id"), primary_key=True)
    group_id = Column(String, nullable=False)
    split = Column(String, nullable=False)


class ExperimentRun(Base):
    __tablename__ = "experiment_runs"
    id = Column(String, primary_key=True, default=uid)
    benchmark_id = Column(ForeignKey("benchmarks.id"), nullable=False)
    configuration_id = Column(ForeignKey("model_configurations.id"), nullable=False)
    analysis_id = Column(ForeignKey("analysis_runs.id"), nullable=False)
    split = Column(String)
    manifest = Column(JSON, nullable=False)
    results = Column(JSON, nullable=False)
    created_at = Column(String, default=now)


class OptimizationStudy(Base):
    __tablename__ = "optimization_studies"
    id = Column(String, primary_key=True, default=uid)
    name = Column(String, nullable=False, unique=True)
    benchmark_id = Column(ForeignKey("benchmarks.id"), nullable=False)
    summary = Column(JSON, default=dict)


class OptimizationTrial(Base):
    __tablename__ = "optimization_trials"
    id = Column(String, primary_key=True, default=uid)
    study_id = Column(ForeignKey("optimization_studies.id"), nullable=False, index=True)
    number = Column(Integer)
    parameters = Column(JSON)
    value = Column(Float)
    state = Column(String)


class Job(Base):
    __tablename__ = "jobs"
    id = Column(String, primary_key=True, default=uid)
    kind = Column(String, nullable=False)
    status = Column(String, default="queued", index=True)
    progress = Column(Float, default=0)
    parameters = Column(JSON, default=dict)
    result = Column(JSON, default=dict)
    error = Column(Text)
    cancel_requested = Column(Boolean, default=False)
    owner = Column(String)
    created_at = Column(String, default=now)
    updated_at = Column(String, default=now)


def make_engine(url=None):
    url = url or os.environ.get("DATABASE_URL", "sqlite:///data/local/harmonygraph-v1.db")
    if url.startswith("sqlite:///data/local/"):
        os.makedirs("data/local", exist_ok=True)
    engine = create_engine(
        url,
        pool_pre_ping=True,
        **({"connect_args": {"check_same_thread": False, "timeout": 60}} if url.startswith("sqlite") else {}),
    )
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def pragmas(conn, record):
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA journal_mode=WAL")

    return engine


def factory(engine):
    return sessionmaker(engine, expire_on_commit=False)


def record(row):
    if not hasattr(row, "__table__"):
        return vars(row).copy()
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}
