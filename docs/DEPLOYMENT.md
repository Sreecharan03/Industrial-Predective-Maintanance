# SenseMinds 360 — Deployment Guide

> **Read [`DEPLOYMENT-STRATEGY-V1.md`](DEPLOYMENT-STRATEGY-V1.md) first** — it is the
> current target architecture (Single Plant, GCE VM + persistent disk) and explains
> *why*. This guide is the step-by-step command reference. Data durability, backups
> and recovery are in [`DATA-GOVERNANCE.md`](DATA-GOVERNANCE.md).

Covers local/VM deployment with Docker Compose, and production deployment on GCP.

---

## 1. What gets deployed

| Component | Image role | Purpose | Required |
|---|---|---|---|
| **postgres** | `timescale/timescaledb:latest-pg16` | Sensor history, findings, knowledge graph, alerts | Yes |
| **migrate** | app image, one-shot | Runs Alembic migrations, then exits | Yes, once per deploy |
| **api** | app image | FastAPI HTTP surface | Yes |
| **dashboard** | nginx + built React | Frontend | Optional (backend works standalone) |
| **worker** | app image, `batch` profile | Periodic analysis of all machines | One of worker/simulator |
| **simulator** | app image, `sim` profile | **Generates synthetic data — demo only** | Never in production |

All Python components are the **same image** with a different command. Build once.

> **Do not run the `sim` profile in production.** It writes fabricated sensor
> readings into the database.

---

## 2. Configuration

Every setting is an environment variable prefixed `SENSEMINDS_`, validated by Pydantic
at startup — a bad config fails immediately and loudly rather than midway through a run.

### Required in any real deployment

| Variable | Notes |
|---|---|
| `SENSEMINDS_DATABASE_URL` | `postgresql+psycopg://user:pass@host:5432/senseminds` |
| `SENSEMINDS_JWT_SECRET` | **Must be changed.** Generate: `openssl rand -hex 32` |
| `SENSEMINDS_DEFAULT_ADMIN_PASSWORD` | **Must be changed.** Seeds the first admin |
| `SENSEMINDS_ENVIRONMENT` | `local` \| `dev` \| `staging` \| `prod` |

### Optional

| Variable | Default | Purpose |
|---|---|---|
| `SENSEMINDS_GROQ_API_KEY` | *(empty)* | Empty ⇒ deterministic offline stub, platform still runs |
| `SENSEMINDS_LLM_MODEL` | `llama-3.3-70b-versatile` | |
| `SENSEMINDS_SMTP_HOST` / `_PORT` / `_USER` / `_PASSWORD` | *(empty)* | Empty ⇒ alerts recorded but not emailed (`status: skipped`) |
| `SENSEMINDS_MAIL_FROM` / `SENSEMINDS_MAIL_TO` | *(empty)* | `MAIL_TO` accepts a comma-separated list |
| `SENSEMINDS_ALERT_REMINDER_MINUTES` | `30` | Re-escalate an unhandled critical |
| `SENSEMINDS_ALERT_COOLDOWN_MINUTES` | `15` | Flapping suppression window |
| `SENSEMINDS_DASHBOARD_URL` | `http://localhost:3000` | Link inside alert emails |
| `SENSEMINDS_WORKER_INTERVAL_SECONDS` | `300` | Worker analysis cadence |
| `SENSEMINDS_LEARNING_INTERVAL_MINUTES` | `30` | Phase-B (ML) cadence |
| `SENSEMINDS_ACCESS_TOKEN_TTL_MINUTES` | `720` | Token lifetime |
| `SENSEMINDS_ARTIFACT_ROOT` | `./artifacts` | **Needs durable storage** — see §5 |

Secrets belong in `deployment/.env` (gitignored) locally, and in **Secret Manager**
on GCP. Never commit them.

---

## 3. Local / VM deployment (Docker Compose)

```bash
cd deployment
cp .env.example .env          # then edit: set JWT secret + admin password
./start.sh sim                # demo, with the synthetic data generator
./start.sh batch              # real analysis worker
./start.sh none               # API only, no data feed
```

`start.sh` waits for Postgres to be genuinely accepting TCP connections, runs
migrations, waits for `/ready`, then starts the chosen feed.

- Dashboard → `http://localhost:3000`
- API → `http://localhost:8000` · docs at `/docs`

### Restarting after a shutdown

Always use `./start.sh`, **never** a bare `docker compose up -d`. On some
filesystems (notably Lightning AI Studios) empty directories are dropped on
shutdown, which deletes Postgres internals such as `pg_notify` and makes the
database refuse to start. `start.sh` recreates them on every boot. Data itself
persists in `senseminds-data/`.

---

## 4. Pre-deployment checklist

Before any internet-facing deployment:

- [x] **Dependencies pinned** — the image builds from `requirements.lock`, and the
      Postgres image is pinned by digest. (Done — see DEPLOYMENT-STRATEGY-V1.md §5.)
- [x] **CORS configurable** — `SENSEMINDS_CORS_ALLOW_ORIGINS`, exact origins.
- [x] **Artifact storage durable** — `LocalDiskArtifactStore` on the persistent
      disk; `ArtifactStore` port ready for GCS later.
- [x] **Database backups + tested restore** — see DATA-GOVERNANCE.md.
- [ ] **`sim` profile not running** — run `--profile batch` (the real worker).
- [ ] **TLS terminated** — Caddy on the v1 VM (automatic on Cloud Run).
- [ ] **`SENSEMINDS_JWT_SECRET` and `SENSEMINDS_DEFAULT_ADMIN_PASSWORD` changed.**
      Deliberately deprioritised for v1; still required before public exposure.

---

## 5. Persistent state

Three things must survive a restart:

1. **Postgres data** — readings, findings, graph, alerts. Compose uses a bind mount
   under `senseminds-data/pgdata`; on GCP use **Cloud SQL**.
2. **Artifacts** (`SENSEMINDS_ARTIFACT_ROOT`) — engine result payloads referenced by
   finding evidence. On a container platform with an ephemeral filesystem
   (**Cloud Run**), a local path is lost on every restart and evidence links break.
   Mount GCS via Cloud Storage FUSE, or run the API on GKE/GCE with a persistent disk.
3. **`.env` / secrets** — Secret Manager in production.

---

## 6. GCP deployment

> **v1 is the GCE VM + persistent disk** (DEPLOYMENT-STRATEGY-V1.md, and §7 below).
> The Cloud Run + Cloud SQL shape shown here is a *future* option for a managed,
> multi-plant deployment — kept for reference. It requires resolving the
> TimescaleDB-on-Cloud-SQL constraint noted below; v1 sidesteps it entirely by
> running TimescaleDB on the VM.

### 6.1 Future managed architecture (reference)

```
              ┌──────────────────────────┐
   HTTPS ────►│  Cloud Run — API         │──► Cloud SQL (PostgreSQL + TimescaleDB)
              │  (autoscaling, TLS)      │──► Secret Manager (JWT, SMTP, Groq)
              └──────────────────────────┘──► GCS bucket (artifacts)
                         ▲
              ┌──────────┴───────────────┐
              │ Cloud Run Job — migrate  │  (run once per deploy)
              │ Cloud Run Job — worker   │  (Cloud Scheduler, every 5 min)
              └──────────────────────────┘
```

Cloud Run gives TLS, autoscaling and IAM without configuration. The API is
stateless, and analysis is idempotent (`UNIQUE(unit, input_hash)`), so **multiple
replicas are safe** — two instances analysing the same input cannot double-write.

> **TimescaleDB note:** Cloud SQL does not offer the TimescaleDB extension. Either
> (a) run PostgreSQL on Cloud SQL and drop the hypertable/compression features, or
> (b) run TimescaleDB on GCE or GKE, or (c) use Timescale Cloud. Verify this before
> committing to an option — migration `0001` creates a hypertable.

### 6.2 Build and push the image

```bash
export PROJECT_ID=your-project
export REGION=asia-south1

gcloud artifacts repositories create senseminds \
  --repository-format=docker --location=$REGION

gcloud builds submit \
  --tag $REGION-docker.pkg.dev/$PROJECT_ID/senseminds/api:v1 .
```

### 6.3 Database

```bash
gcloud sql instances create senseminds-db \
  --database-version=POSTGRES_16 --tier=db-custom-2-7680 \
  --region=$REGION --storage-size=100GB \
  --backup --backup-start-time=02:00

gcloud sql databases create senseminds --instance=senseminds-db
gcloud sql users create senseminds --instance=senseminds-db --password='<STRONG>'
```

### 6.4 Secrets

```bash
openssl rand -hex 32 | gcloud secrets create senseminds-jwt-secret --data-file=-
printf '<STRONG_ADMIN_PW>' | gcloud secrets create senseminds-admin-password --data-file=-
printf '<SMTP_APP_PASSWORD>' | gcloud secrets create senseminds-smtp-password --data-file=-
```

### 6.5 Migrations (run before the API, every deploy)

```bash
gcloud run jobs create senseminds-migrate \
  --image $REGION-docker.pkg.dev/$PROJECT_ID/senseminds/api:v1 \
  --region $REGION \
  --set-cloudsql-instances $PROJECT_ID:$REGION:senseminds-db \
  --command python --args="-m,senseminds.infrastructure.db.migrate" \
  --set-env-vars "SENSEMINDS_DATABASE_URL=postgresql+psycopg://senseminds:<PW>@/senseminds?host=/cloudsql/$PROJECT_ID:$REGION:senseminds-db"

gcloud run jobs execute senseminds-migrate --region $REGION --wait
```

### 6.6 API service

```bash
gcloud run deploy senseminds-api \
  --image $REGION-docker.pkg.dev/$PROJECT_ID/senseminds/api:v1 \
  --region $REGION --platform managed --port 8000 \
  --set-cloudsql-instances $PROJECT_ID:$REGION:senseminds-db \
  --set-env-vars "SENSEMINDS_ENVIRONMENT=prod,SENSEMINDS_DATABASE_URL=postgresql+psycopg://senseminds:<PW>@/senseminds?host=/cloudsql/$PROJECT_ID:$REGION:senseminds-db,SENSEMINDS_SMTP_HOST=smtp.gmail.com,SENSEMINDS_SMTP_PORT=587,SENSEMINDS_MAIL_FROM=...,SENSEMINDS_MAIL_TO=...,SENSEMINDS_DASHBOARD_URL=https://your-dashboard" \
  --set-secrets "SENSEMINDS_JWT_SECRET=senseminds-jwt-secret:latest,SENSEMINDS_DEFAULT_ADMIN_PASSWORD=senseminds-admin-password:latest,SENSEMINDS_SMTP_PASSWORD=senseminds-smtp-password:latest" \
  --min-instances 1 --max-instances 5 \
  --allow-unauthenticated
```

`--min-instances 1` avoids cold starts on the first request of the day.
Use `--no-allow-unauthenticated` and put IAP in front if the API should not be public.

### 6.7 Analysis worker (scheduled)

```bash
gcloud run jobs create senseminds-worker \
  --image $REGION-docker.pkg.dev/$PROJECT_ID/senseminds/api:v1 \
  --region $REGION \
  --set-cloudsql-instances $PROJECT_ID:$REGION:senseminds-db \
  --command python --args="-m,senseminds.workers.analysis_worker" \
  --set-env-vars "SENSEMINDS_DATABASE_URL=...,SENSEMINDS_WORKER_INTERVAL_SECONDS=300" \
  --set-secrets "SENSEMINDS_JWT_SECRET=senseminds-jwt-secret:latest"

gcloud scheduler jobs create http senseminds-worker-tick \
  --schedule "*/5 * * * *" --location $REGION \
  --uri "https://$REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT_ID/jobs/senseminds-worker:run" \
  --http-method POST --oauth-service-account-email <SA>@$PROJECT_ID.iam.gserviceaccount.com
```

Alert emails are dispatched as part of each analysis cycle, so scheduling the worker
also schedules escalation delivery.

### 6.8 Verify the deployment

```bash
API=https://senseminds-api-xxxxx.run.app

curl -s $API/health                       # {"status":"ok",...}
curl -s $API/ready                        # ready  (DB reachable)
TOKEN=$(curl -s -X POST $API/api/v1/auth/token \
  -d "username=admin&password=<ADMIN_PW>" | jq -r .access_token)
curl -s -H "Authorization: Bearer $TOKEN" $API/api/v1/assets | jq length
curl -s -X POST -H "Authorization: Bearer $TOKEN" $API/api/v1/alerts/test   # real email
```

If `/ready` returns non-ready, the database is unreachable — check the Cloud SQL
connection name and that migrations ran.

---

## 7. Alternative: single GCE VM

Simpler, and keeps TimescaleDB:

```bash
gcloud compute instances create senseminds \
  --machine-type=e2-standard-4 --boot-disk-size=200GB \
  --image-family=ubuntu-2204-lts --image-project=ubuntu-os-cloud \
  --tags=http-server,https-server

# on the VM
sudo apt update && sudo apt install -y docker.io docker-compose-plugin git
git clone <repo> && cd SenseMinds360/deployment
cp .env.example .env     # set real secrets
./start.sh batch
```

Then put nginx or a GCP load balancer in front for TLS. Trade-off: you own backups,
patching and uptime; Cloud Run/Cloud SQL handle those for you.

---

## 8. Operations

**Health monitoring** — point uptime checks at `/ready` (not `/health`; `/health`
stays green when the database is down). Scrape `/metrics` for Prometheus.

**Logs** — structured JSON on stdout, so Cloud Logging parses fields directly.
Useful queries: `message="alert_sent"`, `message="analysis_completed"`,
`level="ERROR"`.

**Upgrading** — build a new tag → run the migrate job → deploy the API. Migrations
are forward-only and idempotent.

**Backups** — Cloud SQL automatic backups plus, for a self-managed database:

```bash
docker exec deployment-postgres-1 pg_dump -U senseminds senseminds | gzip > backup.sql.gz
```

**Common failures**

| Symptom | Cause | Fix |
|---|---|---|
| `/ready` not ready | DB unreachable / migrations not run | check URL, run migrate job |
| `401` on every call | JWT secret changed between deploys | re-login; keep the secret stable |
| Alerts stuck `pending` | SMTP unreachable | check `last_error` in `GET /alerts` |
| Alerts `skipped` | SMTP not configured | set the SMTP env vars |
| Findings not updating | no worker running | start the worker job |
| Postgres won't start after reboot | empty dirs dropped by the filesystem | use `./start.sh`, not `docker compose up` |
| Engine output changed after rebuild | unpinned dependencies | pin versions (§4) |
