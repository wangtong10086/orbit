#!/usr/bin/env bash
# Targon image-mode training entrypoint.
#
# Assumes the container image already contains Python, ms-swift, and runtime
# dependencies. This script only injects runtime artifacts and launches.
set -eo pipefail

STATUS_FILE="/tmp/health/status.json"
update_status() { echo "{\"phase\":\"$1\"}" > "$STATUS_FILE"; }

mkdir -p /tmp/health /root/checkpoints /root/data /root/scripts
echo ok > /tmp/health/index.html
python3 -m http.server 8080 --directory /tmp/health > /dev/null 2>&1 &

update_status "downloading"
python3 - <<'PYEOF'
import urllib.request, ssl, os, time, json

token = os.environ.get("HF_TOKEN", "")
repo = os.environ["DATASET_HF_REPO"]
dataset_file = os.environ["DATASET_FILE"]
config_file = os.environ.get("CONFIG_FILE", "swift_config.yaml")
base = f"https://huggingface.co/datasets/{repo}/resolve/main/"
headers = {"Authorization": f"Bearer {token}", "User-Agent": "python"}
ctx = ssl.create_default_context()

for filename, dest_dir in [(dataset_file, "/root/data"), (config_file, "/root/scripts")]:
    json.dump({"phase": "downloading", "file": filename}, open("/tmp/health/status.json", "w"))
    req = urllib.request.Request(base + filename, headers=headers)
    data = urllib.request.urlopen(req, context=ctx, timeout=600).read()
    with open(f"{dest_dir}/{filename}", "wb") as handle:
        handle.write(data)
PYEOF

update_status "training"
$SWIFT_CMD 2>&1 | tee /root/training.log
EXIT_CODE=$?

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
" || true
fi

if [ $EXIT_CODE -eq 0 ]; then
    echo 'TRAINING_COMPLETE'
else
    echo 'TRAINING_FAILED'
    sleep 3600
fi
exit $EXIT_CODE
