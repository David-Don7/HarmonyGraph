"""Run the complete, bounded synthetic workflow through a running Docker API."""

import argparse
import json
import math
import time
from pathlib import Path
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8080/api/v1")
    parser.add_argument("--output", default="artifacts/docker-verification")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    def api(path, body=None):
        request = Request(
            args.url + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=120) as response:
            return json.load(response)

    def job(kind, parameters):
        started = time.monotonic()
        row = api("/jobs", {"kind": kind, "parameters": parameters})
        previous = None
        while time.monotonic() - started < 1800:
            row = api("/jobs/" + row["id"])
            state = (row["status"], round(row["progress"] * 10))
            if state != previous:
                print(f"{kind}: {row['status']} {row['progress']:.0%}", flush=True)
                previous = state
            if row["status"] == "completed":
                return row
            if row["status"] in {"failed", "cancelled"}:
                raise RuntimeError(json.dumps(row))
            time.sleep(2)
        raise TimeoutError(f"{kind} did not finish within 30 minutes")

    health = api("/health")
    assert health["database"] == "postgresql", health
    demo = job("demo", {})
    repeated = job("demo", {})
    assert repeated["result"]["imported"] == 0 and repeated["result"]["skipped"] == 120
    bid = demo["result"]["benchmark_id"]
    queries = api(f"/benchmarks/{bid}/queries")
    assert len(queries) == 120
    modes = {}
    for mode in ("literal", "transposed", "functional", "fuzzy"):
        request = {
            "progression": "G7 C" if mode in {"literal", "transposed"} else "V7 I",
            "mode": mode,
            "section": "chorus",
            "boundary": "end",
        }
        response = api("/search", request)
        assert response["results"], mode
        first = response["results"][0]
        assert math.isclose(first["score"], sum(c["contribution"] for c in first["components"].values()))
        assert first["evidence"]["event_ids"]
        song = api("/songs/" + first["song_id"])
        assert song["events"] and song["sections"]
        modes[mode] = {
            "count": len(response["results"]),
            "timings": response["timings"],
            "analysis_id": first["analysis_id"],
        }
    variants = [
        "B1_absolute",
        "B2_intervals",
        "B3_global_key",
        "B4_deterministic_local",
        "B5_uniform_edit",
        "B6_manual",
        "proposed",
        "without_uncertainty",
        "without_local_changes",
        "without_functions",
        "without_sections",
        "without_boundaries",
        "uniform_costs",
        "without_quality",
        "equal_weights",
    ]
    comparison = job("evaluate", {"benchmark_id": bid, "variants": variants, "max_queries": 6})
    optimization = job("optimize", {"benchmark_id": bid, "trials": 3})
    eid = comparison["result"]["experiment_id"]
    exported = job("export", {"experiment_id": eid})
    for fmt in ("json", "csv"):
        with urlopen(args.url + f"/experiments/{eid}/export?format={fmt}", timeout=120) as response:
            content = response.read()
            assert content
            (output / f"experiment.{fmt}").write_bytes(content)
    summary = {
        "health": health,
        "demo": demo,
        "idempotent_import": repeated,
        "search_modes": modes,
        "comparison_job": comparison["id"],
        "experiment_id": eid,
        "optimization": optimization,
        "export": exported,
        "overview": api("/overview"),
        "note": "Synthetic validation smoke workflow; not an expert or full-corpus research study.",
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({"status": "passed", "output": str(output.resolve()), "experiment_id": eid}), flush=True)


if __name__ == "__main__":
    main()
