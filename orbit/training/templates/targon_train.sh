#!/usr/bin/env bash
# Targon container training entrypoint.
#
# Environment variables (required):
#   HF_TOKEN          — HuggingFace authentication token
#   DATASET_HF_REPO   — HF dataset repo (e.g. "user/dataset")
#   DATASET_FILE       — Filename within the repo (e.g. "train.jsonl")
#   SWIFT_CMD          — Full swift CLI command (e.g. "swift sft --config ...")
#
# Optional:
#   HF_BACKUP_REPO    — HF model repo for uploading training log on completion
#
# Phases (written to /tmp/health/status.json for monitoring):
#   setup_start → installing_swift → downloading → deps_verified → training
set -eo pipefail

STATUS_FILE="/tmp/health/status.json"

update_status() { echo "{\"phase\":\"$1\"}" > "$STATUS_FILE"; }

# ── Health check server ──────────────────────────────────────────
mkdir -p /tmp/health
echo ok > /tmp/health/index.html
python3 -m http.server 8080 --directory /tmp/health > /dev/null 2>&1 &
echo '[HEALTH] HTTP health server started on :8080'

update_status "setup_start"
mkdir -p /root/checkpoints /root/data /root/scripts

# ── Install ms-swift ─────────────────────────────────────────────
update_status "installing_swift"
echo '[SETUP] Installing ms-swift...'
pip install ms-swift -U 2>&1 | tail -5

# ── Download data + config from HuggingFace ──────────────────────
update_status "downloading"
echo '[SETUP] Downloading data + config from HF...'
python3 - <<'PYEOF'
import urllib.request, ssl, os, time, json

token = os.environ.get("HF_TOKEN", "")
repo = os.environ["DATASET_HF_REPO"]
dataset_file = os.environ["DATASET_FILE"]
base = f"https://huggingface.co/datasets/{repo}/resolve/main/"
headers = {"Authorization": f"Bearer {token}", "User-Agent": "python"}
ctx = ssl.create_default_context()

files = [
    (dataset_file, "/root/data"),
    ("swift_config.yaml", "/root/scripts"),
]
for fn, dest_dir in files:
    t0 = time.time()
    json.dump({"phase": "downloading", "file": fn},
              open("/tmp/health/status.json", "w"))
    req = urllib.request.Request(base + fn, headers=headers)
    data = urllib.request.urlopen(req, context=ctx, timeout=600).read()
    with open(f"{dest_dir}/{fn}", "wb") as f:
        f.write(data)
    mb = len(data) / 1024 / 1024
    print(f"  Downloaded {fn} ({mb:.1f} MB, {time.time()-t0:.1f}s)")
PYEOF

# ── Verify dataset downloaded ────────────────────────────────────
if [ ! -f "/root/data/${DATASET_FILE}" ]; then
    update_status "fatal"
    echo '[FATAL] Dataset not downloaded'
    exit 1
fi

update_status "deps_verified"

# ── Launch training ──────────────────────────────────────────────
echo '[SETUP] Launching ms-swift training...'
update_status "training"

$SWIFT_CMD 2>&1 | tee /root/training.log
EXIT_CODE=$?
echo "[EXIT] Training exited with code $EXIT_CODE"

# ── Upload training log ──────────────────────────────────────────
if [ -n "${HF_BACKUP_REPO}" ]; then
    python3 -c "
from huggingface_hub import HfApi
import os
api = HfApi(token=os.environ.get('HF_TOKEN', ''))
api.upload_file(
    path_or_fileobj='/root/training.log',
    path_in_repo='training.log',
    repo_id=os.environ['HF_BACKUP_REPO'],
    repo_type='model',
)
print('[LOG] Training log uploaded to HF')
" || true
fi

if [ $EXIT_CODE -eq 0 ]; then
    echo 'TRAINING_COMPLETE'
else
    echo 'TRAINING_FAILED'
    sleep 3600
fi
exit $EXIT_CODE
