#!/usr/bin/env bash
# SenseMinds 360 — logical database backup (Deployment Strategy v1).
#
# A consistent pg_dump of the whole database, gzipped, timestamped, uploaded to a
# versioned GCS bucket, with local retention. Run nightly from cron:
#
#   0 2 * * *  /opt/senseminds/deployment/scripts/backup.sh >> /var/log/sm-backup.log 2>&1
#
# This is the LOGICAL backup (portable, restorable anywhere). It complements the
# scheduled persistent-disk SNAPSHOTS configured in provision-vm.sh — two
# independent recovery paths, per the data-governance policy.
#
# pg_dump takes a single consistent snapshot inside one transaction, so the dump
# is internally consistent even while the platform keeps writing.
set -euo pipefail

# ---- configuration (override via environment) -------------------------------
PG_CONTAINER="${PG_CONTAINER:-deployment-postgres-1}"
PG_USER="${PG_USER:-senseminds}"
PG_DB="${PG_DB:-senseminds}"
BACKUP_DIR="${BACKUP_DIR:-/mnt/data/backups}"
GCS_BUCKET="${GCS_BUCKET:-}"                 # e.g. gs://senseminds-backups  (empty = local only)
RETENTION_DAYS="${RETENTION_DAYS:-14}"       # local copies to keep

# Timestamp is passed in / derived without relying on subshell date math elsewhere.
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FILE="${BACKUP_DIR}/senseminds-${STAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "[$(date -u)] starting backup -> ${FILE}"

# ---- dump (consistent snapshot) + integrity check ---------------------------
docker exec "$PG_CONTAINER" pg_dump -U "$PG_USER" --clean --if-exists "$PG_DB" \
  | gzip -c > "$FILE"

# Fail loudly if the gzip is corrupt — a backup that will not decompress is not a
# backup. This is the minimum integrity gate; restore.sh does the real validation.
gzip -t "$FILE"
SIZE="$(stat -c%s "$FILE")"
if [ "$SIZE" -lt 1024 ]; then
  echo "ERROR: backup is suspiciously small (${SIZE} bytes) — aborting" >&2
  exit 1
fi
echo "[$(date -u)] dump ok (${SIZE} bytes, gzip integrity verified)"

# ---- upload to GCS (versioned bucket) ---------------------------------------
if [ -n "$GCS_BUCKET" ]; then
  gsutil cp "$FILE" "${GCS_BUCKET}/"
  echo "[$(date -u)] uploaded to ${GCS_BUCKET}/$(basename "$FILE")"
fi

# ---- local retention --------------------------------------------------------
find "$BACKUP_DIR" -name 'senseminds-*.sql.gz' -mtime "+${RETENTION_DAYS}" -delete
echo "[$(date -u)] backup complete; local retention ${RETENTION_DAYS}d"
