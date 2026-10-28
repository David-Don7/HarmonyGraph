#!/usr/bin/env bash
# Native dependencies are optional: Docker builds both application runtimes.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -f .env ]]; then cp .env.example .env; fi
docker compose config --quiet
docker compose up --build -d --wait --wait-timeout 180
docker compose exec -T api harmonygraph catalog start
printf '%s\n' 'HarmonyGraph: http://127.0.0.1:8080' 'Research Studio: http://127.0.0.1:8080/studio'
