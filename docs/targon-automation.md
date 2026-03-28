# Targon Training Automation

Automated environment setup for Targon SSH deployments. Two methods:

## Method 1: Bootstrap Script (Recommended)

Idempotent script that installs the full training stack on any Targon SSH deployment,
caching persistent data on the `/data` volume.

### Quick Start

```bash
# Full setup (training stack + dev tools)
forge rental bootstrap

# Training stack only (skip neovim, zsh, node)
forge rental bootstrap --training-only

# Verify installation
forge rental bootstrap --check
```

### What Gets Installed

| Component | Location | Persistent? |
|-----------|----------|-------------|
| uv (Python package manager) | `/data/.affine/tools/bin/uv` | Yes (volume) |
| Python 3.11 venv | `/data/.affine/venv/` | Yes (volume) |
| PyTorch + CUDA 12.4 | venv | Yes (volume) |
| ms-swift, DeepSpeed, flash-attn | venv | Yes (volume) |
| sglang | venv | Yes (volume) |
| wandb | venv | Yes (volume) |
| Node.js 20 LTS | `/data/.affine/tools/` | Yes (volume) |
| Neovim + LazyVim | `/data/.affine/tools/` | Yes (volume) |
| Zsh + Oh My Zsh | `/data/.affine/ohmyzsh/` | Yes (volume) |
| System packages (git, tmux, etc.) | apt | No (container) |

### Volume Layout

```
/data/
├── .affine/              # Bootstrap installs (persistent)
│   ├── activate.sh       # Source this to activate environment
│   ├── tools/bin/        # uv, nvim, node
│   ├── venv/             # Python virtual environment
│   ├── config/nvim/      # LazyVim config
│   └── ohmyzsh/          # Oh My Zsh
├── .cache/huggingface/   # HF model cache
├── checkpoints/          # Training checkpoints
├── datasets/             # Training datasets
├── logs/                 # Training logs
└── models/               # Saved models
```

### How It Works

1. **System packages** (Phase 0): Checks if core tools are present, installs via apt if needed
2. **uv** (Phase 1): Fast Python package manager, cached on volume
3. **Python venv + ML stack** (Phase 2): Creates venv, installs PyTorch (CUDA 12.4), ms-swift, DeepSpeed, flash-attn
4. **Node.js** (Phase 3): LTS version for tooling
5. **Neovim + LazyVim** (Phase 4): Editor with full IDE features
6. **Zsh + Oh My Zsh** (Phase 5): Shell with plugins
7. **Docker** (Phase 6): Best-effort (may fail in unprivileged containers)
8. **Environment config** (Phase 7): Creates `activate.sh`, configures shell RC files

The script is **idempotent** — safe to run multiple times. Each phase checks if its
work is already done before proceeding.

### After Bootstrap

```bash
# SSH into the machine
forge rental exec "zsh"

# Or run training directly
forge rental start-training --model Qwen/Qwen3-32B --dataset your_dataset
```

## Method 2: Pre-built Docker Image

For deployments that support custom images. Build once, deploy instantly.

### Build

```bash
# Build locally
forge rental docker-build

# Build and push to registry
forge rental docker-build myuser/affine-forge:v1 --push
```

### Dockerfile Contents

- Base: `nvidia/cuda:12.4.1-devel-ubuntu22.04`
- Pre-installed: everything from Method 1
- Volume: `/data` for models, datasets, checkpoints
- Entrypoint: auto-creates data dirs, activates venv, GPU check

### Usage

When creating a Targon deployment, specify the custom image. The `/data` volume
will be mounted automatically.

## Known Issues

### CUDA Error 802 (System Not Ready)

Some Targon deployments may show `cuInit` returning error 802 while `nvidia-smi`
works fine. This is a **platform-level issue** (missing `/dev/nvidia-caps/` device
nodes or Fabric Manager state) — not caused by the bootstrap.

Workaround: Contact Targon support to verify GPU initialization on the host.

### SCP/rsync Protocol Errors

Targon SSH proxy outputs a banner message on connection, breaking SCP/rsync protocols.
The upload system automatically falls back to SSH pipe transfer (`cat | ssh cat >`).

## Architecture

```
forge/setup/           # Setup module (independent of compute/training layers)
├── __init__.py
├── bootstrap.sh       # Method 1: idempotent bootstrap script
├── requirements.txt   # Python dependencies (shared by both methods)
├── Dockerfile         # Method 2: pre-built image definition
└── entrypoint.sh      # Docker entrypoint for Method 2
```

The setup module integrates with the CLI via:
- `forge rental bootstrap` — uploads and runs bootstrap.sh
- `forge rental bootstrap --check` — verifies installation
- `forge rental docker-build` — builds Docker image

