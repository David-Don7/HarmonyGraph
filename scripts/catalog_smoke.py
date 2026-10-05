"""Read-only end-to-end checks against the running real-song catalog."""

import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
import numpy as np

BASE = "http://127.0.0.1:8080/api/v1"


def api(path, body=None):
    request = Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=120) as response:
        return json.load(response)


def main():
    coverage = api("/catalog/coverage")
    assert coverage["imported_records"] > 0
    sample = api("/catalog/songs?ready=true&limit=5")["items"]
    assert sample, "Wait for a named real song to finish indexing"
    collections = api("/catalog/collections")
    assert any(c["songs"] for c in collections)
    detail = api("/catalog/songs/" + sample[0]["id"])
    sections = [s for s in detail["sections"] if len(s["events"]) >= 3]
    progression = " ".join(sections[0]["events"][:3])
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "coverage": coverage,
        "environment": {"client_python": platform.python_version(), "client_platform": platform.platform()},
        "sample_songs": [{k: s[k] for k in ("title", "artist", "id", "track_id")} for s in sample],
        "searches": {},
    }
    for mode in ["literal", "transposed", "functional", "fuzzy"]:
        body = {
            "progression": progression,
            "mode": mode,
            "notation": "chords",
            "limit": 10,
            "catalog_snapshot": coverage["snapshot_id"],
        }
        first = api("/catalog/search", body)
        assert first["results"], mode
        for row in first["results"]:
            assert row["song"]["metadata_status"] == "resolved"
            assert abs(row["score"] - sum(c["contribution"] for c in row["query_contributions"])) < 1e-9
        timings = []
        for _ in range(10):
            started = time.perf_counter()
            api("/catalog/search", body)
            timings.append((time.perf_counter() - started) * 1000)
        report["searches"][mode] = {
            "progression": progression,
            "matches": len(first["results"]),
            "candidate_count": first["candidate_count"],
            "candidate_limit_reached": first["candidate_limit_reached"],
            "warm_http_median_ms": float(np.median(timings)),
            "warm_http_p95_ms": float(np.quantile(timings, 0.95)),
            "samples_ms": timings,
        }
    target = Path("docs/measured/real-catalog.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "coverage": coverage,
                "search_p95_ms": {k: round(v["warm_http_p95_ms"], 2) for k, v in report["searches"].items()},
                "report": str(target),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
