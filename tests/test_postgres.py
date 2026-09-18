"""Integration checks in an isolated schema of an explicitly supplied PostgreSQL database."""

import json
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text
from sqlalchemy.engine import make_url
from harmonygraph.analysis import analyze
from harmonygraph.contracts import AnalysisConfig, SearchRequest
from harmonygraph.db import AnalysisRun, Job, factory, make_engine
from harmonygraph.ingestion import ingest
from harmonygraph.jobs import claim_job
from harmonygraph.retrieval import search

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="TEST_POSTGRES_URL not supplied")


@pytest.fixture
def postgres():
    url = os.environ["TEST_POSTGRES_URL"]
    admin = make_engine(url)
    schema = "harmonygraph_test_" + uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped_url = make_url(url).update_query_dict({"options": f"-csearch_path={schema}"})
    engine = make_engine(scoped_url.render_as_string(hide_password=False))
    try:
        config = Config("alembic.ini")
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_postgres_migrations_indexes_and_skip_locked(postgres):
    sessions = factory(postgres)
    with sessions() as first, sessions() as second:
        a, b = Job(kind="analyze"), Job(kind="analyze")
        first.add_all([a, b])
        first.commit()
        first.execute(select(Job).where(Job.id == a.id).with_for_update()).scalar_one()
        assert claim_job(second, "second") == b.id
        first.rollback()
        assert claim_job(first, "first") == a.id
        assert any(i["name"] == "ix_pattern_lookup" for i in inspect(postgres).get_indexes("pattern_indexes"))
        assert first.scalar(text("SELECT version_num FROM harmonygraph_schema_version")) == "0001"


def test_postgres_ingestion_filtering_versions_and_recovery(postgres, tmp_path):
    path = tmp_path / "fixture.jsonl"
    path.write_text(
        json.dumps(
            {
                "source_id": "postgres-fixture",
                "genres": ["jazz"],
                "year": 1999,
                "sections": [{"label": "chorus", "events": [{"label": c} for c in ["C", "G7", "C"]]}],
            }
        )
    )
    with factory(postgres)() as session:
        assert ingest(session, path)["imported"] == 1
        assert ingest(session, path)["skipped"] == 1
        original = analyze(session)
        newer = analyze(session, AnalysisConfig(window=9))
        assert not session.get(AnalysisRun, original).active
        query = SearchRequest(progression="G7 C", mode="literal", section="chorus", genre="jazz", year_from=1990)
        current = search(session, query)
        assert current.results and all(r.analysis_id == newer for r in current.results)
        historical = search(session, query.model_copy(update={"analysis_id": original}))
        assert historical.results and all(r.analysis_id == original for r in historical.results)
        assert not search(session, query.model_copy(update={"genre": "absent"})).results
        old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        job = Job(kind="analyze", status="running", owner="crashed-worker", updated_at=old)
        session.add(job)
        session.commit()
        assert claim_job(session, "replacement-worker") == job.id
