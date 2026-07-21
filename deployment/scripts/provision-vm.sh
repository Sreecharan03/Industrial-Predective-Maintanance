#!/usr/bin/env bash
# SenseMinds 360 — provision the GCE VM + persistent disk (Deployment Strategy v1).
#
# Run this from your workstation with gcloud authenticated. It creates:
#   * a persistent data disk that survives VM deletion (the source of truth),
#   * a VM with that disk attached and auto-delete DISABLED,
#   * a scheduled snapshot policy on the data disk (independent recovery path),
#   * a firewall that exposes ONLY 80/443 (Caddy) and 22 (SSH).
#
# Nothing here is destructive to data: the data disk is created empty and never
# deleted by this script. Review the variables, then run.
set -euo pipefail

PROJECT="${PROJECT:?set PROJECT=your-gcp-project}"
ZONE="${ZONE:-asia-south1-a}"
REGION="${REGION:-asia-south1}"
VM_NAME="${VM_NAME:-senseminds}"
MACHINE="${MACHINE:-e2-standard-4}"          # 4 vCPU / 16 GB — analysis is CPU-bound
DATA_DISK="${DATA_DISK:-senseminds-data}"
DATA_DISK_GB="${DATA_DISK_GB:-200}"
DATA_DISK_TYPE="${DATA_DISK_TYPE:-pd-ssd}"

gcloud config set project "$PROJECT"

# 1. Persistent data disk — separate resource from the VM, so it outlives it.
gcloud compute disks create "$DATA_DISK" \
  --size="${DATA_DISK_GB}GB" --type="$DATA_DISK_TYPE" --zone="$ZONE"

# 2. Scheduled snapshots of the data disk (second, independent recovery path
#    alongside the nightly pg_dump). Daily, 14-day retention.
gcloud compute resource-policies create snapshot-schedule senseminds-daily \
  --region="$REGION" --max-retention-days=14 \
  --daily-schedule --start-time=20:00 \
  --on-source-disk-delete=keep-auto-snapshots || true
gcloud compute disks add-resource-policies "$DATA_DISK" \
  --resource-policies=senseminds-daily --zone="$ZONE"

# 3. The VM, with the data disk attached and AUTO-DELETE OFF (deleting the VM
#    must never delete the data).
gcloud compute instances create "$VM_NAME" \
  --zone="$ZONE" --machine-type="$MACHINE" \
  --image-family=ubuntu-2204-lts --image-project=ubuntu-os-cloud \
  --boot-disk-size=30GB \
  --disk="name=${DATA_DISK},device-name=${DATA_DISK},mode=rw,boot=no,auto-delete=no" \
  --tags=http-server,https-server

# 4. Firewall: only Caddy (80/443) and SSH (22) are reachable. The container
#    ports (8000/3000) stay closed to the internet — Caddy is the sole entry point.
gcloud compute firewall-rules create senseminds-web \
  --allow=tcp:80,tcp:443 --target-tags=https-server \
  --source-ranges=0.0.0.0/0 --direction=INGRESS || true

cat <<EOF

VM provisioned. Next, on the VM (ssh in):

  # format + mount the data disk ONCE (skip mkfs if it already has data):
  sudo mkfs.ext4 -F /dev/disk/by-id/google-${DATA_DISK}   # ONLY on first setup
  sudo mkdir -p /mnt/data
  echo '/dev/disk/by-id/google-${DATA_DISK} /mnt/data ext4 discard,defaults 0 2' | sudo tee -a /etc/fstab
  sudo mount /mnt/data
  sudo mkdir -p /mnt/data/{pgdata,artifacts,backups,datasets,caddy}

  # install docker, clone the repo, set deployment/.env (SM_DATA=/mnt/data), then:
  cd SenseMinds360/deployment
  docker compose -f docker-compose.yml -f docker-compose.gcp.yml --profile batch up -d --build

See DEPLOYMENT-STRATEGY-V1.md for the full first-boot checklist.
EOF
