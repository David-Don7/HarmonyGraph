from __future__ import annotations

import csv
import json
import platform
import statistics
from pathlib import Path
import numpy as np
from sqlalchemy import select
from .analysis import analyze, corpus_hash, save_config
from .contracts import AnalysisConfig, SearchRequest, fingerprint
from .db import (
    Benchmark,
    BenchmarkQuery,
    ExperimentRun,
    ModelConfiguration,
    uid,
    OptimizationStudy,
    OptimizationTrial,
    RelevanceJudgment,
    Song,
    SourceAnnotation,
    SplitAssignment,
)
from .metrics import agreement, bootstrap, paired_comparison, retrieval_metrics
from .music import NAMES, roman_features, tokenize
from .retrieval import active_run, search

VARIANTS = {
    "B1_absolute": {},
    "B2_intervals": {},
    "B3_global_key": {"local_keys": False, "uncertainty": False},
    "B4_deterministic_local": {"uncertainty": False},
    "B5_uniform_edit": {"theory_costs": False, "insertion": 1.0, "deletion": 1.0},
    "B6_manual": {},
    "proposed": {},
    "without_uncertainty": {"uncertainty": False},
    "without_local_changes": {"local_keys": False},
    "without_functions": {"functions": False, "functional_weight": 0.0, "chord_weight": 1.0},
    "without_sections": {"sections": False},
    "without_boundaries": {"boundaries": False},
    "uniform_costs": {"theory_costs": False, "insertion": 1.0, "deletion": 1.0},
    "without_quality": {"qualities": False},
    "equal_weights": {"functional_weight": 0.25, "chord_weight": 0.25, "section_weight": 0.25, "boundary_weight": 0.25},
}


def grouped_splits(session, seed=42, song_ids=None):
    statement = select(Song).order_by(Song.id)
    if song_ids is not None:
        statement = statement.where(Song.id.in_(song_ids))
    songs = list(session.scalars(statement))
    parents = {song.id: song.id for song in songs}

    def find(x):
        while parents[x] != x:
            parents[x] = parents[parents[x]]
            x = parents[x]
        return x

    seen = {}
    for song in songs:
        for kind, value in [
            ("artist", song.artist_id),
            ("duplicate", song.duplicate_group),
            ("content", song.content_hash),
        ]:
            if not value:
                continue
            token = (kind, value)
            if token in seen:
                a, b = find(song.id), find(seen[token])
                parents[max(a, b)] = min(a, b)
            seen[token] = song.id
    groups = {}
    for song in songs:
        groups.setdefault(find(song.id), []).append(song.id)
    # Stable group fingerprints, not random database IDs, determine partition assignment.
    lookup = {song.id: song for song in songs}
    ordered = sorted(
        groups.values(),
        key=lambda ids: fingerprint([seed, sorted((lookup[i].source_id, lookup[i].content_hash) for i in ids)]),
    )
    assignments = []
    count = len(ordered)
    for i, ids in enumerate(ordered):
        split = "train" if i < max(1, int(count * 0.6)) else "validation" if i < max(2, int(count * 0.8)) else "test"
        group = fingerprint(sorted(lookup[sid].source_id for sid in ids))
        assignments.extend({"song_id": sid, "group_id": group, "split": split} for sid in ids)
    manifest = fingerprint(
        {
            "corpus": corpus_hash(session, song_ids),
            "seed": seed,
            "assignments": sorted(assignments, key=lambda r: r["song_id"]),
        }
    )
    if not session.scalar(select(SplitAssignment).where(SplitAssignment.manifest == manifest).limit(1)):
        session.add_all([SplitAssignment(manifest=manifest, **row) for row in assignments])
        session.commit()
    return manifest, assignments


def benchmark_hash(session, benchmark_id):
    queries = list(
        session.scalars(
            select(BenchmarkQuery).where(BenchmarkQuery.benchmark_id == benchmark_id).order_by(BenchmarkQuery.id)
        )
    )
    judgments = list(
        session.scalars(
            select(RelevanceJudgment)
            .where(RelevanceJudgment.query_id.in_([q.id for q in queries]))
            .order_by(RelevanceJudgment.id)
        )
    )
    return fingerprint(
        {
            "queries": [
                {
                    "id": q.id,
                    "request": q.request,
                    "judgments": q.synthetic_judgments,
                    "pool": q.pool,
                    "protocol": q.protocol,
                }
                for q in queries
            ],
            "judgments": [
                {
                    "id": j.id,
                    "query": j.query_id,
                    "passage": j.passage_id,
                    "annotator": j.annotator_id,
                    "grade": j.relevance,
                    "adjudicated": j.adjudicated,
                }
                for j in judgments
            ],
        }
    )


def judgments_for(session, query):
    rows = list(
        session.scalars(
            select(RelevanceJudgment)
            .where(RelevanceJudgment.query_id == query.id)
            .order_by(RelevanceJudgment.created_at, RelevanceJudgment.id)
        )
    )
    values = dict(query.synthetic_judgments or {})
    latest, adjudicated = {}, {}
    for row in rows:
        if row.adjudicated:
            adjudicated[row.passage_id] = row.relevance
        else:
            latest[row.passage_id, row.annotator_id] = row.relevance
    passages = {p for p, _ in latest}
    for passage in passages:
        grades = [g for (p, _), g in latest.items() if p == passage and g is not None]
        # A median preserves a disagreement without silently selecting an annotator.
        if grades:
            values[passage] = float(statistics.median(grades))
    values.update(adjudicated)
    return {p: g for p, g in values.items() if g is not None}


def absolute_query(session, query, request):
    if request.mode in {"literal", "transposed"}:
        return request.progression
    source = session.scalar(select(SourceAnnotation).where(SourceAnnotation.song_id == query.source_song_id))
    root = (source.data.get("annotations", {}).get("expected_opening_key", 0) if source else 0) % 12
    labels = []
    for token in tokenize(request.progression):
        f = roman_features(token)
        relative = f["root"]
        if f["target"]:
            relative = (roman_features(f["target"])["root"] + 7) % 12
        quality = "m" if f["quality"] == "minor" else "dim" if f["quality"] == "diminished" else ""
        suffix = "maj7" if f["suffix"] in {"maj7", "M7"} else "7" if f["suffix"] == "7" else ""
        labels.append(NAMES[(root + relative) % 12] + quality + suffix)
    return " ".join(labels)


def snapshot_scope(session, snapshot_id):
    if not snapshot_id:
        return None
    from .db import CatalogSnapshot, CatalogArtifact, CatalogRecord

    snapshot = session.get(CatalogSnapshot, snapshot_id)
    if not snapshot:
        raise ValueError("Catalog snapshot not found")
    return list(
        session.scalars(
            select(CatalogRecord.song_id)
            .join(CatalogArtifact, CatalogArtifact.record_id == CatalogRecord.id)
            .where(CatalogArtifact.analysis_id == snapshot.analysis_id, CatalogArtifact.sequence <= snapshot.sequence)
        )
    )


def frozen_manifest(session, benchmark_id, config_id, analysis_id, split_manifest, snapshot_id=None):
    manifest = {
        "corpus_hash": corpus_hash(session, snapshot_scope(session, snapshot_id)),
        "benchmark_hash": benchmark_hash(session, benchmark_id),
        "split_hash": split_manifest,
        "configuration_hash": config_id,
        "analysis_id": analysis_id,
    }
    if snapshot_id:
        manifest["catalog_snapshot"] = snapshot_id
    return manifest


def freeze(session, benchmark_id, config_id=None, catalog_snapshot=None):
    from .db import CatalogSnapshot

    snapshot = session.get(CatalogSnapshot, catalog_snapshot) if catalog_snapshot else None
    if catalog_snapshot and not snapshot:
        raise ValueError("Catalog snapshot not found")
    run = active_run(session, snapshot.analysis_id if snapshot else None)
    config_id = config_id or run.configuration_id
    config = session.get(ModelConfiguration, config_id)
    if not config:
        raise ValueError("Configuration not found")
    scope = snapshot_scope(session, catalog_snapshot)
    analysis_id = analyze(session, AnalysisConfig(**config.parameters), activate=False, song_ids=scope)
    split_manifest, _ = grouped_splits(session, config.parameters.get("seed", 42), scope)
    manifest = frozen_manifest(session, benchmark_id, config_id, analysis_id, split_manifest, catalog_snapshot)
    if config.frozen and config.freeze_manifest != manifest:
        raise ValueError("This configuration is frozen against different data; create a new configuration version")
    config.frozen = True
    config.freeze_manifest = manifest
    session.commit()
    return manifest


def evaluate(
    session,
    benchmark_id,
    variants=None,
    split="validation",
    max_queries=None,
    config=None,
    rerun=False,
    progress=lambda p: None,
    domain=None,
    query_hook=None,
    catalog_snapshot=None,
):
    if split not in {"train", "validation", "test"}:
        raise ValueError("Choose train, validation, or test")
    benchmark = session.get(Benchmark, benchmark_id)
    if not benchmark:
        raise ValueError("Benchmark not found")
    config = config or AnalysisConfig()
    config_id = save_config(session, config)
    variants = variants or [
        "B1_absolute",
        "B2_intervals",
        "B3_global_key",
        "B4_deterministic_local",
        "B5_uniform_edit",
        "B6_manual",
        "proposed",
    ]
    if any(v not in VARIANTS for v in variants):
        raise ValueError("Unknown experiment variant")
    scope = snapshot_scope(session, catalog_snapshot)
    split_manifest, assignments = grouped_splits(session, config.seed, scope)
    song_ids = {row["song_id"] for row in assignments if row["split"] == split}
    queries = list(
        session.scalars(
            select(BenchmarkQuery).where(BenchmarkQuery.benchmark_id == benchmark_id).order_by(BenchmarkQuery.id)
        )
    )
    queries = [q for q in queries if q.source_song_id in song_ids]
    if domain:
        # Explicit domain filters define cross-domain evaluation slices without changing split ownership.
        from .retrieval import song_filter

        allowed = set(session.scalars(song_filter(select(Song.id), SearchRequest(progression="I", **domain))))
        song_ids &= allowed
        queries = [q for q in queries if q.source_song_id in allowed]
    if max_queries:
        queries = queries[:max_queries]
    if not queries:
        raise ValueError("No benchmark queries in this grouped split/domain; assign source songs before evaluating")
    analysis_id = analyze(session, config, activate=False, song_ids=scope)
    manifest = frozen_manifest(session, benchmark_id, config_id, analysis_id, split_manifest, catalog_snapshot)
    previous = list(
        session.scalars(
            select(ExperimentRun).where(
                ExperimentRun.configuration_id == config_id,
                ExperimentRun.benchmark_id == benchmark_id,
                ExperimentRun.split == "test",
            )
        )
    )
    if split == "test":
        stored = session.get(ModelConfiguration, config_id)
        if not stored.frozen or stored.freeze_manifest != manifest:
            raise ValueError(
                "Freeze this exact configuration, corpus, benchmark, and split before final test evaluation"
            )
        if previous and not rerun:
            raise ValueError("Final test already evaluated; an explicit rerun is required and will be recorded")
    outputs, per_variant = {}, {}
    for variant_index, variant in enumerate(variants):
        base = AnalysisConfig() if variant == "B6_manual" else config
        cfg = base.model_copy(update=VARIANTS[variant])
        variant_analysis = analyze(session, cfg, activate=False, song_ids=scope)
        per_query, latencies = [], []
        for index, query in enumerate(queries):
            request = SearchRequest(**query.request)
            request.analysis_id, request.song_ids, request.limit = variant_analysis, sorted(song_ids), 100
            request.catalog_snapshot = catalog_snapshot
            if variant in {"B1_absolute", "B2_intervals"} and request.pattern == "progression":
                request.progression = absolute_query(session, query, request)
                request.mode = "literal" if variant == "B1_absolute" else "transposed"
            if variant == "B5_uniform_edit":
                request.mode = "fuzzy"
            if not cfg.sections:
                request.preferred_section = None
            if not cfg.boundaries:
                request.preferred_boundary = None
            response = search(session, request, override=cfg)
            labels = {
                pid: grade for pid, grade in judgments_for(session, query).items() if pid.rsplit(":", 2)[0] in song_ids
            }
            metrics = retrieval_metrics([r.passage_id for r in response.results], labels)
            latencies.append(response.timings["total_ms"])
            if query_hook:
                query_hook(index, metrics)
            per_query.append(
                {
                    "query_id": query.id,
                    "category": query.category,
                    "request": request.model_dump(),
                    "judgments": labels,
                    "metrics": metrics,
                    "latency_ms": response.timings["total_ms"],
                    "candidate_limit_reached": response.candidate_limit_reached,
                    "results": [r.passage_id for r in response.results],
                }
            )
            progress((variant_index + (index + 1) / len(queries)) / len(variants))
        summary = {
            metric: bootstrap([p["metrics"].get(metric) for p in per_query], config.seed)
            for metric in per_query[0]["metrics"]
            if metric not in {"unjudged_count", "judged_relevant_pool"}
        }
        summary["latency"] = {
            "median_ms": float(np.median(latencies)),
            "p95_ms": float(np.quantile(latencies, 0.95)),
            "queries_per_second": 1000 / float(np.mean(latencies)),
        }
        outputs[variant] = {"summary": summary, "queries": per_query, "analysis_id": variant_analysis}
        per_variant[variant] = [q["metrics"]["ndcg@10"] for q in per_query]
    comparisons = (
        {
            name: paired_comparison(per_variant["proposed"], values, config.seed)
            for name, values in per_variant.items()
            if name != "proposed"
        }
        if "proposed" in per_variant
        else {}
    )
    from .validation import harmonic_evaluation as evaluate_harmonic_references

    harmonic = evaluate_harmonic_references(session, analysis_id, song_ids, config.top_k)
    result = {
        "variants": outputs,
        "comparisons_to_proposed": comparisons,
        "harmonic_analysis": harmonic,
        "synthetic": benchmark.synthetic,
        "notice": "Synthetic fixture results are software checks, not research evidence."
        if benchmark.synthetic
        else "Metrics use available pooled judgments; unjudged results have zero gain and remain marked unjudged.",
        "domain": domain,
        "test_rerun": bool(previous) if split == "test" else False,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor(),
        },
        "candidate_recall": {
            "available": False,
            "reason": "Requires exhaustive oracle run; use candidate-audit command",
        },
    }
    experiment = ExperimentRun(
        benchmark_id=benchmark_id,
        configuration_id=config_id,
        analysis_id=analysis_id,
        split=split,
        manifest=manifest,
        results=result,
    )
    session.add(experiment)
    session.commit()
    return {"experiment_id": experiment.id, **result}


def optimize(
    session,
    benchmark_id,
    trials=3,
    seed=42,
    latency_limit_ms=None,
    progress=lambda p: None,
    sampler="tpe",
    study_key=None,
):
    import optuna

    if not 1 <= trials <= 300:
        raise ValueError("Trials must be between 1 and 300")
    if sampler not in {"tpe", "random"}:
        raise ValueError("Sampler must be tpe or random")
    study_name = f"harmony-{benchmark_id}-{seed}-{sampler}-{study_key or uid()}"
    row = session.scalar(select(OptimizationStudy).where(OptimizationStudy.name == study_name))
    if row is None:
        row = OptimizationStudy(name=study_name, benchmark_id=benchmark_id)
        session.add(row)
        session.commit()
    url = session.get_bind().url.render_as_string(hide_password=False)
    storage = optuna.storages.RDBStorage(url=url)
    study = optuna.create_study(
        study_name=study_name,
        storage=storage,
        load_if_exists=True,
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=seed) if sampler == "tpe" else optuna.samplers.RandomSampler(seed=seed),
        pruner=optuna.pruners.MedianPruner(n_startup_trials=2),
    )

    for previous in study.trials:
        if previous.state == optuna.trial.TrialState.RUNNING:
            study.tell(previous.number, state=optuna.trial.TrialState.FAIL, skip_if_finished=True)

    def objective(trial):
        config = AnalysisConfig(
            window=trial.suggest_int("window", 4, 16),
            change_penalty=trial.suggest_float("change_penalty", 0.1, 3),
            top_k=trial.suggest_int("top_k", 1, 5),
            functional_weight=trial.suggest_float("functional_weight", 0.2, 0.8),
            chord_weight=trial.suggest_float("chord_weight", 0, 0.5),
            section_weight=trial.suggest_float("section_weight", 0, 0.4),
            boundary_weight=trial.suggest_float("boundary_weight", 0, 0.4),
            insertion=trial.suggest_float("insertion", 0.1, 1),
            deletion=trial.suggest_float("deletion", 0.1, 1),
            substitution=trial.suggest_float("substitution", 0, 1),
            confidence_threshold=trial.suggest_float("confidence_threshold", 0.3, 0.9),
            candidate_limit=trial.suggest_int("candidate_limit", 100, 5000, log=True),
            seed=seed,
        )
        partial_scores = []

        def report_partial(index, metrics):
            value = metrics["ndcg@10"]
            if value is not None:
                partial_scores.append(value)
                trial.report(float(np.mean(partial_scores)), index)
                if trial.should_prune():
                    raise optuna.TrialPruned()

        result = evaluate(
            session,
            benchmark_id,
            variants=["proposed"],
            split="validation",
            config=config,
            max_queries=None if trials >= 100 else 6,
            query_hook=report_partial,
            progress=lambda p: progress(min(1.0, (trial.number + p) / trials)),
        )
        queries = result["variants"]["proposed"]["queries"]
        scores = []
        for query in queries:
            value = query["metrics"]["ndcg@10"]
            if value is not None:
                scores.append(value)
        if not scores:
            raise ValueError("Validation benchmark has no judged relevant results")
        latency = result["variants"]["proposed"]["summary"]["latency"]["p95_ms"]
        trial.set_user_attr("p95_ms", latency)
        trial.set_user_attr("configuration_id", fingerprint(config.model_dump()))
        if latency_limit_ms and latency > latency_limit_ms:
            trial.set_user_attr("feasible", False)
            return -1.0
        trial.set_user_attr("feasible", True)
        return float(np.mean(scores))

    def callback(study, trial):
        session.add(
            OptimizationTrial(
                study_id=row.id, number=trial.number, parameters=trial.params, value=trial.value, state=trial.state.name
            )
        )
        session.commit()

    finished = sum(t.state in {optuna.trial.TrialState.COMPLETE, optuna.trial.TrialState.PRUNED} for t in study.trials)
    study.optimize(objective, n_trials=max(0, trials - finished), callbacks=[callback])
    row.summary = {
        "feasible": study.best_trial.user_attrs.get("feasible", True),
        "best_value": study.best_value if study.best_trial.user_attrs.get("feasible", True) else None,
        "best_parameters": study.best_params,
        "configuration_id": study.best_trial.user_attrs["configuration_id"]
        if study.best_trial.user_attrs.get("feasible", True)
        else None,
        "trials": len(study.trials),
        "split": "validation",
        "sampler": sampler,
        "seed": seed,
    }
    session.commit()
    return {"study_id": row.id, **row.summary}


def agreement_report(session, benchmark_id):
    rows = list(
        session.scalars(
            select(RelevanceJudgment)
            .join(BenchmarkQuery)
            .where(BenchmarkQuery.benchmark_id == benchmark_id, RelevanceJudgment.adjudicated.is_(False))
            .order_by(RelevanceJudgment.created_at)
        )
    )
    matrix, ratings = {}, {"correctness": [], "clarity": [], "usefulness": []}
    latest_rows = {(row.query_id, row.passage_id, row.annotator_id): row for row in rows}
    for row in latest_rows.values():
        if row.relevance is not None:
            matrix.setdefault(f"{row.query_id}:{row.passage_id}", {})[row.annotator_id] = row.relevance
        for kind, values in ratings.items():
            if row.ratings.get(kind) is not None:
                values.append(row.ratings[kind])
    return {
        **agreement(matrix),
        "disagreements": [
            {"item": item, "grades": values} for item, values in matrix.items() if len(set(values.values())) > 1
        ],
        "explanation_ratings": {kind: bootstrap(values) for kind, values in ratings.items()},
    }


def export_experiment(session, experiment_id, directory="artifacts"):
    experiment = session.get(ExperimentRun, experiment_id)
    if not experiment:
        raise ValueError("Experiment not found")
    root = Path(directory) / experiment.id
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": experiment.id,
        "manifest": experiment.manifest,
        "results": experiment.results,
        "split": experiment.split,
        "created_at": experiment.created_at,
        "configuration": session.get(ModelConfiguration, experiment.configuration_id).parameters,
        "split_assignments": [
            {"song_id": a.song_id, "group_id": a.group_id, "split": a.split}
            for a in session.scalars(
                select(SplitAssignment).where(SplitAssignment.manifest == experiment.manifest["split_hash"])
            )
        ],
    }
    (root / "report.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with (root / "metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["variant", "metric", "mean", "ci_low", "ci_high", "n"])
        for variant, results in experiment.results["variants"].items():
            for metric, value in results["summary"].items():
                if "mean" in value:
                    writer.writerow([variant, metric, value["mean"], value["low"], value["high"], value["n"]])
    rows = []
    for variant, results in experiment.results["variants"].items():
        score = results["summary"]["ndcg@10"]["mean"]
        latency = results["summary"]["latency"]["p95_ms"]
        rows.append(f"| {variant} | {score if score is not None else 'unavailable'} | {latency:.2f} |")
    (root / "report.md").write_text(
        "# HarmonyGraph measured experiment\n\n"
        + experiment.results["notice"]
        + "\n\n| Variant | nDCG@10 | p95 ms |\n|---|---:|---:|\n"
        + "\n".join(rows)
        + "\n\n```json\n"
        + json.dumps(experiment.manifest, indent=2)
        + "\n```\n",
        encoding="utf-8",
    )
    # Self-contained SVG is a portable exported figure, generated solely from measured metrics.
    bars = []
    import html

    for i, (variant, results) in enumerate(experiment.results["variants"].items()):
        value = results["summary"]["ndcg@10"]["mean"] or 0
        y = 45 + i * 36
        bars.append(
            f'<text x="12" y="{y + 17}">{html.escape(variant)}</text><rect x="230" y="{y}" width="{value * 400:.2f}" height="24" fill="#7b5de5"/><text x="650" y="{y + 17}">{value:.3f}</text>'
        )
    (root / "retrieval.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="740" height="{80 + len(bars) * 36}" role="img"><title>Measured nDCG at 10</title><rect width="100%" height="100%" fill="white"/><g font-family="sans-serif" font-size="13"><text x="12" y="24">Measured nDCG@10 — {experiment.split}</text>'
        + "".join(bars)
        + "</g></svg>",
        encoding="utf-8",
    )
    return {"directory": str(root.resolve()), "files": ["report.json", "metrics.csv", "report.md", "retrieval.svg"]}
