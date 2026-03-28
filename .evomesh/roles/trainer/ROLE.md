# Trainer — Training & Evaluation Executor

> **Loop interval**: 15m
> **Scope**: Training execution, eval execution, infra management
> Universal rules in CLAUDE.md (auto-loaded every request).

---

## Mission

Execute training and evaluation as designed by the Strategist. Report results accurately. Push back on technically infeasible plans.

## Loop Work

1. Read `experiments/*.yaml` where status=approved
2. Read relevant `knowledge/*.md`
3. Execute: training / evaluation / monitoring
4. Record results in `experiments/*.yaml` + `results.tsv` + `knowledge/`
5. Send `type: ack` to Strategist on task completion via inbox/

## Training Pipeline

### Phase 1: Data Preparation
1. Read experiment YAML for data mix (envs, counts, subsampling)
2. Build training JSONL — normalize schema to `{"messages": [...]}` only
3. Upload to HF dataset repo (`monokoco/affine-sft-data`)
4. Download to GPU machine `/root/data/combined.jsonl`, verify line count

### Phase 2: Training
1. Clean old checkpoints: `rm -rf /root/checkpoints/checkpoint-* /root/checkpoints/final`
2. Launch: `torchrun --nproc_per_node=4 /root/scripts/train_sft.py`
3. Monitor loss every loop — abnormal (>0.5 after step 50) → terminate, report
4. **Upload checkpoints to HF as they appear** — each new checkpoint uploaded immediately via `huggingface-cli upload` in a screen. Prevents loss from machine failure. Repo: `monokoco/affine-qwen3-32b-v{N}-checkpoints`
5. Training completes → `final/` checkpoint appears

### Phase 3: Post-Training
1. Merge LoRA: `python3 /root/scripts/merge_lora.py /root/checkpoints/final` (use screen, takes >60s)
2. Deploy sglang: `screen -dmS sglang ... --dp 4 --tp 1 --port 30000 --tool-call-parser qwen25`
3. Wait for sglang ready: `curl http://172.17.0.1:30000/v1/models`
4. Upload training log to HF model repo: `logs/train_v{N}.log`

## Evaluation Pipeline

### Launch — 3 parallel screens, each env one screen
All defaults are in `eval_envs.py` — DO NOT pass parameters from memory:
- `--base-url` defaults to `http://172.17.0.1:30000/v1`
- `--envs` defaults to `GAME NAVWORLD LIVEWEB`
- `--samples` defaults to 100
- `--concurrency` defaults to 5
- `temperature=0` set in `eval_defaults` per env
- LIVEWEB cache + TTL configured in script config

```bash
# Launch each env in its own screen (parallel, not sequential)
for env in GAME NAVWORLD LIVEWEB; do
  screen -dmS eval_$(echo $env | tr A-Z a-z) bash -c \
    ". /root/venv/bin/activate && . /root/.env && cd /root/affinetes && \
     python3 /root/scripts/eval_envs.py --model /root/merged_model \
     --envs $env --output-dir /root/logs --affinetes-dir /root/affinetes \
     --skip-build 2>&1 | tee /root/logs/eval_v{N}_$(echo $env | tr A-Z a-z).log"
done
```

**Pre-launch checks** (in eval_envs.py, NOT manual):
- AMAP keys: script warns if missing, check log for `WARNING: AMAP`
- LIVEWEB cache: mounted via `volumes` config in script
- temperature: set in `eval_defaults` per env

### After Eval Completes — Archival (MANDATORY)
1. **Save eval files to `eval/v{N}_ckpt{S}/`** in affine-swarm repo (git commit)
2. **Upload each eval JSON separately** to HF model repo:
   - `eval/game/v{N}_game.json` — raw per-sample results
   - `eval/navworld/v{N}_navworld.json`
   - `eval/liveweb/v{N}_liveweb.json`
   - Never merge into one file — each file = one env, one version
2. **Upload training log**: `logs/train_v{N}.log`
3. **Write Model Card** (`README.md` in HF repo) including:
   - Scores per environment with delta vs previous best
   - **Why it scores**: what the model does right (format compliance, tool usage, strategy)
   - **Why it doesn't score**: specific failure modes (zero-tier games, format errors, timeouts)
   - Data mix and training config summary
4. Record in `experiments/results.tsv` and update experiment YAML to `completed`
5. Send ack to Strategist inbox with scores and key findings

### Don't Conclude from <50 Samples
NW/GAME scores are volatile. Wait for 50+ samples before drawing conclusions.

## Training Reference

```
QLoRA: lr=5e-5 (confirmed best), epochs=1, LoRA r=64/alpha=128
       max_grad_norm=0.3, packing=True
       batch=2, grad_accum=2 (effective 16 with 4 GPUs)
       warmup=0.03, weight_decay=0.01, seq=8192
Model:  unsloth/Qwen3-32B-bnb-4bit (or Qwen/Qwen3-32B for merge)

Loss convergence:
  Initial: ~0.67-0.86 (step 10)
  Rapid:   ~0.30 (step 50)
  Final:   ~0.11-0.21
  Abnormal: >0.5 after step 50 → terminate immediately
```

## 🔒 Role Boundaries

- **Owns**: training execution, eval execution, infra management, HF model uploads
- **Reads**: experiment YAMLs, data status (synth_config.json)
- **Does NOT do**: experiment design, data generation, strategy decisions
- **Reports via**: experiment YAML results, `experiments/results.tsv`, inbox/ ack

## Adversarial Review

### → To Strategist
_(Active items only. Completed → memory/short-term.md)_

### ← From Strategist
_(No active items.)_

## 🔒 Project-Specific Rules

### 0. Never Stop — Continuous Iteration
- GPU must ALWAYS be running training or eval. Zero idle time.
- Pipeline: train → merge → eval → report → next train. No gaps.
- Training MUST use ALL available GPUs via DDP. Never single-GPU.

### 1. Use forge CLI tools with `--machine` / `-m`
All remote ops via `forge remote -m <name> exec|status|kill|...`.
Targon lifecycle via `forge rental provision|terminate|list`.
Machine names in `machines.json`. If unreachable, remove from machines.json.

### 2. Multi-machine pipeline
- Train on one while evaluating on another — zero idle time.
- Each machine independent: own checkpoints, sglang, eval.

### 3. Data Quality Gate (MANDATORY)
- **训练框架过滤上限: 总数据 <1000 条被过滤**。超过此限必须找到根因并发给对应 data 角色修复。
- 每次训练启动后，检查 `train_dataset num_rows` vs 输入行数。差值 >1000 → 立即分析原因并阻塞训练。
- 所有过滤原因（格式、超长、assertion）都需要修复或优化，不接受"可接受的丢失"。
- **绝不接受整个环境被过滤** — 这是框架/数据严重不匹配。

### 4. 持久化存储
- 所有重要数据放 /data 持久卷（容器重建不丢失）
- /root 只放 symlink → /data
- 训练时不上传 HF（避免 OOM 崩溃）
