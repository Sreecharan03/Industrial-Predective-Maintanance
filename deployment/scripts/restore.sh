#!/usr/bin/env bash
# SenseMinds 360 — restore a database backup (Deployment Strategy v1).
#
#   ./restore.sh /mnt/data/backups/senseminds-20260720T020000Z.sql.gz
#   ./restore.sh gs://senseminds-backups/senseminds-20260720T020000Z.sql.gz
#
# DESTRUCTIVE: the dump was taken with --clean --if-exists, so restoring drops and
# recreates every object. Intended for disaster recovery, not routine use.
#
# For a NON-destructive validation that a backup is genuinely restorable, use
# validate-restore.sh instead — it restores into a throwaway database and checks
# row counts without touching production.
set -euo pipefail

SRC="${1:-}"
PG_CONTAINER="${PG_CONTAINER:-deployment-postgres-1}"
PG_USER="${PG_USER:-senseminds}"
PG_DB="${PG_DB:-senseminds}"

if [ -z "$SRC" ]; then
  echo "usage: $0 <backup.sql.gz | gs://bucket/backup.sql.gz>" >&2
  exit 2
fi

echo "!! This will OVERWRITE the '${PG_DB}' database in container '${PG_CONTAINER}'."
read -r -p "Type the database name to confirm: " confirm
[ "$confirm" = "$PG_DB" ] || { echo "aborted"; exit 1; }

# Resolve GCS sources to a local temp file.
LOCAL="$SRC"
CLEANUP=""
if [[ "$SRC" == gs://* ]]; then
  LOCAL="$(mktemp --suffix=.sql.gz)"
  CLEANUP="$LOCAL"
  gsutil cp "$SRC" "$LOCAL"
fi
trap '[ -n "$CLEANUP" ] && rm -f "$CLEANUP"' EXIT

gzip -t "$LOCAL"   # refuse a corrupt archive before touching the database

# TimescaleDB requires restoring mode for the dump's DROP/CREATE EXTENSION to
# work; set it at the database level so the restore connection inherits it.
echo "restoring ${LOCAL} -> ${PG_DB} ..."
docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d postgres \
  -c "ALTER DATABASE ${PG_DB} SET timescaledb.restoring TO 'on'"
gunzip -c "$LOCAL" | docker exec -i "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB"
docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d postgres \
  -c "ALTER DATABASE ${PG_DB} RESET timescaledb.restoring"

echo "restore complete. Verify:"
docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -tAc \
  "SELECT 'findings='||count(*) FROM application.finding"
