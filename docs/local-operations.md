# Local operation and recovery

## Start and stop

On macOS/Linux with Docker Desktop running:

```bash
./scripts/start.sh
```

The script creates `.env` only if absent, builds the application, waits for healthy
services, and resumes the idempotent catalog pipeline. Open `http://127.0.0.1:8080`
or `/studio`; API documentation is at `http://127.0.0.1:8000/docs`.
Windows users can use `scripts/start.ps1 -Docker`.

```bash
docker compose ps
docker compose exec -T api harmonygraph catalog status
docker compose logs --tail 50 worker metadata
docker compose stop
docker compose up -d --wait
```

PostgreSQL and report artifacts use named volumes. `docker compose down` retains
them. `docker compose down -v` deletes them and must not be used for normal stops.
Downloaded source charts are under `data/chordonomicon` on the host. Catalog
metadata resolution runs incrementally; imported rows, named songs and searchable
songs are different counts. Full import is not complete metadata coverage.

## Back up research evidence

```bash
./scripts/backup.sh
# Or provide a destination on another mounted device:
./scripts/backup.sh /path/to/backup-directory
```

Each backup includes a consistent PostgreSQL dump (including annotations, jobs,
analyses and experiment reports), an archive of artifact reports, source revision,
tracked changes and untracked source files. The dump and report archive are taken
sequentially. In-flight report files can change between them; completed v2 reports
also reside in the database. `.env` secrets, installed dependencies and the
redownloadable catalog CSV are excluded. Keep backups on a separate device or
backup service; a copy on the same laptop does not protect against device loss.
Codex chat history is not part of these backups.

## Restore to an empty installation

Use the recorded source commit and source patch/additions, recreate `.env`, then:

```bash
docker compose build
docker compose up -d db
# Wait until docker compose ps reports db healthy.
docker compose exec -T db pg_restore -U harmony -d harmonygraph \
  --clean --if-exists --no-owner < /path/to/backup/database.dump
# Restore reports into the artifact volume before resuming workers:
docker compose run --rm --no-deps -T api \
  tar -xzf - -C /app < /path/to/backup/reports.tar.gz
docker compose up -d --wait
docker compose exec -T api harmonygraph catalog start
```

Restore replaces target database contents. Use a fresh installation or back up the
target first. Do not restore while API or workers are running. Native SQLite data
is separate from Docker's PostgreSQL database and is not restored by these commands.

## Verification

```bash
docker compose --profile verification build verify
# Create this disposable database once if it does not already exist:
docker compose exec -T db createdb -U harmony harmonygraph_verification
docker compose --profile verification run --rm verify
cd web
npm ci
npx playwright install chromium
BASE_URL=http://127.0.0.1:8080 npm run test:e2e -- music.spec.ts study.spec.ts
```

These browser checks use real indexed songs. The study scenario creates a clearly
labelled synthetic software-check benchmark and leaves it for inspection. The old
workbench scenarios that seed demo experiments or reanalyze the complete corpus
belong in an isolated demo environment, not a growing real-catalog installation.
