# Performance, reliability, and playback improvements

This follow-up addresses the limitations observed in the real-song release. It does not claim that every source record can now be identified or that the entire release has finished indexing.

## What changed

- Exact and transposed search require the full progression in the position index before fetching song evidence. Broad partial matches no longer consume that mode's candidate budget.
- Search reads evidence in batches of 32 songs, shares it across query-key alternatives, and caches immutable passage interpretation beams with a fixed capacity. PostgreSQL uses a covering index, bounded ordered lookups, and memoized visibility checks. The candidate limit is unchanged and remains exposed in responses.
- Harmonic analysis reuses chord-key evidence and transition matrices. A golden posterior regression test verifies the previous values, duration weighting, and repeatability.
- Metadata resolution bulk-reads cached identities and continuously replenishes four request slots, retaining the existing request rate and provider cooldown handling. Productive jobs continue without an artificial inter-batch pause.
- Catalog jobs retry transient database failures up to three times. Cancelled jobs stay cancelled. Saved checkpoints and committed artifacts survive recovery. The interrupted analysis job observed during deployment was resumed; historical failures remain visible.
- The web proxy refreshes Docker service addresses, fixing stale upstream addresses after API replacement. Configuration validation and an API-only restart followed by a successful proxied health check were executed.
- Song pages provide **Hear the harmony**: a local, browser-generated chord-practice player with adjustable tempo, beats per chord, section looping, and manual stepping. It requires no Spotify connection. Slash basses, extensions, and omitted tones use the same chord parser as search; unknown symbols are silent and marked. Navigation, a hidden tab, or Spotify playback stops practice.

## Verification and measurements

The full Docker backend suite passed **60 tests**, including PostgreSQL. The native run passed 57, with the three PostgreSQL tests skipped there and executed in Docker. Production browser checks passed **four workflows**, including practice playback with Spotify requests deliberately blocked. TypeScript/Vite production builds, Ruff, and Nginx configuration validation passed.

After the final PostgreSQL memoization change, the eight focused database and scaling regression tests passed again. All four search modes were then exercised through the deployed web proxy, and returned scores were reconstructed successfully.

The HTTP comparison script uses the same `D A G` passage and immutable 1,032-song snapshot as the first release. It records the first request separately, then five warm requests per mode, with scores reconstructed from their contributions. The first release used ten warm samples. Both are small observational samples, not controlled research benchmarks or guarantees for arbitrary queries. The total live database has continued growing, and background processing competes for the same hardware. No complete-response cache is used to manufacture the timing improvement.

See [raw final HTTP measurements](measured/improvements.json), [processing observations](measured/improvement-runtime.json), and the [original delivery measurements](measured/real-catalog.json). `scripts/benchmark_improvements.py` reruns the pinned comparison without changing the original baseline report.

Final observed warm HTTP p95, recorded September 19, 2026 at 01:31 UTC:

| Mode | Original delivery | After this pass | First request after restart |
| --- | ---: | ---: | ---: |
| Exact chords | 688.92 ms | 89.69 ms | 786.09 ms |
| Any key | 602.09 ms | 169.65 ms | 954.21 ms |
| Functional | 4,165.03 ms | 2,017.70 ms | 3,051.16 ms |
| Similar harmony | 5,270.75 ms | 4,878.51 ms | 5,116.33 ms |

Exact and transposed search improved substantially in this sample; functional search also improved. The small fuzzy-search change should not be treated as a reliable general speedup, and **Similar harmony still misses the one-second target**. No corpus-wide latency or relevance improvement has been established. The final timing run had the metadata and analysis workers active, with no simultaneous builds or automated browser test run.

A live coverage check after the benchmark found 5,498 named songs and 3,499 chord-search-ready unique songs, all from the fully imported real release. These counts continue changing. The separate runtime observation recorded about 5.0 GB of database storage and 75.06 chart artifacts per minute over a short loaded interval. That interval is not a controlled throughput comparison and does not establish an improved sustained ingestion rate.

## Limits that remain

The source contains 679,807 chart records and 430,323 distinct Spotify track IDs. **239,523 records have no Spotify track ID**; the checked release has no human-readable title or artist-name columns. The application cannot reliably recover those identities from oEmbed without another trustworthy mapping. Unidentified records remain stored, and synthetic consumer records remain excluded.

The entire named catalog has not finished metadata resolution and indexing. Provider rate limits, database growth, and local hardware still constrain completion. A configurable 20 GiB database budget remains in place; filling it stops further indexing while preserving published search. Removing the budget without providing enough storage would not solve that constraint. Current storage and observed throughput are recorded separately from unique-song counts.

The practice player plays generated chord tones at a chosen even tempo. **It is not the original recording and does not establish recording synchronization.** Chordonomicon provides no reliable event timestamps for this purpose. Original-song listening remains in Spotify's official player or external link, subject to Spotify's availability. Accurate alignment would need a separate timing source or an explicitly scoped audio-alignment workflow.

The maintained Spotify integration follows the documented [oEmbed interface](https://developer.spotify.com/documentation/embeds/reference/oembed). No developer credentials, downloaded recordings, fabricated track names, inferred popularity claims, or expert relevance judgments were added.
