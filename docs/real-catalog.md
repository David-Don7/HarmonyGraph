# Real-song catalog and music discovery

The public website uses only named Chordonomicon records. Research and synthetic fixtures are available separately at `/studio`. Songs saved in the browser do not require an account. Spotify embeds load only after a listening action; Spotify controls playback availability. Chord annotations have event positions, not synchronized audio timestamps.

Song pages also include **Hear the harmony**, a local chord-practice player. It synthesizes the annotated chords in the browser, including slash basses and omitted tones, with adjustable practice tempo, beats per chord, section looping, and manual chord stepping. Unknown symbols are silent and explicitly marked; no-chord symbols are rests. Practice stops when leaving the page, hiding the browser tab, or starting Spotify. Its evenly spaced practice timing is not a recording alignment, and it does not download or host song audio.

Metadata resolution consumes its cache in bulk and keeps four rate-limited request slots continuously occupied instead of waiting for a slow group of responses. Productive catalog batches continue immediately; empty batches back off for 60 seconds. TLS roots, request spacing, and Retry-After handling remain enforced.

Catalog jobs retry transient database connection failures up to three times with increasing delays. A successful batch resets that retry count; cancellation takes precedence. Permanent or repeatedly failing work remains visible as a failed job. Restart it with `catalog index` or `catalog metadata` after resolving the reported problem; committed artifacts are reused.

Search batches candidate evidence in groups of 32 songs and reuses immutable passage interpretations in a bounded cache. Exact and transposed searches require the complete indexed progression before loading song details. PostgreSQL migration `0003` adds section IDs to the covering lookup index and adjusts analysis statistics thresholds for incremental catalog growth. Applying this migration to an existing large catalog can take several minutes and temporarily block background writes; allow it to finish before measuring performance.

## Start and resume

```powershell
docker compose up --build -d
docker compose exec api harmonygraph catalog start
docker compose exec api harmonygraph catalog status
docker compose logs -f worker metadata
```

Open [HarmonyGraph](http://localhost:8080). Starting the catalog is idempotent while its job is queued/running. Completed downloads are reused. Import resumes from a committed CSV record checkpoint, and completed analysis artifacts are reused. `catalog metadata` and `catalog index` enqueue the corresponding resumable stages after a cancellation or failure. Job details and cancellation are available in Studio and `/api/v1/jobs`.

The pinned source is `ailsntua/Chordonomicon`, revision `f3a8b678bd65639c01caa342921733f1db01be23`, file `chordonomicon_v2.csv`. The inspected release has 679,807 chart records. Downloaded source files and their SHA-256 manifests live in `data/chordonomicon/` and are excluded from Git. Dataset fingerprint includes the source checksum, revision, and adapter version. Source licensing is CC BY-NC 4.0; attribution appears on the website and song pages.

The CSV does not contain human-readable titles or artist names. The metadata worker resolves the publisher's Spotify track and artist IDs through the official public oEmbed API. These are provider-resolved names, not expert verification of chart-to-recording alignment. Missing identifiers and unavailable provider records stay unresolved. Identical Spotify track IDs group charts into a consumer song; chart variants remain individually inspectable. Spotify artwork remains at its provider URL, with abstract placeholders when unavailable.

## Processing and resource use

Raw ingestion commits 1,000 rows at a time without expanding chord events. A separate metadata worker selects batches of 250 pending charts, interleaving genre and decade groups. Cached track and artist responses avoid duplicate requests. The single metadata worker permits up to four in-flight requests with separate database sessions. A shared limiter spaces request starts by at least 0.25 seconds; actual throughput is limited by provider response time. HTTP 429 applies a global Retry-After pause. Temporary provider failures retry later without holding up unrelated songs.

One analysis worker materializes and analyzes up to 20 named charts per batch. The first delivery milestone is 1,000 named, searchable songs; processing continues beyond it. Unresolved records remain stored, and their annotations are analyzed after the metadata queue is exhausted. No full-corpus completion time is promised. Coverage reports source records imported, provider-linked tracks, named songs, and unique named songs ready for search separately.

Each committed song artifact has a configuration fingerprint, content hash, analysis ID, and publication sequence. A new immutable snapshot publishes a completed sequence watermark in one transaction. Search captures that snapshot at request start and filters all candidates by its watermark, so later batch publication cannot change the request's corpus. An interrupted analysis resumes committed artifacts and publishes them after recovery; failed indexing does not replace the previous snapshot. Graceful Docker shutdown requeues the current job. An abrupt crash is recovered after the five-minute worker lease expires.

The default 20 GiB database processing budget stops further analysis with an actionable job error before unbounded index growth. Already published songs remain available. Set `CATALOG_DATABASE_BUDGET_GB` after checking the drive holding Docker data, then resume `catalog index`. The source download itself is about 264 MB; expanded annotations and indexes are substantially larger.

Normal research analysis remains separate. To freeze and evaluate against a fixed live-catalog subset, use the `snapshot_id` from `/api/v1/catalog/coverage`:

```powershell
harmonygraph freeze BENCHMARK_ID --catalog-snapshot SNAPSHOT_ID
harmonygraph evaluate BENCHMARK_ID --catalog-snapshot SNAPSHOT_ID --split validation
```

Catalog-scoped split manifests and corpus hashes use only that snapshot's charts. New catalog songs do not alter the frozen subset. Expert relevance judgments are still required for real-corpus research findings; the public catalog does not manufacture them.

## Public interfaces

- `GET /api/v1/catalog/coverage`: imported, named, searchable, unavailable counts and current snapshot.
- `GET /api/v1/catalog/songs`: title/artist substring search, genre, decade, ready-only filtering, limit and cursor pagination.
- `GET /api/v1/catalog/collections`: actual available genre, decade, and searchable-song shelves.
- `GET /api/v1/catalog/songs/{record_id}`: source chord sections, chart variants, metadata and Spotify links; unresolved and non-catalog IDs return 404.
- `POST /api/v1/catalog/search`: original structural filters plus `notation: chords|roman` and optional `catalog_snapshot`. Chord input in fuzzy/functional mode is interpreted through retained query-key hypotheses. Results group passages by Spotify track, retain alignment evidence, and expose probability-weighted query contributions whose sum is the displayed score.

Existing research endpoints are preserved. Consumer visibility is enforced by server queries, including candidate generation. The frontend types for consumer song cards, pages, search requests and results are generated from OpenAPI.

## TLS on this Windows machine

The local antivirus intercepts HTTPS using a certificate already trusted by Windows. Containers do not inherit the Windows trust store. This installation exports only that public certificate to ignored `data/local/network-root.pem`; `HARMONY_CA_FILE` adds it to Python's normal CA roots. Verification and hostname checks remain enabled. Other machines do not need this file unless their own trusted network environment requires an additional CA. Never copy private keys or disable certificate verification.

## Verification

See the [executed real-catalog results](real-catalog-results.md) for actual coverage, throughput, storage, test outcomes, and search timings.

```powershell
.venv\Scripts\python -m pytest -q
docker compose --profile verification run --build --rm verify
$env:BASE_URL='http://127.0.0.1:8080'
npm run test:e2e --prefix web -- music.spec.ts
.venv\Scripts\python scripts/catalog_smoke.py
```

Consumer browser tests require at least one named, indexed real song. Research browser tests use a separately seeded research environment. Neither consumer startup nor the consumer smoke check seeds synthetic data. The smoke report records observed coverage, sample real titles, actual HTTP latency, and environment details; its performance results apply only to the measured published subset.
