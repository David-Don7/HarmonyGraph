from __future__ import annotations

import json
import logging
import os
import signal
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError
from .contracts import AnalysisConfig
from .db import Job, factory, make_engine, now

log = logging.getLogger("harmonygraph.worker")


class Cancelled(Exception):
    pass


def claim_job(session, owner):
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    session.execute(
        update(Job)
        .where(Job.status == "running", Job.updated_at < cutoff)
        .values(status="queued", owner=None, error="Worker lease expired; retrying idempotent job")
    )
    statement = select(Job).where(Job.status == "queued", Job.updated_at <= now())
    kinds = os.environ.get("JOB_KINDS", "")
    statement = (
        statement.where(Job.kind.in_(kinds.split(","))) if kinds else statement.where(Job.kind != "catalog_metadata")
    )
    job = session.scalar(statement.order_by(Job.updated_at).with_for_update(skip_locked=True).limit(1))
    if job is None:
        session.commit()
        return None
    if job.cancel_requested:
        job.status, job.updated_at = "cancelled", now()
        session.commit()
        return None
    # Compare-and-set also protects local SQLite mode, which does not support row locks.
    changed = session.execute(
        update(Job)
        .where(Job.id == job.id, Job.status == "queued")
        .values(status="running", owner=owner, updated_at=now())
    )
    session.commit()
    return job.id if changed.rowcount else None


def input_path(value):
    root = Path(os.environ.get("DATA_ROOT", "data")).resolve()
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if not path.is_relative_to(root):
        raise ValueError("Import paths must be inside DATA_ROOT")
    if not path.exists():
        raise ValueError(f"Dataset input does not exist: {path.name}")
    return path


def dispatch(session, kind, parameters, progress):
    if kind.startswith("catalog_"):
        from .catalog import dispatch_catalog

        return dispatch_catalog(session, kind, parameters, progress)
    from .analysis import analyze
    from .demo import generate, seed_benchmark
    from .ingestion import ingest
    from .research import evaluate, export_experiment, optimize

    if kind == "demo":
        path = Path(os.environ.get("DATA_ROOT", "data")) / "demo" / "songs.jsonl"
        if not path.exists():
            generate(path)
        result = ingest(
            session, path, "jsonl", "HarmonyGraph original synthetic corpus", "CC0-1.0", lambda p: progress(p * 0.2)
        )
        analysis_id = analyze(session, progress=lambda p: progress(0.2 + p * 0.7))
        benchmark_id = seed_benchmark(session)
        return {**result, "analysis_id": analysis_id, "benchmark_id": benchmark_id}
    if kind == "import":
        return ingest(
            session,
            input_path(parameters["path"]),
            parameters.get("source", "jsonl"),
            parameters.get("name"),
            parameters.get("license", "unspecified"),
            progress,
        )
    if kind == "analyze":
        return {
            "analysis_id": analyze(
                session, AnalysisConfig(**parameters.get("config", {})), parameters.get("activate", True), progress
            )
        }
    if kind == "evaluate":
        return evaluate(
            session,
            parameters["benchmark_id"],
            parameters.get("variants"),
            parameters.get("split", "validation"),
            parameters.get("max_queries"),
            AnalysisConfig(**parameters.get("config", {})),
            parameters.get("rerun", False),
            progress,
            parameters.get("domain"),
            catalog_snapshot=parameters.get("catalog_snapshot"),
        )
    if kind == "optimize":
        return optimize(
            session,
            parameters["benchmark_id"],
            parameters.get("trials", 3),
            parameters.get("seed", 42),
            parameters.get("latency_limit_ms"),
            progress,
            parameters.get("sampler", "tpe"),
            parameters.get("_job_id"),
        )
    if kind == "export":
        return export_experiment(session, parameters["experiment_id"])
    raise ValueError("Unknown job type")


def run_job(sessions, job_id, owner):
    stop = threading.Event()

    def heartbeat():
        while not stop.wait(30):
            with sessions() as session:
                session.execute(
                    update(Job)
                    .where(Job.id == job_id, Job.owner == owner, Job.status == "running")
                    .values(updated_at=now())
                )
                session.commit()

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()

    def progress(value):
        with sessions() as session:
            job = session.get(Job, job_id)
            if job.cancel_requested or job.owner != owner:
                raise Cancelled("Job cancelled or lease reassigned")
            job.progress, job.updated_at = float(value), now()
            session.commit()

    try:
        with sessions() as session:
            job = session.get(Job, job_id)
            kind, parameters = job.kind, {**job.parameters, "_job_id": job_id}
        with sessions() as session:
            result = dispatch(session, kind, parameters, progress)
        progress(1)
        with sessions() as session:
            repeat = result.get("continue", False) if isinstance(result, dict) else False
            delay = 5
            if kind in {"catalog_analyze", "catalog_metadata"} and repeat:
                completed = result.get("indexed_this_batch", result.get("resolved_this_batch", 0))
                delay = 0 if completed else 60
            session.execute(
                update(Job)
                .where(Job.id == job_id, Job.owner == owner)
                .values(
                    status="queued" if repeat else "completed",
                    parameters={k: v for k, v in parameters.items() if k not in {"_job_id", "_transient_retries"}},
                    error=None,
                    result=result,
                    progress=1.0,
                    owner=None,
                    updated_at=(datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat() if repeat else now(),
                )
            )
            session.commit()
        log.info(json.dumps({"event": "job_completed", "job_id": job_id, "kind": kind}))
    except SystemExit:
        with sessions() as session:
            session.execute(
                update(Job)
                .where(Job.id == job_id, Job.owner == owner)
                .values(status="queued", owner=None, updated_at=now())
            )
            session.commit()
        raise
    except Exception as error:
        with sessions() as session:
            job = session.get(Job, job_id)
            if not job or job.owner != owner:
                return
            cancelled = isinstance(error, Cancelled) or job.cancel_requested
            retries = int((job.parameters or {}).get("_transient_retries", 0))
            retry = (
                not cancelled
                and isinstance(error, OperationalError)
                and job.kind.startswith("catalog_")
                and retries < 3
            )
            values = dict(status="cancelled" if cancelled else "failed", error=str(error), updated_at=now())
            if retry:
                values.update(
                    status="queued",
                    owner=None,
                    parameters={**job.parameters, "_transient_retries": retries + 1},
                    updated_at=(datetime.now(timezone.utc) + timedelta(seconds=10 * 2**retries)).isoformat(),
                )
            session.execute(update(Job).where(Job.id == job_id, Job.owner == owner).values(**values))
            session.commit()
        log.exception(json.dumps({"event": "job_retry" if retry else "job_failed", "job_id": job_id}))
    finally:
        stop.set()
        thread.join(timeout=2)


def worker(once=False):
    if threading.current_thread() is threading.main_thread():

        def shutdown(signum, frame):
            raise SystemExit(0)

        signal.signal(signal.SIGTERM, shutdown)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sessions = factory(make_engine())
    owner = str(uuid.uuid4())
    while True:
        with sessions() as session:
            job_id = claim_job(session, owner)
        if job_id:
            run_job(sessions, job_id, owner)
        elif once:
            break
        else:
            time.sleep(2)
        if once:
            break


if __name__ == "__main__":
    worker()
