#!/usr/bin/env bash
# Bring SenseMinds 360 back up after the host (or Studio) has been restarted.
#
# Safe to run any time — it is idempotent. Your data is NOT touched: the database,
# artifacts and live CSVs live on persistent disk ($SM_DATA), not in Docker volumes,
# and the simulator resumes rather than reseeding (SENSEMINDS_SIM_RESET=false).
set -euo pipefail

cd "$(dirname "$0")"

MODE="${1:-sim}"   # sim | batch | none

echo "▸ Bringing up the core stack (postgres · migrate · api · dashboard)…"
docker compose up -d --build

echo "▸ Waiting for the API…"
for _ in $(seq 1 60); do
  if curl -sf http://localhost:8000/ready >/dev/null 2>&1; then break; fi
  sleep 2
done
curl -sf http://localhost:8000/ready >/dev/null 2>&1 \
  && echo "  API ready." \
  || { echo "  API did not come up. Check: docker compose logs api"; exit 1; }

case "$MODE" in
  sim)
    echo "▸ Starting the live 30-second simulator (resumes; does not wipe data)…"
    docker compose --profile sim up -d simulator
    ;;
  batch)
    echo "▸ Starting the batch worker (real historical CSVs)…"
    docker compose --profile batch up -d worker
    ;;
  none)
    echo "▸ No data feed started."
    ;;
  *)
    echo "usage: ./start.sh [sim|batch|none]" >&2; exit 2
    ;;
esac

echo
docker compose ps --format 'table {{.Name}}\t{{.Status}}'
echo
echo "✔ Dashboard  → http://localhost:3000"
echo "✔ API        → http://localhost:8000/health"
echo
echo "  Data on disk: ${SM_DATA:-../../senseminds-data}"
echo "  (On a Lightning Studio, re-expose port 3000 in the right-hand sidebar.)"
