from __future__ import annotations


import csv

import io

import json

import logging

import time

from fastapi import Depends, FastAPI, HTTPException, Query, Request

from fastapi.middleware.cors import CORSMiddleware

from fastapi.responses import Response

from pydantic import BaseModel, Field

from sqlalchemy import func, select, text

from .contracts import AnalysisConfig, JobInput, JobResponse, JudgmentInput, SearchRequest, SearchResponse

from .db import (
    AnalysisRun,
    Annotator,
    Artist,
    Benchmark,
    BenchmarkQuery,
    ChordEvent,
    Dataset,
    ExperimentRun,
    Genre,
    Job,
    ModelConfiguration,
    OptimizationStudy,
    OptimizationTrial,
    RelevanceJudgment,
    Song,
    SourceAnnotation,
    factory,
    make_engine,
    now,
    record,
)

from .retrieval import active_run, load_song_evidence, search


class NameInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class AnnotatorInput(NameInput):
    qualifications: str = ""


class BenchmarkInput(NameInput):
    synthetic: bool = False


class QueryInput(BaseModel):
    category: str

    request: SearchRequest

    source_song_id: str | None = None
    protocol: dict = {}


class FreezeInput(BaseModel):
    benchmark_id: str

    configuration_id: str | None = None
    catalog_snapshot: str | None = None


def create_app(engine=None):
    engine = engine or make_engine()

    sessions = factory(engine)

    app = FastAPI(
        title="HarmonyGraph", version="0.1.0", description="Local uncertainty-aware harmonic retrieval and research API"
    )

    app.state.sessions = sessions

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8080",
            "http://127.0.0.1:8080",
        ],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    def db():
        with sessions() as session:
            yield session

    from .consumer import router

    app.include_router(router(db))

    def require(session, model, identifier):
        value = session.get(model, identifier)

        if value is None:
            raise HTTPException(404, f"{model.__name__} not found")

        return value

    @app.exception_handler(ValueError)
    async def validation_error(request, error):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=422, content={"detail": str(error)})

    @app.middleware("http")
    async def timing(request: Request, call_next):
        start = time.perf_counter()

        response = await call_next(request)

        response.headers["X-Process-Time-Ms"] = str(round((time.perf_counter() - start) * 1000, 2))

        logging.getLogger("harmonygraph.api").info(
            json.dumps(
                {
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "ms": response.headers["X-Process-Time-Ms"],
                }
            )
        )

        return response

    @app.get("/api/v1/health")
    def health(session=Depends(db)):
        session.execute(text("SELECT 1"))

        return {"status": "ok", "database": engine.dialect.name, "version": "0.1.0"}

    @app.get("/api/v1/overview")
    def overview(session=Depends(db)):
        try:
            run = active_run(session)
        except ValueError:
            run = None

        return {
            "songs": session.scalar(select(func.count()).select_from(Song)),
            "events": session.scalar(select(func.count()).select_from(ChordEvent)),
            "datasets": session.scalar(select(func.count()).select_from(Dataset)),
            "analysis": record(run) if run else None,
            "genres": list(session.scalars(select(Genre.name).order_by(Genre.name))),
            "notice": "Model confidence is not established calibration. Synthetic data is marked throughout.",
        }

    @app.post("/api/v1/search", response_model=SearchResponse)
    def search_api(request: SearchRequest, session=Depends(db)):
        return search(session, request, persist=True)

    @app.get("/api/v1/songs")
    def songs(q: str = "", limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), session=Depends(db)):
        stmt = select(Song, Artist.name).outerjoin(Artist).order_by(Song.title).offset(offset).limit(limit)

        if q:
            stmt = stmt.where(Song.title.ilike(f"%{q}%"))

        return [{**record(song), "artist": artist} for song, artist in session.execute(stmt)]

    @app.get("/api/v1/songs/{song_id}")
    def song_detail(song_id: str, analysis_id: str | None = None, session=Depends(db)):
        require(session, Song, song_id)

        run = active_run(session, analysis_id)

        song, events, chords, sections, analysis, alternatives, relations, artist = load_song_evidence(
            session, song_id, run.id
        )

        if not analysis:
            raise HTTPException(409, "Song is not part of this analysis version")

        source = session.scalar(select(SourceAnnotation).where(SourceAnnotation.song_id == song_id))

        return {
            **record(song),
            "artist": artist.name if artist else None,
            "analysis_id": run.id,
            "sections": [record(s) for s in sorted(sections.values(), key=lambda s: s.ordinal)],
            "events": [
                {
                    **record(e),
                    "chord": c.data(),
                    "posterior": analysis.posterior[e.ordinal],
                    "path_key": analysis.path[e.ordinal],
                    "interpretations": dict(alternatives[e.id]),
                }
                for e, c in zip(events, chords)
            ],
            "relations": [record(r) for r in relations],
            "source": source.data if source else None,
        }

    @app.get("/api/v1/datasets")
    def datasets(session=Depends(db)):
        return [record(row) for row in session.scalars(select(Dataset).order_by(Dataset.created_at.desc()))]

    @app.post("/api/v1/imports", response_model=JobResponse, status_code=202)
    def import_api(body: dict, session=Depends(db)):
        from .jobs import input_path

        input_path(body.get("path", ""))

        job = Job(kind="import", parameters=body)

        session.add(job)

        session.commit()

        return record(job)

    @app.get("/api/v1/jobs", response_model=list[JobResponse])
    def jobs(session=Depends(db)):
        return [record(row) for row in session.scalars(select(Job).order_by(Job.created_at.desc()).limit(100))]

    @app.post("/api/v1/jobs", response_model=JobResponse, status_code=202)
    def submit_job(body: JobInput, session=Depends(db)):
        if body.kind == "research_v2_compare":
            from .study import comparison_parameters

            body.parameters = comparison_parameters(session, body.parameters)
        job = Job(kind=body.kind, parameters=body.parameters)

        session.add(job)

        session.commit()

        return record(job)

    @app.get("/api/v1/jobs/{job_id}", response_model=JobResponse)
    def get_job(job_id: str, session=Depends(db)):
        return record(require(session, Job, job_id))

    @app.post("/api/v1/jobs/{job_id}/cancel", response_model=JobResponse)
    def cancel_job(job_id: str, session=Depends(db)):
        job = require(session, Job, job_id)

        if job.status in {"queued", "running"}:
            job.cancel_requested, job.updated_at = True, now()

        session.commit()

        return record(job)

    @app.get("/api/v1/analyses")
    def analyses(session=Depends(db)):
        return [record(row) for row in session.scalars(select(AnalysisRun).order_by(AnalysisRun.created_at.desc()))]

    @app.post("/api/v1/analyses/{analysis_id}/activate")
    def activate_analysis(analysis_id: str, session=Depends(db)):
        from sqlalchemy import update

        run = active_run(session, analysis_id)

        session.execute(update(AnalysisRun).values(active=False))

        run.active = True

        session.commit()

        return record(run)

    @app.get("/api/v1/configurations")
    def configurations(session=Depends(db)):
        return [
            record(row)
            for row in session.scalars(select(ModelConfiguration).order_by(ModelConfiguration.created_at.desc()))
        ]

    @app.post("/api/v1/configurations")
    def configuration(body: AnalysisConfig, session=Depends(db)):
        from .analysis import save_config

        return {"configuration_id": save_config(session, body)}

    @app.get("/api/v1/configurations/{configuration_id}/export")
    def export_configuration(configuration_id: str, session=Depends(db)):
        config = require(session, ModelConfiguration, configuration_id)

        return Response(
            json.dumps(config.parameters, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=selected-config.json"},
        )

    @app.post("/api/v1/configurations/freeze")
    def freeze_configuration(body: FreezeInput, session=Depends(db)):
        from .research import freeze

        require(session, Benchmark, body.benchmark_id)

        return freeze(session, body.benchmark_id, body.configuration_id, body.catalog_snapshot)

    @app.get("/api/v1/research-v2/status")
    def research_v2_status():
        from .research_v2 import READINESS

        return READINESS

    @app.get("/api/v1/benchmarks/{benchmark_id}/readiness")
    def study_readiness(benchmark_id: str, session=Depends(db)):
        from .study import readiness

        require(session, Benchmark, benchmark_id)
        return readiness(session, benchmark_id)

    @app.get("/api/v1/benchmarks/{benchmark_id}/review-packet")
    def study_packet(benchmark_id: str, session=Depends(db)):
        from .study import review_packet

        require(session, Benchmark, benchmark_id)
        return Response(
            json.dumps(review_packet(session, benchmark_id), indent=2),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=blinded-review-packet.json"},
        )

    @app.post("/api/v1/benchmarks/{benchmark_id}/review-responses")
    def study_responses(benchmark_id: str, body: dict, session=Depends(db)):
        from .study import ReviewSubmission, import_reviews

        require(session, Benchmark, benchmark_id)
        return import_reviews(session, benchmark_id, ReviewSubmission.model_validate(body))

    @app.get("/api/v1/jobs/{job_id}/export")
    def export_job(job_id: str, session=Depends(db)):
        job = require(session, Job, job_id)
        if job.kind != "research_v2_compare" or job.status != "completed":
            raise ValueError("A completed research v2 comparison is required")
        return Response(
            json.dumps(job.result, indent=2), media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=research-v2-comparison.json"},
        )

    @app.get("/api/v1/benchmark-queries/{query_id}/blind-pool")
    def blind_pool(query_id: str, session=Depends(db)):
        query = require(session, BenchmarkQuery, query_id)
        from .research_v2 import blinded_pool

        return blinded_pool(query)

    @app.get("/api/v1/annotators")
    def annotators(session=Depends(db)):
        return [record(row) for row in session.scalars(select(Annotator).order_by(Annotator.name))]

    @app.post("/api/v1/annotators", status_code=201)
    def annotator(body: AnnotatorInput, session=Depends(db)):
        name = body.name.strip()

        if not name:
            raise ValueError("Name cannot be blank")

        row = session.scalar(select(Annotator).where(Annotator.name == name))

        if row is None:
            row = Annotator(name=name, qualifications=body.qualifications)

            session.add(row)

            session.commit()

        return record(row)

    @app.get("/api/v1/benchmarks")
    def benchmarks(session=Depends(db)):
        return [
            {
                **record(row),
                "query_count": session.scalar(
                    select(func.count()).select_from(BenchmarkQuery).where(BenchmarkQuery.benchmark_id == row.id)
                ),
            }
            for row in session.scalars(select(Benchmark))
        ]

    @app.post("/api/v1/benchmarks", status_code=201)
    def benchmark(body: BenchmarkInput, session=Depends(db)):
        row = Benchmark(**body.model_dump())

        session.add(row)

        session.commit()

        return record(row)

    @app.get("/api/v1/benchmarks/{benchmark_id}/queries")
    def benchmark_queries(benchmark_id: str, session=Depends(db)):
        require(session, Benchmark, benchmark_id)

        return [
            record(row)
            for row in session.scalars(
                select(BenchmarkQuery)
                .where(BenchmarkQuery.benchmark_id == benchmark_id)
                .order_by(BenchmarkQuery.category, BenchmarkQuery.id)
            )
        ]

    @app.post("/api/v1/benchmarks/{benchmark_id}/queries", status_code=201)
    def create_query(benchmark_id: str, body: QueryInput, session=Depends(db)):
        require(session, Benchmark, benchmark_id)

        if body.source_song_id:
            require(session, Song, body.source_song_id)

        from .retrieval import query_tokens

        query_tokens(body.request)
        from .research_v2 import freeze_context

        body.protocol = freeze_context(session, body.source_song_id, body.protocol)

        row = BenchmarkQuery(benchmark_id=benchmark_id, **body.model_dump())

        session.add(row)

        session.commit()

        return record(row)

    @app.post("/api/v1/benchmark-queries/{query_id}")
    def edit_query(query_id: str, body: QueryInput, session=Depends(db)):
        query = require(session, BenchmarkQuery, query_id)

        if body.source_song_id:
            require(session, Song, body.source_song_id)

        from .retrieval import query_tokens

        query_tokens(body.request)
        from .research_v2 import freeze_context

        body.protocol = freeze_context(session, body.source_song_id, body.protocol)

        original = require(session, Benchmark, query.benchmark_id)

        # Editing starts a new annotation round. Prior queries, pools, and judgments

        # retain their identities and cannot be silently reinterpreted under new text.

        revision = Benchmark(name=f"{original.name} · revision of {original.id[:8]}", synthetic=original.synthetic)

        session.add(revision)

        session.flush()

        edited = None

        originals = list(session.scalars(select(BenchmarkQuery).where(BenchmarkQuery.benchmark_id == original.id)))

        for previous in originals:
            changed = previous.id == query_id

            copied = BenchmarkQuery(
                benchmark_id=revision.id,
                category=body.category if changed else previous.category,
                request=body.request.model_dump() if changed else previous.request,
                source_song_id=body.source_song_id if changed else previous.source_song_id,
                pool=[] if changed else previous.pool,
                synthetic_judgments={} if changed else previous.synthetic_judgments,
                protocol=body.protocol if changed else previous.protocol,
            )

            session.add(copied)

            if changed:
                edited = copied

        session.commit()

        return {**record(edited), "previous_benchmark_id": original.id}

    @app.post("/api/v1/benchmark-queries/{query_id}/pool")
    def pool(query_id: str, session=Depends(db)):
        query = require(session, BenchmarkQuery, query_id)

        if session.scalar(select(RelevanceJudgment.id).where(RelevanceJudgment.query_id == query.id).limit(1)):
            raise ValueError(
                "This pool has judgments and is frozen. Edit the query to create a new benchmark revision."
            )
        request = SearchRequest(**query.request)

        request.limit = 100

        from .research import absolute_query

        requests = [request.model_copy(update={"limit": 25})]
        if request.ranking != "legacy_mixture":
            requests.extend(
                request.model_copy(update={"ranking": method, "limit": 25})
                for method in ("legacy_mixture", "hard_path")
            )

        if request.pattern == "progression":
            absolute = absolute_query(session, query, request)

            for mode in ("literal", "transposed"):
                requests.append(
                    request.model_copy(
                        update={"mode": mode, "progression": absolute, "ranking": "legacy_mixture", "limit": 25}
                    )
                )

            if request.mode in {"functional", "fuzzy"}:
                requests.append(request.model_copy(update={"mode": "fuzzy", "limit": 25}))

        pooled = {}

        for candidate_request in requests:
            result = search(session, candidate_request)

            for candidate in result.results:
                value = pooled.setdefault(candidate.passage_id, candidate.model_dump())

                value["evidence"].setdefault("pooling_modes", []).append(candidate_request.mode)
                if "context_labels" not in value["evidence"]:
                    context = load_song_evidence(session, candidate.song_id, candidate.analysis_id)
                    value["evidence"]["context_labels"] = [e.label for e in context[1]]

        query.pool = [pooled[key] for key in sorted(pooled)]

        session.commit()

        return query.pool

    @app.get("/api/v1/benchmark-queries/{query_id}/judgments")
    def judgments(query_id: str, annotator_id: str, review: bool = False, session=Depends(db)):
        require(session, BenchmarkQuery, query_id)

        stmt = select(RelevanceJudgment).where(RelevanceJudgment.query_id == query_id)

        if not review:
            stmt = stmt.where(RelevanceJudgment.annotator_id == annotator_id)

        return [record(row) for row in session.scalars(stmt.order_by(RelevanceJudgment.created_at))]

    @app.post("/api/v1/judgments", status_code=201)
    def judgment(body: JudgmentInput, session=Depends(db)):
        query = require(session, BenchmarkQuery, body.query_id)

        require(session, Annotator, body.annotator_id)

        if body.passage_id not in {r["passage_id"] for r in query.pool}:
            raise ValueError("Judgments must reference a passage in this query's candidate pool")

        if body.adjudicated:
            sources = list(session.scalars(select(RelevanceJudgment).where(
                RelevanceJudgment.id.in_(body.adjudication_sources),
                RelevanceJudgment.query_id == body.query_id,
                RelevanceJudgment.passage_id == body.passage_id,
                RelevanceJudgment.adjudicated.is_(False),
            )))
            if len(sources) != len(set(body.adjudication_sources)) or len({s.annotator_id for s in sources}) < 2:
                raise ValueError("Adjudication requires source judgments from at least two distinct reviewers of this passage")

        row = RelevanceJudgment(
            query_id=body.query_id,
            passage_id=body.passage_id,
            annotator_id=body.annotator_id,
            relevance=body.relevance,
            ratings={
                k: getattr(body, k)
                for k in (
                    "correctness",
                    "clarity",
                    "usefulness",
                    "status",
                    "supported_interpretations",
                    "section_correct",
                    "evidence_basis",
                    "adjudication_sources",
                )
            },
            notes=body.notes,
            adjudicated=body.adjudicated,
        )

        session.add(row)

        session.commit()

        return record(row)

    @app.get("/api/v1/benchmarks/{benchmark_id}/agreement")
    def agreement_api(benchmark_id: str, session=Depends(db)):
        from .research import agreement_report

        require(session, Benchmark, benchmark_id)

        return agreement_report(session, benchmark_id)

    @app.get("/api/v1/benchmarks/{benchmark_id}/export")
    def benchmark_export(benchmark_id: str, session=Depends(db)):
        queries = benchmark_queries(benchmark_id, session)

        return Response(
            "\n".join(json.dumps(q) for q in queries),
            media_type="application/x-ndjson",
            headers={"Content-Disposition": "attachment; filename=benchmark.jsonl"},
        )

    @app.get("/api/v1/experiments")
    def experiments(session=Depends(db)):
        return [
            record(row)
            for row in session.scalars(select(ExperimentRun).order_by(ExperimentRun.created_at.desc()).limit(100))
        ]

    @app.get("/api/v1/experiments/{experiment_id}/export")
    def experiment_export(experiment_id: str, format: str = "json", session=Depends(db)):
        row = require(session, ExperimentRun, experiment_id)

        if format == "json":
            return Response(
                json.dumps(record(row), indent=2),
                media_type="application/json",
                headers={"Content-Disposition": "attachment; filename=experiment.json"},
            )

        if format != "csv":
            raise ValueError("Export format must be json or csv")

        stream = io.StringIO()

        writer = csv.writer(stream)

        writer.writerow(["variant", "metric", "mean", "low", "high"])

        for variant, result in row.results["variants"].items():
            for metric, value in result["summary"].items():
                if "mean" in value:
                    writer.writerow([variant, metric, value["mean"], value["low"], value["high"]])

        return Response(
            stream.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=metrics.csv"},
        )

    @app.get("/api/v1/optimization-studies")
    def studies(session=Depends(db)):
        return [
            {
                **record(row),
                "trials": [
                    record(t)
                    for t in session.scalars(
                        select(OptimizationTrial)
                        .where(OptimizationTrial.study_id == row.id)
                        .order_by(OptimizationTrial.number)
                    )
                ],
            }
            for row in session.scalars(select(OptimizationStudy))
        ]

    return app


app = create_app()
