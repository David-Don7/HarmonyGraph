# Real-catalog delivery verification

Measured on September 19, 2026, against the running Docker application at `http://localhost:8080`. These results describe the first usable release; enrichment and indexing of the remaining source are still running.

## Catalog coverage

The complete pinned Chordonomicon CSV was imported: **679,807 chart records, zero malformed records**, and 430,323 distinct supplied Spotify track IDs. A chart record is not necessarily a unique song. The source file contains 264,198,044 bytes; its verified SHA-256 is `9d2f4ccdc876a4e816712f128e4772b2af558c2a2923cce5be3a0364fbad9a8d`, at revision `f3a8b678bd65639c01caa342921733f1db01be23`.

At the start of the recorded search benchmark, there were **1,150 named songs and 1,032 unique chord-search-ready songs**, from 1,370 metadata-resolved chart records. The benchmark pins snapshot `8205d63bdfb461bd7ea07ac54c0eb803c910324f03b0bd53482a4bbcfd4e021a`. Processing continued during measurement. A subsequent database check found indexed charts across all 12 available genre labels and 14 decades.

239,523 records were classified as missing identifiers or unavailable metadata at this observation. Remaining unresolved records include pending provider lookups. Unresolved charts remain in raw storage and are not displayed with fabricated titles or artist names. The full source import does **not** mean the entire catalog is named or searchable. Names and artwork are obtained from Spotify oEmbed; chart-to-recording alignment has not been independently expert-verified.

Synthetic research records remain separate and are excluded by consumer API queries, including direct song access and candidate generation. Normal startup does not seed them.

## Search measurements

Each mode received one initial request followed by ten sequential warm HTTP requests for the same three-chord passage from a real song, through the web reverse proxy. Functional and fuzzy modes inferred three alternative query-key interpretations. The raw report retains the progression, candidate-limit diagnostics, individual timings, sample songs, and snapshot identity.

| Search mode | Warm HTTP p95 |
| --- | ---: |
| Exact chords / literal | 688.92 ms |
| Any key / transposed | 602.09 ms |
| Functional with chord input | 4,165.03 ms |
| Similar harmony / fuzzy | 5,270.75 ms |

All four modes returned real named songs, and each displayed score was reconstructed from its stored query contributions. These are small-sample latency observations, not corpus-wide performance claims. Functional and fuzzy search currently exceed the one-second target. Background analysis and metadata processing were active throughout. Candidate generation is bounded; a reached candidate limit means these results are not an exhaustive recall evaluation. No real-corpus relevance or superiority claim is made.

## Throughput and resources

The deployment used an Intel Core i5-12450HX with 12 logical CPUs, Docker Desktop Linux containers under WSL2, a 7.613 GiB Docker memory limit, Python 3.12.14, and PostgreSQL 17.6. The Windows HTTP measurement client used Python 3.12.4.

One analysis worker published 140 chart artifacts between 00:42:37 and 00:44:19 UTC: approximately **81.77 chart artifacts per minute**. Variants are counted separately; this short window must not be extrapolated to a guaranteed full-catalog completion time. The single metadata worker allows four rate-limited in-flight requests, caches repeated IDs, and honors provider retry pauses.

At 00:44:30 UTC, the application database occupied **2,407,459,987 bytes** (about 2.4 GB / 2.24 GiB), including retained research records. A nearby container memory sample recorded API 269.7 MiB, analysis worker 73.21 MiB, metadata worker 79.95 MiB, web 10.51 MiB, and PostgreSQL 2.014 GiB. These are observations, not peak measurements. Storage continues to grow as annotations and indexes are expanded. Analysis has a configurable 20 GiB database budget; reaching it pauses further indexing with an actionable job failure while published search remains available. See the operating guide before increasing that budget.

The import was interrupted and resumed without duplicates. Its final resume attempt recorded 319.823 seconds; this is not the total import duration. Initial TLS failure and cancelled import history remain visible rather than being erased. The completed download/import and currently running analysis/metadata jobs were verified in PostgreSQL.

## Verification executed

- **55 backend tests passed in Docker**, including PostgreSQL migration, indexes, filtering, version isolation, durable jobs, and real-catalog publication tests.
- After the final migration cleanup, all **3 PostgreSQL integration tests passed again**. Native checks passed 52 tests with the 3 PostgreSQL-only tests skipped there.
- **6 browser workflows passed** in an isolated test environment: consumer discovery/search/saving/Spotify fallback/history/mobile/error states, plus research annotation, experiment execution, and report download.
- The final production build passed the **3 consumer browser workflows again** against live real songs.
- TypeScript and Vite production builds, Ruff, and whitespace checks passed. Desktop and mobile presentation were inspected.
- Focused fixtures cover real release notation, date precision, idempotent imports, failed-publication recovery, immutable snapshots, all four retrieval modes, metadata unavailable states, score reconstruction, and synthetic exclusion.

The revised application, PostgreSQL, API, web, analysis worker, and metadata worker are running locally. Full metadata/index completion, exhaustive candidate recall, peak-memory profiling, large-corpus latency, and expert relevance evaluation remain measured follow-up work rather than completed claims.

## Reproduce and inspect

- [Raw HTTP search measurements](measured/real-catalog.json)
- [Runtime, source, and throughput observations](measured/real-catalog-runtime.json)
- [Operation, resume commands, snapshot freezing, and attribution](real-catalog.md)

Run `.venv\Scripts\python scripts/catalog_smoke.py` to produce a new observed report. It uses only the real catalog and does not seed data. Live coverage is available at `/api/v1/catalog/coverage` and in the website's collection-status disclosure.
