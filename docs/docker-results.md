# Docker verification completed

Verified on 19 September 2026 against a fresh Docker Compose stack and new PostgreSQL volume. The earlier unavailable-engine limitation is resolved.

## Running application

- Web workbench: http://localhost:8080
- API documentation: http://localhost:8000/docs
- PostgreSQL 17.6 runs on the internal Compose network.
- API and database health checks passed. The worker and web container are running. The migration container exited successfully with code 0.
- Data and exported reports persist in the `postgres_data` and `artifacts_data` named volumes. Services use `restart: unless-stopped`.

Start the existing stack again with `docker compose up -d`; stop it without deleting data using `docker compose stop`.

## Executed checks

| Check | Result |
|---|---|
| Fresh image builds and production frontend compilation | Passed |
| Initial PostgreSQL migrations | Passed |
| Complete Python suite in verification container | **43 passed, zero skipped**, 44.28 seconds |
| PostgreSQL migration/index/locking/filter/version/recovery checks | Both passed in isolated schemas of `harmonygraph_verification` |
| Production browser workflows | **3 passed**, 23.3 seconds |
| Demo import and analysis/indexing | 120 songs, 2,388 events, 120 synthetic benchmark queries |
| Reimport | 0 new songs, 120 skipped; no duplicates |
| Four search modes | Results returned; stored contributions reconstruct scores; song timelines available |
| Background experiment run | B1–B6, proposed, and eight ablations completed on six validation queries |
| Background optimization | Three seeded TPE trials completed; study and parameters persisted |
| Background report export | JSON, CSV, Markdown and SVG generated; JSON/CSV download endpoints verified |

The Python test run emitted one non-failing upstream Starlette/httpx deprecation warning. CI was not run remotely; these checks ran locally in Docker and through its published web port.

## Reports and reproducibility

The [Docker workflow summary](measured/docker/summary.json) records job IDs, import counts, search diagnostics, and configuration IDs. The [experiment report](measured/docker/60e3096d-36f1-45e6-b94f-1ff7871b4d3f/report.md) links to its recorded metrics through adjacent `metrics.csv`, `report.json`, and `retrieval.svg` files. The JSON report includes the configuration, split assignments, per-query records, and manifest hashes.

All three trial records are in [optimization-studies.json](measured/docker/optimization-studies.json). Their validation nDCG@10 values were 1.0, 1.0, and 0.6667. These are synthetic smoke results and do not establish research superiority. No long optimization preset or final held-out evaluation was started.

The repeatable workflow driver is `scripts/docker_smoke.py`. The optional Compose `verification` profile builds a separate test image; test dependencies are excluded from production images. Commands are in the README.

## Warm HTTP latency

One warm-up followed by ten serial requests per mode, through the Docker web proxy, on 120 synthetic songs:

| Mode | HTTP median ms | HTTP p95 ms | Application-service p95 ms |
|---|---:|---:|---:|
| literal | 40.1 | 54.6 | 22.1 |
| transposed | 38.9 | 59.4 | 17.1 |
| functional | 66.7 | 105.6 | 59.9 |
| fuzzy | 239.4 | 322.1 | 286.6 |

All four representative warm queries met the one-second p95 target. This is a small demonstration, not a corpus-wide latency guarantee. Initial requests were slower; the initial functional request in the workflow took 1,669 ms in the application service. Full samples and requests are in [warm-latency.json](measured/docker/warm-latency.json). Prior native SQLite measurements remain separately labeled in `demo-results.md`.

Runtime: Docker Desktop 4.89.0, Docker Engine 29.7.2, Linux x86-64 on WSL2 kernel 6.6.87.2, Python 3.12.14, PostgreSQL 17.6. Docker reported approximately 7.6 GiB available memory. The host has 12 logical CPUs; other local workloads were not isolated.

## Remaining research work

Expert annotations, external-corpus validation at scale, calibration findings, transfer studies, long optimization studies, and frozen final-test evaluation remain pending. The delivered Docker software workflow is verified.
