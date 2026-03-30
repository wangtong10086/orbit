# Infrastructure Knowledge

## Machines
- **m1, m2**: 4xH200 (576GB VRAM) — Targon rentals
- **m3**: 8xH200 (1152GB VRAM) — Targon rental
- **c1, w1, w2**: CPU workers (AWS)
- All machines in `machines.json`, managed via `forge remote -m <name>`

## CLI Architecture

### `forge remote -m <machine>` — Remote operations (any SSH machine)
```bash
forge remote -m m1 status                    # GPU/disk/screens
forge remote -m m1 exec "<command>"          # Remote command
forge remote -m m1 kill sglang|eval|training|all
forge remote -m m1 upload <local> <remote>   # File upload (rsync/scp)
forge remote -m m1 download <remote> <local> # File download
forge remote -m m1 transfer m2 /root/model   # Machine-to-machine
forge remote -m m1 sync                      # Sync project files
forge remote -m m1 run "<cmd>"               # Sync + execute
forge remote -m m1 setup                     # Full machine setup
forge remote -m m1 clone-eval m2             # Copy eval infra
forge remote -m m1 monitor                   # Training progress
forge remote -m m1 game test --all           # Game bot testing
```

### `forge rental` — Targon machine lifecycle
```bash
forge rental provision --gpu H200 --name worker  # Rent new machine
forge rental terminate <id>                      # End rental
forge rental list                                # List active rentals
forge rental capacity                            # Available GPUs
forge rental logs <id>                           # Container logs
forge rental register --name m4 --host ...       # Add to machines.json
forge rental unregister m4                       # Remove from machines.json
```

## sglang Setup
- Install in venv: `pip install sglang[all]`
- Training inference: `--tp 4` (all GPUs, one model instance)
- Eval inference: `--dp 4 --tp 1` (4 instances, 4x throughput)
- **Critical**: `--tool-call-parser qwen25` for NAVWORLD/LIVEWEB tool calling
- Without tool-call-parser, `<tool_call>` text is not parsed into OpenAI format

## Eval Setup
- `scripts/eval_envs.py` — runs affinetes SDK evaluations
- Requires Docker with host_network=True
- Concurrency 4, timeout 7200s (long games need time)
- AMAP_MAPS_API_KEY needed for NAVWORLD
- SWE-Infinite: needs Docker images from DockerHub (affinefoundation/swe_infinite_images)

## Pre-Quantized Model
- `unsloth/Qwen3-32B-bnb-4bit`: 4 safetensors, ~18GB, ~90s download
- vs `Qwen/Qwen3-32B`: 16 safetensors, ~65GB, 10-30 min
- Always use pre-quantized

## Cost Reference
- Training run (4xH200, ~3h): ~$9
- Eval run (3 envs, 100 samples each): ~$5-7
