#!/usr/bin/env bash
# PostgreSQL's consistent snapshot preserves annotations while workers continue.
set -euo pipefail
cd "$(dirname "$0")/.."
backup_root="${1:-artifacts/backups}"
backup_stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="$backup_root/$backup_stamp"
mkdir -p "$backup_dir"
docker compose exec -T db pg_dump -U harmony -d harmonygraph -Fc > "$backup_dir/database.dump.partial"
mv "$backup_dir/database.dump.partial" "$backup_dir/database.dump"
docker compose exec -T api tar -czf - -C /app artifacts > "$backup_dir/reports.tar.gz.partial"
mv "$backup_dir/reports.tar.gz.partial" "$backup_dir/reports.tar.gz"
git rev-parse HEAD > "$backup_dir/source-commit.txt"
git diff --binary HEAD > "$backup_dir/source-changes.patch"
# Capture untracked source additions too; never include .env, installed packages,
# databases or downloaded catalog files. git's ignore rules define the boundary.
git ls-files --others --exclude-standard -z > "$backup_dir/untracked-files.list"
if [[ -s "$backup_dir/untracked-files.list" ]]; then
  tar --null -T "$backup_dir/untracked-files.list" -czf "$backup_dir/untracked-source.tar.gz"
fi
cp compose.yaml "$backup_dir/compose.yaml"
cat > "$backup_dir/README.txt" <<'EOF'
Contains a consistent PostgreSQL snapshot (songs, analyses, benchmarks, judgments,
jobs and experiments), report files, and source revision information.
The database and report archive are captured sequentially; in-flight report files
may change between them. Completed comparison reports are also stored in the DB.
Catalog CSV and environment secrets are excluded. Store this directory on a
separate device or backup service. See docs/local-operations.md for restore steps.
EOF
printf 'Backup saved: %s\n' "$backup_dir"
