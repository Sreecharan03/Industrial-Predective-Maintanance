# Deployment Strategy v1 — Single Plant

**Status: current target architecture for the first production deployment.**

This is *v1*, not the final architecture. It is deliberately the lowest-risk path
that satisfies the real requirements for one plant: durable state, data
consistency, and operational supportability. Because the application depends only
on abstractions — repositories, an `ArtifactStore` port, and per-store database
URLs — a future multi-plant deployment can migrate to managed services **without
changing application code** (see §7).

---

## 1. Principle: state lives independently of the container lifecycle

The single rule the whole design follows:

> **Containers are stateless. The persistent disk is the source of truth.**

Any container — API, worker, database — can be killed and replaced at any moment.
Nothing durable may live inside one. Three things hold state, and all three are
placed on the persistent disk, independent of any container:

| State | Location on the persistent disk | Survives container/VM restart |
|---|---|---|
| PostgreSQL + TimescaleDB data | `/mnt/data/pgdata` | ✅ |
| Engine artifacts (evidence behind findings) | `/mnt/data/artifacts` | ✅ |
| Backups | `/mnt/data/backups` (+ GCS) | ✅ |
| TLS material | `/mnt/data/caddy` | ✅ |

Secrets live in `deployment/.env` (never committed).

---

## 2. Topology

```
                       Internet
                          │  (only 80/443/22 open — GCP firewall)
                          ▼
                   ┌────────────┐
                   │   Caddy    │  automatic TLS, reverse proxy
                   └────┬───────┘
              /api/*    │    everything else
                   ▼         ▼
              ┌────────┐  ┌───────────┐
              │  API   │  │ dashboard │      (stateless containers)
              └───┬────┘  └───────────┘
                  │
      ┌───────────┼──────────────┐
      ▼           ▼              ▼
 ┌─────────┐ ┌─────────┐   ┌──────────────┐
 │ worker  │ │ Postgres│   │ artifacts    │
 │ (batch) │ │+Timescale   │ (local disk) │
 └─────────┘ └────┬────┘   └──────────────┘
                  │
         ═════════▼═══════════════════════════
              PERSISTENT DISK  /mnt/data
              pgdata · artifacts · backups · caddy
         (separate GCP resource; auto-delete OFF;
          scheduled snapshots; survives VM deletion)
```

Why a GCE VM rather than Cloud Run + Cloud SQL:

- **TimescaleDB stays unchanged.** Cloud SQL does not offer the extension; the VM
  runs the platform's own `timescale/timescaledb` image, so hypertables and
  compression work with no code change.
- **The existing docker-compose stack runs almost as-is** — least new surface,
  least risk to data consistency.
- **Artifacts need no new code.** A persistent disk holds them; the
  `ArtifactStore` abstraction is ready for a `GcsArtifactStore` later, but v1
  does not need one.

---

## 3. What runs

```bash
docker compose -f docker-compose.yml -f docker-compose.gcp.yml \
    --profile batch up -d --build
```

The overlay (`docker-compose.gcp.yml`) adds only Caddy; everything else is the
base stack with `SM_DATA=/mnt/data` pointing all volumes at the persistent disk.

- **`--profile batch` runs the real analysis worker.** This matters: the API only
  *serves* already-computed state. Without a worker (or an explicit
  `POST /analyze`), no new data is ever processed. The worker is what keeps
  analysis and escalation email flowing on the live feed.
- **The simulator is never run in production** — it writes synthetic readings.

---

## 4. First deploy is not automatically populated

A fresh database is empty, so every endpoint returns `[]` until data exists. This
is expected, not a bug. Load data deliberately, once:

- Set `SENSEMINDS_BOOTSTRAP_ON_START=true` (the default) and mount the processed
  CSVs at `/data/datasets`; the worker bootstraps sensor history on first start.
- Or `POST` readings to `/api/v1/readings` from an integration.

Until one of these runs, the API is up but empty. Verify with
`GET /api/v1/assets` returning a non-empty list.

---

## 5. Reproducibility: everything is pinned

The platform's core promise is byte-for-byte reproducible engine output. Two pins
protect it, both discovered to matter during this work:

1. **`requirements.lock`** — exact Python versions (numpy, scipy, scikit-learn,
   pandas and the rest). The image builds from the lock, not from pyproject's
   open `>=` ranges. An unpinned rebuild could pull a newer numerical library and
   silently shift results.
2. **The Postgres image is pinned by digest.** A floating `latest-pg16` tag had
   already drifted — the TimescaleDB binary moved to 2.28.3 while stored data was
   2.28.2, which silently broke logical restore. Pinning keeps binary and
   extension in lockstep. This was caught by actually testing a restore (§6 of
   DATA-GOVERNANCE.md).

---

## 6. Operational supportability

Not a full observability stack — the minimum that makes the deployment
supportable:

| Concern | Mechanism |
|---|---|
| Structured logs | JSON to stdout → Cloud Logging parses fields directly |
| Liveness | `GET /health` (process up) |
| Readiness | `GET /ready` (database reachable) — what Caddy and uptime checks watch |
| Container recovery | `restart: always` on every long-running service |
| Database health | `/metrics`: `senseminds_db_reachable`, connection-pool checkout gauges |
| Resource health | `/metrics`: disk used-ratio (the durability threat), memory, load |
| Data-volume signals | `/metrics`: findings / runs / alerts / KG-node counts |

`/metrics` is **not** exposed publicly through Caddy — finding and run counts are
information; scrape it from inside the VM or a private network.

---

## 7. Why v1 does not lock you in

Every piece that would need to change for a managed, multi-plant deployment is
already behind an abstraction:

| Concern | v1 (single plant) | Future (managed / multi-plant) | Code change? |
|---|---|---|---|
| Database | Postgres+TimescaleDB on the VM | Timescale Cloud, or per-plant instances | **None** — per-store URLs are config |
| Artifacts | `LocalDiskArtifactStore` on the disk | `GcsArtifactStore` | **None** — `ArtifactStore` port + `build_artifact_store` factory |
| Knowledge graph | Postgres `kg_node`/`kg_edge` | Neo4j | **None** — `KnowledgeGraphRepository` port |
| Compute | one VM | Cloud Run / GKE, autoscaled | Config + provisioning only |

The application layer is unaware of any of these choices. v1 is a deployment
decision, not an architectural one.

---

## 8. Provisioning and operation

- `deployment/scripts/provision-vm.sh` — creates the VM, the persistent data disk
  (auto-delete off), a daily snapshot schedule, and a firewall exposing only
  80/443/22.
- `deployment/scripts/backup.sh` — nightly consistent `pg_dump` → GCS.
- `deployment/scripts/validate-restore.sh` — restores into a throwaway database
  and checks it; run weekly.
- `deployment/scripts/restore.sh` — disaster recovery into the live database.

Full backup, retention, and recovery policy: **DATA-GOVERNANCE.md**.
Step-by-step GCP commands: **DEPLOYMENT.md** (VM section).
