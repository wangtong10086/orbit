#!/bin/bash
# One-shot setup for training machine (Ubuntu 24.04 + NVIDIA H200)
# Usage: forge remote -m <machine> exec "bash /root/setup.sh"
# Or pipe: cat scripts/setup_train_machine.sh | forge remote -m <machine> exec "bash -s"
set -euo pipefail

echo "=== Affine Training Machine Setup ==="
echo "Date: $(date)"
echo "Host: $(hostname)"
echo "GPUs: $(nvidia-smi -L 2>/dev/null | wc -l)"
echo "======================================"

# ---- 1. System packages ----
echo "[1/7] Installing system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git screen curl wget build-essential > /dev/null 2>&1
echo "  Python: $(python3 --version)"

# ---- 2. Venv + core packages ----
echo "[2/7] Creating venv and installing packages..."
python3 -m venv /root/venv
source /root/venv/bin/activate

# Install torch first (matching CUDA driver)
pip install -q torch torchvision torchaudio

# Install training stack
pip install -q "ms-swift[llm]>=4.0" deepspeed accelerate transformers
pip install -q flash-attn --no-build-isolation 2>/dev/null || echo "  flash-attn build failed (optional, will use sdpa)"
pip install -q sglang[all] huggingface_hub

echo "  torch=$(python3 -c 'import torch; print(torch.__version__)')"
echo "  swift=$(pip show ms-swift 2>/dev/null | grep Version | awk '{print $2}')"
echo "  deepspeed=$(pip show deepspeed 2>/dev/null | grep Version | awk '{print $2}')"

# ---- 3. Directories ----
echo "[3/7] Creating directories..."
mkdir -p /root/{data,models,checkpoints,logs,scripts,configs}

# ---- 4. HF Auth ----
echo "[4/7] Configuring HuggingFace..."
if [ -n "${HF_TOKEN:-}" ]; then
    huggingface-cli login --token "$HF_TOKEN" 2>/dev/null || /root/venv/bin/huggingface-cli login --token "$HF_TOKEN" 2>/dev/null
    echo "  HF login OK"
else
    echo "  WARNING: HF_TOKEN not set, skipping HF login"
fi

# ---- 5. Download model ----
echo "[5/7] Downloading Qwen3-32B model..."
if [ -d "/root/models/Qwen3-32B" ] && [ -f "/root/models/Qwen3-32B/config.json" ]; then
    echo "  Model already exists, skipping"
else
    /root/venv/bin/huggingface-cli download Qwen/Qwen3-32B --local-dir /root/models/Qwen3-32B --repo-type model 2>&1 | tail -3
    echo "  Model downloaded: $(ls /root/models/Qwen3-32B/*.safetensors | wc -l) shards"
fi

# ---- 6. Download training data ----
echo "[6/7] Downloading training data..."
# Download all canonical data files from HF
for f in game.jsonl navworld.jsonl liveweb.jsonl swe_infinite.jsonl memorygym.jsonl; do
    if [ -f "/root/data/$f" ]; then
        echo "  $f already exists"
    else
        /root/venv/bin/huggingface-cli download monokoco/affine-sft-data "$f" --local-dir /root/data --repo-type dataset 2>&1 | tail -1
        echo "  $f: $(wc -l < /root/data/$f) lines"
    fi
done

# Build combined.jsonl
echo "  Building combined.jsonl..."
cat /root/data/game.jsonl /root/data/navworld.jsonl /root/data/liveweb.jsonl /root/data/swe_infinite.jsonl /root/data/memorygym.jsonl > /root/data/combined.jsonl
echo "  combined.jsonl: $(wc -l < /root/data/combined.jsonl) lines"

# ---- 7. Write .env ----
echo "[7/7] Writing .env..."
cat > /root/.env << 'ENVEOF'
export HF_TOKEN="${HF_TOKEN}"
export AMAP_API_KEY="${AMAP_API_KEY}"
export AMAP_MAPS_API_KEY="${AMAP_MAPS_API_KEY}"
ENVEOF
# Substitute actual values
if [ -n "${HF_TOKEN:-}" ]; then
    sed -i "s|\${HF_TOKEN}|${HF_TOKEN}|g" /root/.env
fi
if [ -n "${AMAP_API_KEY:-}" ]; then
    sed -i "s|\${AMAP_API_KEY}|${AMAP_API_KEY}|g" /root/.env
    sed -i "s|\${AMAP_MAPS_API_KEY}|${AMAP_MAPS_API_KEY}|g" /root/.env
fi
echo "  .env written"

# ---- Verify ----
echo ""
echo "=== Setup Complete ==="
echo "Python: $(python3 --version)"
echo "Torch:  $(python3 -c 'import torch; print(torch.__version__, "CUDA:", torch.cuda.is_available())')"
echo "GPUs:   $(nvidia-smi -L | wc -l)"
echo "Model:  /root/models/Qwen3-32B ($(ls /root/models/Qwen3-32B/*.safetensors 2>/dev/null | wc -l) shards)"
echo "Data:   /root/data/combined.jsonl ($(wc -l < /root/data/combined.jsonl) lines)"
echo ""
echo "Ready to train! Use:"
echo "  forge train launch -m <machine>"
echo "  forge train monitor -m <machine>"
