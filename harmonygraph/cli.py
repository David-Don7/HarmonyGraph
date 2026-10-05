import json
from pathlib import Path
import click
from .contracts import AnalysisConfig, SearchRequest
from .db import factory, make_engine


def output(value):
    click.echo(json.dumps(value, indent=2, default=str))


@click.group()
def main():
    """HarmonyGraph: reproducible harmonic analysis and retrieval."""


@main.command()
def migrate():
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config("alembic.ini"), "head")


@main.command()
def demo():
    """Import the original synthetic corpus, analyze, index, and create its benchmark."""
    from .jobs import dispatch

    with factory(make_engine())() as session:
        output(dispatch(session, "demo", {}, lambda p: None))


@main.command("import")
@click.argument("path", type=click.Path(exists=True))
@click.option("--source", type=click.Choice(["jsonl", "chordonomicon", "billboard", "isophonics"]), default="jsonl")
@click.option("--name")
@click.option("--license", default="unspecified")
def import_data(path, source, name, license):
    from .ingestion import ingest

    with factory(make_engine())() as session:
        output(ingest(session, path, source, name, license))


@main.command("analyze")
@click.option("--config", type=click.Path(exists=True))
@click.option("--no-activate", is_flag=True)
def analyze_command(config, no_activate):
    from .analysis import analyze

    settings = AnalysisConfig(**json.loads(Path(config).read_text())) if config else AnalysisConfig()
    with factory(make_engine())() as session:
        output({"analysis_id": analyze(session, settings, not no_activate)})


main.add_command(analyze_command, "index")


@main.command("search")
@click.argument("progression")
@click.option("--mode", type=click.Choice(["literal", "transposed", "functional", "fuzzy"]), default="functional")
@click.option("--section")
@click.option("--boundary", type=click.Choice(["start", "end", "interior", "adjacent"]))
def search_command(progression, mode, section, boundary):
    from .retrieval import search

    with factory(make_engine())() as session:
        output(
            search(
                session, SearchRequest(progression=progression, mode=mode, section=section, boundary=boundary)
            ).model_dump()
        )


@main.command("evaluate")
@click.argument("benchmark_id")
@click.option("--split", default="validation", type=click.Choice(["train", "validation", "test"]))
@click.option("--max-queries", type=int)
@click.option("--ablations", is_flag=True)
@click.option("--rerun", is_flag=True)
@click.option("--config", type=click.Path(exists=True))
@click.option("--domain", help="JSON object with genre/year/dataset filters")
@click.option("--catalog-snapshot")
def evaluate_command(benchmark_id, split, max_queries, ablations, rerun, config, domain, catalog_snapshot):
    from .research import VARIANTS, evaluate

    cfg = AnalysisConfig(**json.loads(Path(config).read_text())) if config else AnalysisConfig()
    with factory(make_engine())() as session:
        output(
            evaluate(
                session,
                benchmark_id,
                list(VARIANTS) if ablations else None,
                split,
                max_queries,
                cfg,
                rerun,
                domain=json.loads(domain) if domain else None,
                catalog_snapshot=catalog_snapshot,
            )
        )


@main.command("optimize")
@click.argument("benchmark_id")
@click.option("--trials", default=3, type=click.IntRange(1, 300))
@click.option("--research", is_flag=True, help="Run 150 trials")
@click.option("--sampler", type=click.Choice(["tpe", "random"]), default="tpe")
@click.option("--latency-limit-ms", type=float)
def optimize_command(benchmark_id, trials, research, sampler, latency_limit_ms):
    from .research import optimize

    with factory(make_engine())() as session:
        output(
            optimize(
                session, benchmark_id, 150 if research else trials, latency_limit_ms=latency_limit_ms, sampler=sampler
            )
        )


@main.command("freeze")
@click.argument("benchmark_id")
@click.option("--configuration-id")
@click.option("--catalog-snapshot")
def freeze_command(benchmark_id, configuration_id, catalog_snapshot):
    from .research import freeze

    with factory(make_engine())() as session:
        output(freeze(session, benchmark_id, configuration_id, catalog_snapshot))


@main.command("catalog")
@click.argument("action", type=click.Choice(["start", "status", "metadata", "index"]))
def catalog_command(action):
    """Start/resume the real catalog pipeline or show publication coverage."""
    from .catalog import enqueue
    from .db import CatalogSnapshot, record
    from sqlalchemy import select

    with factory(make_engine())() as session:
        if action == "status":
            from .db import CatalogRecord
            from sqlalchemy import func

            snapshot = session.scalar(select(CatalogSnapshot).where(CatalogSnapshot.active.is_(True)))
            output(
                {
                    "imported_records": session.scalar(select(func.count()).select_from(CatalogRecord)),
                    "snapshot": record(snapshot) if snapshot else None,
                }
            )
        else:
            kind = {"start": "catalog_download", "metadata": "catalog_metadata", "index": "catalog_analyze"}[action]
            job = enqueue(session, kind)
            session.commit()
            output(record(job))


@main.command("export")
@click.argument("experiment_id")
@click.option("--directory", default="artifacts")
def export_command(experiment_id, directory):
    from .research import export_experiment

    with factory(make_engine())() as session:
        output(export_experiment(session, experiment_id, directory))


@main.command()
@click.option("--once", is_flag=True)
def worker(once):
    from .jobs import worker as run

    run(once)


@main.command()
@click.option("--port", default=8000)
def serve(port):
    import uvicorn

    uvicorn.run("harmonygraph.api:app", host="127.0.0.1", port=port)


@main.command("candidate-audit")
@click.argument("progression")
@click.option("--mode", default="functional", type=click.Choice(["literal", "transposed", "functional", "fuzzy"]))
@click.option("--section")
def candidate_audit_command(progression, mode, section):
    from .performance import candidate_audit

    with factory(make_engine())() as session:
        output(candidate_audit(session, SearchRequest(progression=progression, mode=mode, section=section)))


@main.command("performance")
@click.option("--repeats", default=10, type=click.IntRange(1, 100))
@click.option("--output-path", default="artifacts/performance.json")
def performance_command(repeats, output_path):
    from .performance import benchmark_performance

    with factory(make_engine())() as session:
        result = benchmark_performance(session, repeats=repeats)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    output(result)


@main.command("research-v2-audit")
@click.option("--song-id", multiple=True, required=True)
@click.option("--analysis-id")
@click.option("--examples", default=8, type=click.IntRange(6, 10))
@click.option("--directory", default="artifacts/research-v2")
def research_v2_audit(song_id, analysis_id, examples, directory):
    """Audit up to 20 analyzed songs and export a blinded review packet."""
    from .research_v2 import bounded_audit, export_packet
    with factory(make_engine())() as session:
        audit, packet = bounded_audit(session, list(song_id), analysis_id=analysis_id, example_count=examples)
    output({"directory": export_packet(directory, audit, packet), "coverage": audit["coverage"], "candidate_audit": audit["candidate_audit"]})


@main.command("research-v2-compare")
@click.argument("benchmark_id")
@click.option("--song-id", multiple=True, required=True)
@click.option("--analysis-id")
@click.option("--path-budget", default=32, type=click.IntRange(1, 256))
@click.option("--annotator-id")
@click.option("--directory", default="artifacts/research-v2")
def research_v2_compare(benchmark_id, song_id, analysis_id, path_budget, annotator_id, directory):
    """Controlled development comparison; held-out test queries are rejected."""
    from .research_v2 import controlled_run
    with factory(make_engine())() as session:
        report = controlled_run(session, benchmark_id, list(song_id), analysis_id=analysis_id, path_budget=path_budget, annotator=annotator_id)
    path = Path(directory) / (report["manifest_hash"] + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise click.ClickException("This frozen manifest already has a report; use a new directory for an explicit rerun")
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    output({"report": str(path.resolve()), "manifest_hash": report["manifest_hash"]})


if __name__ == "__main__":
    main()
