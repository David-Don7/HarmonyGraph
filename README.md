# HarmonyGraph

**Find songs through the chords they share.** HarmonyGraph combines a music discovery app with a reproducible research workbench for symbolic harmonic analysis and passage retrieval.

Enter a progression such as `C G Am F` to find matching passages, including songs in another key. Explore the surrounding chord sections, inspect why a passage matched, listen through Spotify, practice the harmony in your browser, and save songs and searches locally. Researchers can open `/studio` to inspect tonal interpretations, annotate benchmark candidates, and compare retrieval methods.

HarmonyGraph works with **chord annotations**, rather than recognizing chords from audio. The consumer app displays named real catalog songs; synthetic fixtures are reserved for the research and testing workflows.

## Contents

- [Features](#features)
- [How it works](#how-it-works)
- [Technology and project structure](#technology-and-project-structure)
- [Start with Docker](#start-with-docker)
- [Native Windows development](#native-windows-development)
- [Search and research workflows](#workflows)
- [Dataset imports](#dataset-imports)
- [Research direction (v2)](#research-direction-v2)
- [Verification](#verification)
- [Operational details](#operational-details)
- [Data attribution and software licensing](#data-attribution-and-software-licensing)

## Features

### Music discovery

- **Search by progression:** match exact chords, the same movement in any key, harmonic function, or a similar progression with missing or extra events.
- **Filter passages:** restrict results by song section, section position, genre, year, local key, and harmonic features.
- **Browse real songs:** explore title/artist search and genre/decade collections backed by the Chordonomicon catalog and provider-resolved metadata.
- **Inspect the evidence:** view matched sections, alternative interpretations, alignment operations, and contributions to the ranking score.
- **Listen and practice:** load Spotify playback on demand or synthesize annotated chords locally with tempo, section looping, and manual stepping. Practice timing is evenly spaced; it is not synchronized to the recording.
- **Keep a local library:** save songs and searches in browser storage without an account.

### Research Studio

- Versioned chord parsing, local-key inference, harmonic interpretations, and positional indexes.
- Independent annotation, preserved judgment history, adjudication, and benchmark revisions.
- Retrieval baselines, ablations, validation-only optimization, frozen evaluation manifests, and JSON/CSV exports.
- An explicit research v2 mode for coherent context-conditioned key/function paths, with retained and omitted probability mass exposed.
- Durable background jobs with progress, cancellation, retries, and interrupted-work recovery.

## How it works

1. **Import chord charts.** The catalog pipeline downloads a pinned Chordonomicon release and stores source records in resumable batches. Research adapters also accept JSONL, Billboard, and Isophonics inputs.
2. **Resolve catalog metadata.** A separate worker uses the supplied Spotify identifiers to obtain names and artwork through Spotify oEmbed. Records that cannot be resolved remain visible in coverage statistics without invented names.
3. **Analyze and index.** The analysis worker parses chords, infers local-key hypotheses, assigns functional alternatives, and builds passage indexes. Completed catalog batches publish immutable search snapshots.
4. **Retrieve and explain.** Indexed evidence proposes candidate passages; a bounded matcher aligns and ranks them. The API returns the matched chords, structural context, score components, and search diagnostics.
5. **Evaluate deliberately.** Studio manages benchmark definitions, judgments, controlled comparisons, and frozen corpus/configuration identities. Model confidence and matching scores are not human relevance probabilities.

The [real-catalog verification report](docs/real-catalog-results.md) records a complete **679,807-chart source import** and a measured subset of **1,032 unique search-ready songs**. These are historical observations, not the coverage of a fresh installation or a claim that the full source is searchable. Metadata resolution and indexing proceed incrementally; inspect `/api/v1/catalog/coverage` for your installation's current status.

## Technology and project structure

| Layer | Technology / responsibility |
| --- | --- |
| Browser | React 19, TypeScript, Vite, TanStack Query, Recharts, Web Audio |
| API and CLI | Python 3.12+, FastAPI, Pydantic, Click |
| Persistence | SQLAlchemy and Alembic; PostgreSQL for Docker, SQLite for native development |
| Analysis and experiments | NumPy, SciPy, scikit-learn, Optuna |
| Packaging and verification | Docker Compose, pytest, Ruff, Playwright, GitHub Actions |

```text
HarmonyGraph/
├── harmonygraph/       # API, CLI, workers, ingestion, analysis, retrieval, research
├── web/                # Consumer app, Studio, generated API types, browser tests
├── migrations/         # Versioned application database migrations
├── tests/              # Backend tests and bounded source-format fixtures
├── scripts/            # Startup, smoke checks, audits, benchmarks, schema export
├── docs/               # Architecture, dataset guides, research specs, measured reports
├── data/demo/          # Original synthetic research fixtures
├── compose.yaml        # PostgreSQL, migrations, API, workers, web, verification profile
└── requirements*.lock  # Pinned Python dependencies
```

Downloaded catalogs, local databases, environment files, generated artifacts, and installed dependencies are excluded from Git. A clone contains the application and documented fixtures; start the catalog pipeline to populate real-song discovery.

Read the [implementation map](docs/architecture.md), [catalog operating guide](docs/real-catalog.md), and [performance/recovery/practice follow-up](docs/improvements.md) for further detail.

## Research direction (v2)

The governing specification is [research proposal v2](docs/research-proposal-v2.md), read together with the [novelty audit](docs/novelty-audit-2026-10-01.md). The implemented alternative ranks passages using coherent context-conditioned key/function paths, preserves omitted probability mass, and keeps the original averaged-key mixture as a baseline. It does not establish human relevance or research superiority.

See [implementation status, measured bounded audit, and remaining gates](docs/research-v2-alignment.md). In Studio, choose **Context paths · research v2** and enter 2–8 Roman numerals. Consumer music search keeps its existing behavior. The legacy `evaluate`/Optuna runner is historical infrastructure; its `proposed` label refers to the old mixture, not v2.

```powershell
.\.venv\Scripts\python.exe scripts/research_v2_local_audit.py
# Uses the existing pinned CSV; writes an isolated eight-chart audit and review packet.
harmonygraph research-v2-audit --song-id <id> --song-id <id> --examples 8
harmonygraph research-v2-compare <benchmark-id> --song-id <development-song-id>
```

No large study, optimization or annotation recruitment starts automatically.

## Start with Docker

Requires Git and Docker Desktop with its Linux engine running. This is the simplest way to run the complete application with PostgreSQL and both background workers.

```powershell
git clone https://github.com/David-Don7/HarmonyGraph.git
cd HarmonyGraph
Copy-Item .env.example .env
docker compose up --build -d
docker compose exec api harmonygraph catalog start
```

Open **http://localhost:8080**. The pinned 679,807-record Chordonomicon release imports in resumable batches; Spotify metadata resolution and harmonic indexing progressively publish real songs. Coverage distinguishes imported records, named songs, and searchable songs. See [real-catalog operation and limitations](docs/real-catalog.md). OpenAPI documentation is at **http://localhost:8000/docs**.

```powershell
docker compose logs -f worker
docker compose exec api harmonygraph catalog status
docker compose exec api harmonygraph search "V7 I" --section chorus --boundary end
```

The CLI `search` command exposes research retrieval. Use the discovery page or `POST /api/v1/catalog/search` to search the consumer catalog. A new installation may initially show no songs while the workers import, resolve, and index data.

| Address | Purpose |
| --- | --- |
| `http://localhost:8080` | Music discovery app |
| `http://localhost:8080/studio` | Research workbench |
| `http://localhost:8000/docs` | Interactive API documentation |
| `http://localhost:8000/api/v1/catalog/coverage` | Live catalog progress and snapshot |

Stop services with `docker compose down`; the named database and artifact volumes retain their data.

Only the web and API are exposed, on localhost. PostgreSQL remains internal. This is a local research application without authentication. Synthetic judgments are constructed test fixtures, never expert labels.

## Native Windows development

Python 3.12 and Node 20.19+ or 22.12+ are required. The fallback database is SQLite. A separate PostgreSQL integration test is provided; its execution status is recorded in the verification report.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.lock
.\.venv\Scripts\python -m pip install --no-deps -e .
.\.venv\Scripts\python -m harmonygraph.cli migrate
.\.venv\Scripts\python -m harmonygraph.cli catalog start
.\.venv\Scripts\python -m harmonygraph.cli serve
```

In a second terminal:

```powershell
.\.venv\Scripts\python -m harmonygraph.jobs
```

For metadata resolution, start another worker terminal with `$env:JOB_KINDS='catalog_metadata'` and the same worker command. The setup script starts both workers automatically.

In a frontend terminal:

```powershell
cd web
npm ci --cache .npm-cache
npm run dev
```

Open **http://127.0.0.1:5173**. Alternatively, `scripts/start.ps1` installs dependencies and starts hidden development processes; `scripts/start.ps1 -Docker` starts Compose.

If ports are occupied, run the API with `serve --port 8010`, set `$env:API_PROXY_TARGET='http://127.0.0.1:8010'`, and run `npm run dev -- --port 5180 --strictPort`. The frontend proxies API calls on its own origin.

## Workflows

**Search:** literal and transposed modes accept chord symbols (`C G Am F`). Functional modes accept Roman numerals (`I V vi IV`, `ii7 V7 Imaj7`, `V7/V V I`, `bVI bVII I`). Separate tokens with spaces, bars, commas, or spaced dashes. Queries contain 1–32 events. Hard filters restrict section, boundary, genre, year, and candidate local key; optional section/boundary preferences affect ranking. Fuzzy matching permits up to two extra or missing events in the candidate window.

**Song explorer:** inspect original events, section boundaries, full local-key posterior data, functional alternatives, harmonic relations, and raw source annotations. Confidence is explicitly model confidence; calibration requires evaluation.

**Benchmark lab:** select or create local annotator profiles, build candidate pools, and assign relevance 0–2 plus optional explanation ratings 1–5. Independent views hide others' judgments. Explicit review mode exposes history and permits adjudication. Every submission is retained. Editing a query creates a new benchmark revision and annotation round, preserving earlier definitions and judgments.

**Experiments:** compare B1–B6 and the proposed configuration; add eight ablations; inspect confidence intervals and export JSON/CSV. Quick web runs use six queries per split. Final test evaluation requires a matching frozen manifest.

## Dataset imports

Place additional research inputs under `data/imports/`. The CLI accepts an explicit local path. `catalog start` explicitly downloads the pinned Chordonomicon release; normal startup never seeds synthetic songs. Use the catalog pipeline for the full release rather than the small-file research adapter shown below.

```powershell
harmonygraph import data/imports/chordonomicon.csv --source chordonomicon --name Chordonomicon --license CC-BY-NC-4.0
harmonygraph import data/imports/McGill-Billboard --source billboard --name Billboard --license CC0-1.0
harmonygraph import data/imports/isophonics/manifest.json --source isophonics --name Isophonics
harmonygraph analyze
```

See [implementation map](docs/architecture.md) for service boundaries, versioning, and retrieval limits.

See [dataset formats](docs/datasets.md) for canonical JSONL, Isophonics manifests, source format details, attribution, and validation behavior. Imports are streaming, resumable by source ID, and idempotent within a fingerprinted release. Changed source files create a distinct dataset release. Check unknown-label counts before conducting experiments.

## Research commands

Use a benchmark ID from the web UI or `GET /api/v1/benchmarks`.

```powershell
harmonygraph evaluate BENCHMARK_ID --split validation
harmonygraph evaluate BENCHMARK_ID --split validation --ablations
harmonygraph optimize BENCHMARK_ID --trials 3
harmonygraph optimize BENCHMARK_ID --research
harmonygraph optimize BENCHMARK_ID --trials 150 --sampler random
harmonygraph freeze BENCHMARK_ID --configuration-id CONFIGURATION_HASH
harmonygraph evaluate BENCHMARK_ID --split test --config selected-config.json
harmonygraph export EXPERIMENT_ID
harmonygraph candidate-audit "V7 I" --section chorus
harmonygraph performance --repeats 10
```

Save a configuration's `parameters` object from `/api/v1/configurations` as `selected-config.json` before evaluating it. A 150-trial research optimization is explicit and potentially expensive. All tuning uses validation data; test feedback is excluded. Transfer slices are available through `evaluate --domain` with a JSON filter object containing genre, year range, or dataset IDs.

Pooled recall is labeled as such. Unjudged results contribute no gain but are counted separately from explicit negative judgments. Missing expert references produce unavailable metrics, not invented numbers. The paper scaffold is [docs/paper.md](docs/paper.md).

## Verification

```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m ruff check harmonygraph tests scripts
.\.venv\Scripts\python scripts/export_openapi.py
cd web
npm run types
npm run build
npx playwright install chromium
npm run test:e2e
```

Consumer browser tests (`music.spec.ts`) require a named, indexed real song. Research browser tests (`workbench.spec.ts`) exercise `/studio` in a separately demo-loaded environment. Set `BASE_URL` when testing a nondefault frontend port. PostgreSQL tests require `TEST_POSTGRES_URL` pointing at a disposable database.

See [verification results](docs/demo-results.md) for checks actually executed in this delivery, rather than treating the presence of a test as proof it passed.

## Verify the Docker deployment

The full local Docker workflow has passed. See [Docker verification results](docs/docker-results.md) for executed checks and measured latency.

For the current consumer workflow, run `python scripts/catalog_smoke.py`. The historical bounded synthetic workflow below is for an isolated research environment:

```powershell
.\.venv\Scripts\python scripts/docker_smoke.py
```

This explicitly runs demo import and reimport, four search modes, all baselines and ablations on six validation queries, a three-trial optimization, and JSON/CSV report export. Results are saved under `artifacts/docker-verification`. It does not start the long research preset.

Run the complete Python suite in a separate verification image and database:

```powershell
docker compose exec db createdb -U harmony harmonygraph_verification
docker compose --profile verification run --build --rm verify
```

Create the verification database only once. Its PostgreSQL checks create and remove their own isolated schemas. Production images omit testing dependencies.

Then check the production web interface:

```powershell
cd web
$env:BASE_URL = 'http://127.0.0.1:8080'
npm run test:e2e
```

## Operational details

| Setting | Purpose |
| --- | --- |
| `POSTGRES_PASSWORD` | Local Compose database password; the example value is a development default |
| `DATABASE_URL` | Backend database connection; native execution defaults to SQLite |
| `DATA_ROOT` | Dataset storage directory (`data` by default) |
| `CATALOG_DATABASE_BUDGET_GB` | Indexing storage budget, 20 GiB by default |
| `JOB_KINDS` | Restrict a worker to selected job types, such as `catalog_metadata` |
| `API_PROXY_TARGET` | Native frontend's API target when using another API port |
| `HARMONY_CA_FILE` | Optional additional trusted CA file for an HTTPS-inspecting network |

Compose reads `.env` for its configured variables. Set native-process environment variables explicitly in PowerShell when overriding defaults, for example `$env:DATABASE_URL = '...'`. Keep real credentials and local environment files out of commits.

Jobs use row locking, leases, a heartbeat, cooperative cancellation, and stale-job recovery. Failed analyses never replace the active version. Cache entries contain immutable per-song snapshots and are bounded to 256 songs / 50,000 events. APIs expose status and timing; worker logs include job IDs. Dataset and experiment jobs perform expensive work offline.

Back up PostgreSQL without PowerShell binary redirection:

```powershell
docker compose exec db pg_dump -U harmony -d harmonygraph -Fc -f /tmp/harmonygraph.dump
docker compose cp db:/tmp/harmonygraph.dump ./harmonygraph.dump
```

Restore into an empty replacement database, after stopping API and worker writes:

```powershell
docker compose cp ./harmonygraph.dump db:/tmp/harmonygraph.dump
docker compose exec db pg_restore -U harmony -d harmonygraph /tmp/harmonygraph.dump
```

Database migrations run before API/worker startup. `harmonygraph index` runs the versioned analysis/index pipeline; a ready matching version is reused. Dependency lockfiles are `requirements.lock`, `requirements-dev.lock`, and `web/package-lock.json`. Application migrations use `harmonygraph_schema_version`; Optuna retains its own version table. Docker report files live in the `artifacts_data` volume and can be copied out with `docker compose cp worker:/app/artifacts ./exported-artifacts`.

## Research boundaries

The implementation is a research prototype with heuristic major/minor harmony rules. Full-corpus scalability, expert-verified relevance, confidence calibration, and scientific superiority remain empirical work. No audio recognition, music generation, embeddings, graph database, cloud deployment, or authenticated team accounts are included.

The word **Graph** refers to inspectable harmonic relationships within the analysis; persistence uses a relational database. Spotify controls recording availability and playback. Imported annotations preserve source limitations, and candidate limits make search approximate. Research v2 remains a bounded, explicitly selected research method; consumer search retains its existing behavior.

## Data attribution and software licensing

The Chordonomicon source release is recorded as **CC BY-NC 4.0** in the catalog provenance. Its pinned revision, checksums, attribution, and import behavior are documented in the [catalog guide](docs/real-catalog.md). Source data is downloaded separately and retains its own terms; the public repository does not bundle the full catalog or song recordings.

Original synthetic demo fixtures are documented as **CC0-1.0**. Additional research datasets retain their respective release terms; see [dataset formats and attribution](docs/datasets.md).

This repository currently has no software `LICENSE` file. Public visibility does not itself grant an open-source software license, and dataset licenses should not be treated as a license for the application code.
