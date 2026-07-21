# Data Governance (Deployment Strategy v1)

How SenseMinds 360 keeps data **durable**, **consistent**, and **recoverable**.
Much of this is enforced in the platform itself; this document states the
guarantees, the backup and retention policy, and — importantly — evidence that
recovery actually works.

---

## 1. Durability — data survives any restart

State lives on the **persistent disk**, independent of container and VM lifecycle
(DEPLOYMENT-STRATEGY-V1.md §1). Two independent recovery paths protect it:

| Path | What it is | Cadence | Retention |
|---|---|---|---|
| **Disk snapshots** | Block-level snapshot of the whole persistent disk | Daily (GCP schedule) | 14 days |
| **Logical backups** | Consistent `pg_dump`, gzipped, to a versioned GCS bucket | Nightly | 14 days local + GCS versioning |

Two paths on purpose: a snapshot restores the entire disk fast; a logical dump is
portable and can be restored into any Postgres, at row granularity, anywhere.
Losing one still leaves the other.

The persistent disk itself is created with **auto-delete disabled**, so deleting
or recreating the VM never touches the data.

---

## 2. Consistency — the database cannot be left half-written

These are enforced in code and schema, not by convention:

| Guarantee | Mechanism |
|---|---|
| A finding and its knowledge-graph projection commit together, or not at all | One `AnalysisUnitOfWork` spanning both schemas in a single transaction |
| Re-processing the same input never double-writes | `UNIQUE(unit, input_hash)` on `engine_run`; `INSERT … ON CONFLICT DO NOTHING` |
| Findings cannot be rewritten or deleted | Append-only, enforced by a **database trigger** |
| Engineer verdicts (training labels) cannot be rewritten or deleted | Append-only, enforced by a **database trigger** |
| A dropped connection does not corrupt a write | SQLAlchemy `pool_pre_ping` transparently replaces dead connections; `pool_recycle` retires stale ones |
| A backup is internally consistent even under live writes | `pg_dump` runs in a single transaction snapshot |

The append-only triggers are part of the governance surface: a restore that lost
them would silently lose the guarantee, so restore validation checks they came
back (§4).

---

## 3. Auditability — who and what, over time

- **`engine_run`** records every analysis cycle: input hash, status, timings,
  finding count, engine versions, the identities observed.
- **Findings** carry full provenance (engine, version, input hash, timestamp) and
  are immutable, so the history of what the platform believed is a permanent
  record.
- **Feedback** records each engineer verdict with its author (taken from the
  auth token, never the request body) and timestamp; a changed verdict is a new
  row, so disagreement and revision stay visible.

---

## 4. Recoverability — backups are tested, not assumed

A backup is worthless until a restore has succeeded from it. The policy therefore
includes a **tested restore validation** that runs the real recovery path into a
throwaway database and checks the data came back — without touching production.

`deployment/scripts/validate-restore.sh` restores the latest backup into a
temporary database (created from `template0` so no stale extension interferes),
then asserts the core tables and the append-only trigger are present with
plausible row counts, and drops the temporary database.

### Validated on 21 July 2026 — result

```
validating restore of: senseminds-20260721T080456Z.sql.gz
  ok   application.finding    = 9269   (>= 1)
  ok   application.engine_run = 7712   (>= 1)
  ok   knowledge.kg_node      = 3875   (>= 1)
  ok   application.asset      = 6      (>= 1)
  ok   sensor_history rows    = 764302 (>= 0)
  ok   append-only trigger restored
RESTORE VALIDATION PASSED — this backup is recoverable.
```

**Run it weekly**, and after any change to the database image or backup pipeline.

### What testing the restore caught

The first restore attempts failed — which is precisely why backups must be
tested. Two real, latent defects surfaced:

1. **A floating Postgres image tag.** `latest-pg16` had drifted so the TimescaleDB
   binary (2.28.3) ran ahead of the stored extension (2.28.2). A logical restore
   does `DROP/CREATE EXTENSION`, which spans versions and aborts. **Fix:** the
   Postgres image is now pinned by digest, keeping binary and extension in
   lockstep — the same discipline as `requirements.lock`.
2. **A stale template database.** New databases cloned `template1`, which carried
   the old extension version. **Fix:** validation restores from `template0`
   (extension-free), and TimescaleDB restoring mode is set at the database level
   so the restore connection inherits it.

Neither would have been found without actually running a restore. Both are now
handled and pinned.

---

## 5. Retention and access

- **Backups:** 14 days locally on the disk; GCS bucket versioning retains older
  copies per the bucket lifecycle policy. Adjust `RETENTION_DAYS` in `backup.sh`.
- **Sensor history:** TimescaleDB compression after 7 days (installed policy);
  raw data retained indefinitely unless a retention policy is added later.
- **Access:** the database is not internet-exposed — the GCP firewall opens only
  80/443 (Caddy) and 22 (SSH). `/metrics` is not proxied publicly. Application
  access is JWT-authenticated with role checks.

> Note (tracked separately): auth hardening — rotating the dev JWT secret and
> admin password, refresh tokens, and user management — was explicitly
> deprioritised for v1 and is not part of this governance baseline yet.

---

## 6. Recovery procedures

**Restore a specific backup into the live database** (disaster recovery):

```bash
deployment/scripts/restore.sh /mnt/data/backups/senseminds-<stamp>.sql.gz
# or from GCS:
deployment/scripts/restore.sh gs://<bucket>/senseminds-<stamp>.sql.gz
```

Destructive by design (the dump is `--clean`); it prompts for confirmation.

**Restore the entire disk from a snapshot** (fastest full recovery): create a new
disk from the latest snapshot in the GCP console / `gcloud`, attach it to the VM
at `/mnt/data`, and start the stack. No application steps — the disk *is* the
state.

**Verify after any restore:**

```bash
curl -s localhost:8000/ready         # ready
curl -s localhost:8000/metrics | grep senseminds_findings_total
```
