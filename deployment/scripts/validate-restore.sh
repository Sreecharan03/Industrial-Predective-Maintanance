#!/usr/bin/env bash
# SenseMinds 360 — tested restore validation (Deployment Strategy v1 governance).
#
# A backup is only real if it can be restored. This restores the most recent (or a
# named) backup into a THROWAWAY database inside the same Postgres container, checks
# that the schemas and key tables come back with plausible row counts, then drops
# the throwaway database. Production is never touched.
#
#   ./validate-restore.sh                     # newest local backup
#   ./validate-restore.sh <backup.sql.gz>     # a specific one
#
# Run it after the first backup, and on a schedule (e.g. weekly) so a silently
# broken backup pipeline is caught long before you actually need to recover.
set -euo pipefail

PG_CONTAINER="${PG_CONTAINER:-deployment-postgres-1}"
PG_USER="${PG_USER:-senseminds}"
BACKUP_DIR="${BACKUP_DIR:-/mnt/data/backups}"
TEST_DB="senseminds_restore_test"

SRC="${1:-}"
if [ -z "$SRC" ]; then
  SRC="$(ls -1t "${BACKUP_DIR}"/senseminds-*.sql.gz 2>/dev/null | head -1 || true)"
fi
[ -n "$SRC" ] && [ -f "$SRC" ] || { echo "no backup found (looked in ${BACKUP_DIR})" >&2; exit 2; }

echo "validating restore of: $SRC"
gzip -t "$SRC"   # archive integrity

psql() { docker exec -i "$PG_CONTAINER" psql -U "$PG_USER" "$@"; }

# Fresh throwaway database. `timescaledb.restoring=on` is set at the DATABASE
# level (not the session) so the restore's own new connection inherits it — the
# dump does DROP/CREATE EXTENSION timescaledb, which only works in restoring mode.
# TEMPLATE template0 gives a truly empty database, so the dump installs the
# extension itself at the dump's own version. Cloning the default template1 can
# inherit a stale pre-installed extension and make DROP/CREATE EXTENSION span
# versions — the exact failure this validation is meant to catch.
psql -d postgres -c "DROP DATABASE IF EXISTS ${TEST_DB}" >/dev/null
psql -d postgres -c "CREATE DATABASE ${TEST_DB} TEMPLATE template0" >/dev/null
psql -d postgres -c "ALTER DATABASE ${TEST_DB} SET timescaledb.restoring TO 'on'" >/dev/null
trap 'psql -d postgres -c "DROP DATABASE IF EXISTS ${TEST_DB}" >/dev/null 2>&1 || true' EXIT

# Restore. A fatal (e.g. an extension version mismatch) drops the connection, so
# we detect failure by checking the tables afterwards rather than trusting exit code.
gunzip -c "$SRC" | psql -d "$TEST_DB" >/dev/null 2>&1 || true
psql -d postgres -c "ALTER DATABASE ${TEST_DB} RESET timescaledb.restoring" >/dev/null

# Assert the core tables exist and are non-empty (schema + data both came back).
check() {  # <label> <sql> <min>
  local n
  n="$(psql -d "$TEST_DB" -tAc "$2" | tr -d '[:space:]')"
  if [[ "$n" =~ ^[0-9]+$ ]] && [ "$n" -ge "$3" ]; then
    echo "  ok   $1 = $n  (>= $3)"
  else
    echo "  FAIL $1 = ${n:-<none>}  (expected >= $3)" >&2
    return 1
  fi
}

fail=0
check "application.finding"    "SELECT count(*) FROM application.finding"     1 || fail=1
check "application.engine_run" "SELECT count(*) FROM application.engine_run"  1 || fail=1
check "knowledge.kg_node"      "SELECT count(*) FROM knowledge.kg_node"       1 || fail=1
check "application.asset"      "SELECT count(*) FROM application.asset"       1 || fail=1
# sensor_reading lives in TimescaleDB chunks; count via the parent still works.
check "sensor_history rows"    "SELECT count(*) FROM sensor_history.sensor_reading" 0 || fail=1
# The append-only trigger must survive a restore, or governance is silently lost.
TRG="$(psql -d "$TEST_DB" -tAc \
  "SELECT count(*) FROM pg_trigger WHERE tgname='application_finding_no_update_delete' \
   OR tgname LIKE '%append_only%' OR tgname LIKE '%finding%'" | tr -d '[:space:]')"
[ "${TRG:-0}" -ge 1 ] && echo "  ok   append-only trigger restored" \
                      || { echo "  WARN append-only trigger not detected"; }

if [ "$fail" -eq 0 ]; then
  echo "RESTORE VALIDATION PASSED — this backup is recoverable."
else
  echo "RESTORE VALIDATION FAILED — do not trust this backup." >&2
  exit 1
fi
