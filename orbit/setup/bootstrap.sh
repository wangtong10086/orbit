#!/bin/bash
# ORBIT — Targon Bootstrap Script (Method 1)
#
# Idempotent environment setup for Targon SSH deployments.
# Installs training stack + dev tools, caching to /data/.affine/ for
# persistence across container restarts.
#
# Usage:
#   bash bootstrap.sh              # Full setup
#   bash bootstrap.sh --training   # Training stack only (skip dev tools)
#   bash bootstrap.sh --check      # Verify installation
#   bash bootstrap.sh --flash-attn # Optional flash-attn install for special recipes
#
set -euo pipefail

VOLUME="/data"
AFFINE_DIR="$VOLUME/.affine"
VENV_DIR="$AFFINE_DIR/venv"
TOOLS_DIR="$AFFINE_DIR/tools"
CONFIG_DIR="$AFFINE_DIR/config"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${GREEN}[AFFINE]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
info() { echo -e "${BLUE}[INFO]${NC} $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

TRAINING_ONLY=false
CHECK_ONLY=false
INSTALL_FLASH_ATTN=false
ORBIT_TORCH_VERSION="${ORBIT_TORCH_VERSION:-2.10.0}"
ORBIT_TRANSFORMERS_VERSION="${ORBIT_TRANSFORMERS_VERSION:-4.57.6}"
ORBIT_SWIFT_VERSION="${ORBIT_SWIFT_VERSION:-4.0.4}"
ORBIT_VLLM_VERSION="${ORBIT_VLLM_VERSION:-0.19.0}"
for arg in "$@"; do
    case "$arg" in
        --training) TRAINING_ONLY=true ;;
        --check)    CHECK_ONLY=true ;;
        --flash-attn) INSTALL_FLASH_ATTN=true ;;
    esac
done

mkdir -p "$AFFINE_DIR" "$TOOLS_DIR/bin" "$CONFIG_DIR"

# ─── Check mode ────────────────────────────────────────────────────
if $CHECK_ONLY; then
    # Source activate.sh first for correct PATH
    [ -f "$AFFINE_DIR/activate.sh" ] && source "$AFFINE_DIR/activate.sh" 2>/dev/null
    export PATH="$TOOLS_DIR/bin:$TOOLS_DIR/lib:$PATH"
    log "Checking installation..."
    FAIL=0
    require() { command -v "$1" &>/dev/null && info "$1: $(command -v $1)" || { warn "$1: NOT FOUND (required)"; FAIL=1; }; }
    optional() { command -v "$1" &>/dev/null && info "$1: $(command -v $1)" || info "$1: not installed (optional)"; }
    require python3; require uv; optional nvim; optional node; optional zsh
    if [ -f "$VENV_DIR/bin/activate" ]; then
        source "$VENV_DIR/bin/activate"
        GPU_COUNT=$(nvidia-smi -L 2>/dev/null | wc -l)
        python3 -c "
import importlib.metadata as im
import torch; print(f'  torch={torch.__version__}, CUDA_built={torch.version.cuda}')
import transformers; print(f'  transformers={transformers.__version__}')
import swift; print(f'  ms-swift={swift.__version__}')
print(f'  affine-ms-swift-fork={im.version(\"affine-ms-swift-fork\")}')
import pynvml; print(f'  pynvml={getattr(pynvml, \"__version__\", \"unknown\")}')
import vllm; print(f'  vllm={vllm.__version__}')
import deepspeed; print(f'  deepspeed={deepspeed.__version__}')
from transformers.image_utils import VideoInput; print('  transformers.video_input=OK')
from transformers.models.mllama.image_processing_mllama import is_valid_list_of_images; print('  transformers.mllama_images=OK')
try:
    import flash_attn
    print(f'  flash_attn={getattr(flash_attn, "__version__", "unknown")} (optional)')
except ImportError:
    print('  flash_attn=not installed (optional)')
" 2>/dev/null || { warn "Python packages check failed"; FAIL=1; }
        info "GPUs detected by nvidia-smi: $GPU_COUNT"
    else
        warn "Python venv not found at $VENV_DIR"; FAIL=1
    fi
    [ $FAIL -eq 0 ] && log "All checks passed" || warn "Some checks failed"
    exit $FAIL
fi

START_TIME=$(date +%s)

# ─── Phase 0: System packages ──────────────────────────────────────
# These live in the container filesystem (lost on recreate), so always check.
phase0_system() {
    local NEED_INSTALL=false
    for cmd in git curl wget zsh tmux screen jq rsync; do
        command -v "$cmd" &>/dev/null || { NEED_INSTALL=true; break; }
    done

    if $NEED_INSTALL; then
        log "Phase 0: Installing system packages..."
        apt-get update -qq 2>/dev/null
        DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
            build-essential git curl wget unzip \
            zsh tmux screen htop jq \
            openssh-client rsync \
            libnuma1 libnuma-dev \
            2>&1 | tail -3
        log "Phase 0: Done"
    else
        info "Phase 0: System packages (present)"
    fi
}

# ─── Phase 1: uv ───────────────────────────────────────────────────
phase1_uv() {
    if [ -f "$TOOLS_DIR/bin/uv" ] && "$TOOLS_DIR/bin/uv" --version &>/dev/null; then
        info "Phase 1: uv (cached at $TOOLS_DIR/bin/uv)"
    else
        rm -f "$TOOLS_DIR/bin/uv" "$TOOLS_DIR/bin/uvx" 2>/dev/null
        log "Phase 1: Installing uv..."
        curl -LsSf "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-unknown-linux-gnu.tar.gz" \
            | tar xzf - --strip-components=1 -C "$TOOLS_DIR/bin"
        log "Phase 1: uv installed ($($TOOLS_DIR/bin/uv --version))"
    fi
    export PATH="$TOOLS_DIR/bin:$PATH"
}

# ─── Phase 2: Python venv + ML stack ───────────────────────────────
phase2_venv() {
    if [ -f "$VENV_DIR/bin/activate" ]; then
        source "$VENV_DIR/bin/activate"
        # Quick smoke test — if torch imports, env is good
        if python3 -c "import torch, swift, vllm, deepspeed; from transformers.image_utils import VideoInput; from transformers.models.mllama.image_processing_mllama import is_valid_list_of_images" 2>/dev/null; then
            info "Phase 2: Python venv + ML stack (cached)"
            return
        else
            warn "Phase 2: Venv exists but packages incomplete, reinstalling..."
            rm -rf "$VENV_DIR"
        fi
    fi

    log "Phase 2: Creating Python venv + ML stack..."
    uv venv "$VENV_DIR" --python 3.11 2>/dev/null || uv venv "$VENV_DIR" 2>/dev/null
    source "$VENV_DIR/bin/activate"

    # Locate the project root (pyproject.toml)
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

    # Step 1: Install the native GKD runtime stack first so the default
    # execution environment matches the image and no remote hotfix is needed.
    if [ -f "$PROJECT_ROOT/pyproject.toml" ]; then
        log "  Installing local affine RL stack from repository..."
        "$PROJECT_ROOT/orbit/setup/install_local_rl_stack.sh" "$PROJECT_ROOT" 2>&1 | tail -20
    else
        err "  pyproject.toml not found at $PROJECT_ROOT; local fork install requires the repository checkout"
    fi

    # Step 2: flash-attn is optional for recipes that explicitly need it.
    if $INSTALL_FLASH_ATTN; then
        log "  Installing flash-attn (optional path)..."
        "$PROJECT_ROOT/orbit/setup/install_flash_attn.sh" 2>&1 | tail -10
    else
        info "  Skipping flash-attn (optional; default GKD path uses sdpa + packing:false)"
    fi

    # Step 3: Remove torchao if installed (not needed for the validated GKD stack)
    pip uninstall torchao -y 2>/dev/null || true

    log "Phase 2: Done"
}

# ─── Phase 3: Node.js ──────────────────────────────────────────────
phase3_nodejs() {
    if [ -f "$TOOLS_DIR/bin/node" ]; then
        info "Phase 3: Node.js (cached)"
        return
    fi

    log "Phase 3: Installing Node.js..."
    local NODE_VER="v20.18.1"
    curl -fsSL "https://nodejs.org/dist/${NODE_VER}/node-${NODE_VER}-linux-x64.tar.xz" \
        | tar xJf - --strip-components=1 -C "$TOOLS_DIR"
    log "Phase 3: Node.js installed ($($TOOLS_DIR/bin/node --version))"
}

# ─── Phase 4: Neovim + LazyVim ─────────────────────────────────────
phase4_neovim() {
    if [ -f "$TOOLS_DIR/bin/nvim" ]; then
        info "Phase 4: Neovim + LazyVim (cached)"
        return
    fi

    log "Phase 4: Installing Neovim + LazyVim..."
    curl -fsSL "https://github.com/neovim/neovim/releases/latest/download/nvim-linux-x86_64.tar.gz" \
        | tar xzf - --strip-components=1 -C "$TOOLS_DIR"

    # LazyVim starter config
    if [ ! -d "$CONFIG_DIR/nvim" ]; then
        git clone --depth 1 https://github.com/LazyVim/starter "$CONFIG_DIR/nvim" 2>/dev/null
        rm -rf "$CONFIG_DIR/nvim/.git"
    fi
    log "Phase 4: Done"
}

# ─── Phase 5: Zsh + Oh My Zsh ──────────────────────────────────────
phase5_zsh() {
    if [ -d "$AFFINE_DIR/ohmyzsh" ]; then
        info "Phase 5: Oh My Zsh (cached)"
    else
        log "Phase 5: Installing Oh My Zsh..."
        export RUNZSH=no CHSH=no KEEP_ZSHRC=yes ZSH="$AFFINE_DIR/ohmyzsh"
        sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended 2>/dev/null || true
        log "Phase 5: Done"
    fi
}

# ─── Phase 6: Docker (best effort) ─────────────────────────────────
phase6_docker() {
    if command -v docker &>/dev/null; then
        info "Phase 6: Docker (present)"
        return
    fi

    log "Phase 6: Installing Docker (best effort)..."
    if apt-get install -y -qq docker.io 2>/dev/null; then
        # Try to start daemon (may fail in unprivileged containers)
        dockerd &>/dev/null &
        sleep 2
        if docker info &>/dev/null; then
            log "Phase 6: Docker daemon running"
        else
            kill %1 2>/dev/null || true
            warn "Phase 6: Docker installed but daemon cannot start (container security limits)"
            info "  Docker client available — can connect to remote daemons"
        fi
    else
        warn "Phase 6: Docker not installable — skipping"
    fi
}

# ─── Phase 7: Environment config ───────────────────────────────────
phase7_config() {
    log "Configuring environment..."

    # Create activation script
    cat > "$AFFINE_DIR/activate.sh" << 'ACTIVATE_EOF'
#!/bin/bash
# Affine training environment activation script.
# Source this: source /data/.affine/activate.sh
export AFFINE_DIR="/data/.affine"
export AFFINE_PROJECT_ROOT="__AFFINE_PROJECT_ROOT__"
export PATH="$AFFINE_DIR/tools/bin:$AFFINE_DIR/tools/lib:$PATH"
export XDG_CONFIG_HOME="$AFFINE_DIR/config"
export XDG_DATA_HOME="$AFFINE_DIR/data"
export ZSH="$AFFINE_DIR/ohmyzsh"

# Python venv
if [ -f "$AFFINE_DIR/venv/bin/activate" ]; then
    source "$AFFINE_DIR/venv/bin/activate"
fi

# CUDA
export PATH="/usr/local/cuda/bin:$PATH"
export LD_LIBRARY_PATH="/usr/local/cuda/lib64:${LD_LIBRARY_PATH:-}"

# HuggingFace cache on volume
export HF_HOME="/data/.cache/huggingface"
export TRANSFORMERS_CACHE="/data/.cache/huggingface/hub"
export AFFINE_MS_SWIFT_FORK_ROOT="$AFFINE_PROJECT_ROOT/packages/affine_ms_swift/vendor/ms_swift_fork"
export AFFINE_MEMORYGYM_ROOT="$AFFINE_PROJECT_ROOT/repos/MemoryGym"
mkdir -p "$HF_HOME"

# HuggingFace token (set during bootstrap or manually)
if [ -f "/data/.cache/huggingface/token" ]; then
    export HF_TOKEN=$(cat /data/.cache/huggingface/token)
fi

# Training dirs
mkdir -p /data/checkpoints /data/datasets /data/logs

echo "Affine env active | Python: $(python3 --version 2>&1) | GPUs: $(nvidia-smi -L 2>/dev/null | wc -l || echo '?')"
ACTIVATE_EOF
    sed -i "s|__AFFINE_PROJECT_ROOT__|$PROJECT_ROOT|g" "$AFFINE_DIR/activate.sh"
    chmod +x "$AFFINE_DIR/activate.sh"

    # Inject into shell RC files
    for rc in /root/.bashrc /root/.zshrc; do
        [ -f "$rc" ] || touch "$rc"
        if ! grep -q "affine/activate" "$rc" 2>/dev/null; then
            echo '[ -f /data/.affine/activate.sh ] && source /data/.affine/activate.sh' >> "$rc"
        fi
    done

    # Configure zsh as default if available
    if command -v zsh &>/dev/null && [ -d "$AFFINE_DIR/ohmyzsh" ]; then
        # Set default shell for new SSH sessions
        [ -f /root/.zshrc ] || touch /root/.zshrc
        if ! grep -q 'ZSH_THEME' /root/.zshrc 2>/dev/null; then
            cat > /root/.zshrc << 'ZSHRC_EOF'
export ZSH="/data/.affine/ohmyzsh"
ZSH_THEME="robbyrussell"
plugins=(git docker python)
source $ZSH/oh-my-zsh.sh
[ -f /data/.affine/activate.sh ] && source /data/.affine/activate.sh
ZSHRC_EOF
        fi
    fi

    info "Environment configured. Activate: source /data/.affine/activate.sh"
}

# ─── Phase 8: Data directory structure ──────────────────────────────
phase8_dirs() {
    mkdir -p /data/{checkpoints,datasets,logs,models,.cache/huggingface}
    info "Data directories ready: /data/{checkpoints,datasets,logs,models}"
}

# ─── Run all phases ────────────────────────────────────────────────
log "ORBIT Bootstrap — starting"

phase0_system
phase1_uv
phase2_venv

if ! $TRAINING_ONLY; then
    phase3_nodejs
    phase4_neovim
    phase5_zsh
    phase6_docker
fi

phase7_config
phase8_dirs

ELAPSED=$(( $(date +%s) - START_TIME ))
log "Bootstrap complete in ${ELAPSED}s"

# Final verification
source "$AFFINE_DIR/activate.sh"
python3 -c "
import torch
import importlib.metadata as im
cuda_ok = torch.cuda.is_available()
gpus = torch.cuda.device_count()
print(f'  torch={torch.__version__}, CUDA={cuda_ok}, GPUs={gpus}')
if not cuda_ok:
    print('  [WARN] CUDA not available — may be a platform/driver issue (error 802)')
    print('         nvidia-smi may work while CUDA compute does not')
    print('         This is NOT caused by the bootstrap — contact platform support')
import transformers; print(f'  transformers={transformers.__version__}')
import swift; print(f'  ms-swift={swift.__version__}')
print(f'  affine-ms-swift-fork={im.version(\"affine-ms-swift-fork\")}')
import vllm; print(f'  vllm={vllm.__version__}')
import deepspeed; print(f'  deepspeed: OK')
from transformers.image_utils import VideoInput; print('  transformers.video_input=OK')
from transformers.models.mllama.image_processing_mllama import is_valid_list_of_images; print('  transformers.mllama_images=OK')
print('  native GKD runtime: OK')
" 2>/dev/null || warn "Some verification checks failed"

log "Ready! Run: source /data/.affine/activate.sh"
