"""Compare the same pinned real passage without overwriting the delivery baseline."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
import numpy as np

BASE = "http://127.0.0.1:8080/api/v1"


def api(path, body=None):
    request = Request(
        BASE + path, data=json.dumps(body).encode() if body else None, headers={"Content-Type": "application/json"}
    )
    with urlopen(request, timeout=180) as response:
        return json.load(response)


def main():
    baseline = json.loads(Path("docs/measured/real-catalog.json").read_text())
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_id": baseline["coverage"]["snapshot_id"],
        "live_coverage": api("/catalog/coverage"),
        "searches": {},
    }
    for mode, old in baseline["searches"].items():
        body = {
            "progression": old["progression"],
            "mode": mode,
            "notation": "chords",
            "limit": 10,
            "catalog_snapshot": report["snapshot_id"],
        }
        samples = []
        for iteration in range(6):
            started = time.perf_counter()
            response = api("/catalog/search", body)
            samples.append((time.perf_counter() - started) * 1000)
            assert response["results"], mode
            assert response["snapshot_id"] == report["snapshot_id"]
            for result in response["results"]:
                assert abs(result["score"] - sum(c["contribution"] for c in result["query_contributions"])) < 1e-9
        report["searches"][mode] = {
            "progression": body["progression"],
            "first_request_ms": samples[0],
            "warm_samples_ms": samples[1:],
            "warm_p95_ms": float(np.quantile(samples[1:], 0.95)),
            "baseline_warm_p95_ms": old["warm_http_p95_ms"],
            "last_stages_ms": response["timings"],
            "candidate_count": response["candidate_count"],
            "candidate_limit_reached": response["candidate_limit_reached"],
        }
        print(mode, round(report["searches"][mode]["warm_p95_ms"], 1), flush=True)
        Path("docs/measured/improvements.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
