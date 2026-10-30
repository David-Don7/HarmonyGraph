"""Offline before/after search benchmark. Does not touch the published catalog.

Run: PYTHONPATH=. .venv/bin/python scripts/benchmark_search_optimization.py \
    --baseline-ref f366256 --output artifacts/search-optimization/comparison.json

Loads the trusted local Git revision's paths.py as the reference implementation.
Both implementations search the same temporary SQLite corpus and candidate pool.
Times cover backend search only, excluding HTTP and response serialization.
"""
import argparse
import json
import statistics
import subprocess
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import patch

from harmonygraph import paths, retrieval
from harmonygraph.analysis import analyze
from harmonygraph.contracts import SearchRequest, fingerprint
from harmonygraph.db import Base, factory, make_engine
from harmonygraph.ingestion import ingest
from harmonygraph.music import NAMES, _cached_alignment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-ref", default="f366256")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    revision = subprocess.check_output(["git", "rev-parse", "--verify", args.baseline_ref + "^{commit}"], text=True).strip()
    source = subprocess.check_output(["git", "show", f"{revision}:harmonygraph/paths.py"], text=True)
    baseline = types.ModuleType("harmonygraph._benchmark_reference")
    baseline.__package__ = "harmonygraph"
    exec(compile(source, "reference/paths.py", "exec"), baseline.__dict__)
    baseline_retrieval = types.ModuleType("harmonygraph._benchmark_retrieval")
    baseline_retrieval.__package__ = "harmonygraph"
    retrieval_source = subprocess.check_output(["git", "show", f"{revision}:harmonygraph/retrieval.py"], text=True)
    exec(compile(retrieval_source, "reference/retrieval.py", "exec"), baseline_retrieval.__dict__)
    cases = [
        ("functional-budget-4", dict(mode="functional", ranking="path_expectation", path_budget=4)),
        ("functional-budget-16", dict(mode="functional", ranking="path_expectation", path_budget=16)),
        ("fuzzy-budget-16", dict(mode="fuzzy", ranking="path_expectation", path_budget=16)),
        ("deterministic", dict(mode="functional", ranking="hard_path", path_budget=64)),
    ]
    report = {"baseline_revision": revision, "synthetic_software_benchmark": True,
              "scope": "12 transposed 72-event charts; up to 500 candidate starts; SQLite; no HTTP",
              "repeats": args.repeats, "cases": []}
    with tempfile.TemporaryDirectory(prefix="harmonygraph-search-benchmark-") as directory:
        root = Path(directory)
        source_file = root / "songs.jsonl"
        progression = [(0, ""), (7, ""), (9, "m"), (5, ""), (2, "m"), (7, "7"), (0, ""), (2, "7")]
        songs = [{"source_id": str(shift), "title": f"Software fixture {shift}", "synthetic": True,
                  "sections": [{"label": f"Chorus {section}", "events": [
                      {"label": NAMES[(pc + shift) % 12] + suffix} for pc, suffix in progression * 3
                  ]} for section in range(3)]} for shift in range(12)]
        source_file.write_text("\n".join(json.dumps(s) for s in songs), encoding="utf-8")
        engine = make_engine(f"sqlite:///{root / 'benchmark.db'}")
        Base.metadata.create_all(engine)
        with factory(engine)() as session:
            ingest(session, source_file)
            analysis_id = analyze(session)
            for name, settings in cases:
                request = SearchRequest(progression="ii V7 I", analysis_id=analysis_id, **settings)
                measured = {}
                payloads = {}
                for label, module, search_module in (("before", baseline, baseline_retrieval),
                                                      ("after", paths, retrieval)):
                    _cached_alignment.cache_clear()
                    search_module._evidence_cache.clear()
                    search_module._cached_events = 0
                    paths._contexts.clear()
                    paths._context_bytes = 0
                    paths._function_options.cache_clear()
                    with patch.dict(sys.modules, {"harmonygraph.paths": module}):
                        cold = search_module.search(session, request)
                        warm = [search_module.search(session, request) for _ in range(args.repeats)]
                    measured[label] = {
                        "cold_ms": cold.timings["total_ms"],
                        "warm_median_ms": statistics.median(r.timings["total_ms"] for r in warm),
                        "warm_rerank_median_ms": statistics.median(r.timings["rerank_ms"] for r in warm),
                        "warm_candidate_median_ms": statistics.median(r.timings["candidate_ms"] for r in warm),
                    }
                    payloads[label] = cold.model_dump(exclude={"timings"})
                    assert all(r.model_dump(exclude={"timings"}) == payloads[label] for r in warm)
                assert payloads["before"] == payloads["after"], f"Search payload changed for {name}"
                report["cases"].append({"name": name, "candidate_count": cold.candidate_count,
                                        "identical_results_and_evidence": True,
                                        "result_fingerprint": fingerprint(payloads["after"]), **measured,
                                        "warm_speedup": measured["before"]["warm_median_ms"] / measured["after"]["warm_median_ms"]})
        engine.dispose()
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
