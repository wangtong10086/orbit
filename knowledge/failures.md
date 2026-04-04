# Failure Museum

> Status: Reference note
> Authority: Non-normative
> Last reviewed: 2026-04-04
> Use this file for background and deep analysis, not as the primary source of truth.


## Key Facts
- Total estimated cost of failures: ~$80-100+
- Most expensive category: Targon network issues (~$50)
- Most impactful fix: apply_chat_template + sglang tool-call-parser (NAVWORLD 0→8.7%)
- Lesson: always validate data format against eval source code before training

## Expensive Failures

### 1. HF Upload Callback Corruption — ~$60
**Versions affected**: v1B, v2, v3 (3 training runs)
**Symptom**: HF uploads silently fail after step 200-300, training continues but results unrecoverable
**Root cause**: HfApi instance connection pool/auth state corrupts during long-running training
**Attempted fixes that failed**: reduce frequency, new HfApi instance, 3 retries + backoff
**Working fix**: Fork independent Python subprocess per upload, JSON task file, 300s timeout
**Cost**: GAME ~$24 + Mixed v1 ~$16 + Mixed v2 ~$20 = ~$60

### 2. Targon Network Outage — ~$25-30
**Date**: 2026-03-12, ~8 hours
**Symptom**: All outbound network (HTTP/HTTPS) Connection refused or Network unreachable
**Impact**: ~15 container attempts, all failed to install dependencies
**Key finding**: Network was intermittent (~30-60s window after startup)
**Resolution**: Offline wheel bundle approach (202MB tar.gz on HF, urllib download)
**Cost**: ~$25-30 in wasted container time

### 3. LIVEWEB Training Noise — ~$8 (v3 training budget wasted)
**Version**: v3
**Symptom**: 2532 LIVEWEB entries (20.4% of mix) were pure noise
**Root cause**: All 844 entries median 145K chars, 0 usable at max_seq_len=8192
**Impact**: 20.4% of training compute wasted on truncated garbage data
**Fix**: Removed LIVEWEB from v4, re-added in v7 with strict length filtering

### 4. NAVWORLD Text Format — ~$15 (v3-v6 training wasted for NAVWORLD)
**Versions affected**: v3-v6
**Symptom**: NAVWORLD score always 0.000 across all evaluations
**Root cause chain**:
1. Synthetic data used text format ("Call tool: xxx") instead of standard tool_calls
2. Even after format fix, custom `<tool_calls>` serialization didn't match Qwen3 native format
3. Even with correct training, sglang didn't parse tool calls without `--tool-call-parser qwen25`
**Fix**: Three-part fix over v4-v8 (delete text data → apply_chat_template → tool-call-parser)
**Lesson**: Read eval source code FIRST, validate format end-to-end before any training

### 5. Training from Top Model — ~$3
**Version**: Quick Experiment #1
**Symptom**: Loss oscillated wildly (0.64→0.92) without convergence
**Root cause**: Top model already deeply fine-tuned, QLoRA cannot stably learn on top
**Fix**: Always train from base Qwen3-32B
**Lesson**: QLoRA on top of existing fine-tunes is unstable

### 6. LR Too Low (1e-5) — ~$40 (v1-v3 suboptimal)
**Versions affected**: v1-v3
**Symptom**: Loss plateaued at ~0.45, never reached <0.2
**Root cause**: 1e-5 is 10x too low for QLoRA standard range
**Fix**: Increased to 1e-4 in v4+ (loss dropped to ~0.11-0.18)
**Cost**: 3 training runs at suboptimal LR, partial waste

### 7. Eval Timeout Too Short — Misdiagnosed model quality
**Versions affected**: v5-v8 evaluations
**Symptom**: GAME scores appeared low (~0.10)
**Root cause**: 600s timeout killed long-running games that would have scored
**Fix**: Increased to 7200s timeout, added concurrency 4
**Impact**: v9 GAME jumped from 0.10 to 0.19 just from config change

### 8. SWE-SYNTH Trailing User Message — Unknown cost
**Versions affected**: v1-v3
**Symptom**: Model learns to predict user diff output instead of generating fixes
**Root cause**: 444 entries had last message as user role
**Fix**: Removed trailing user messages in v4

### 9. v4 Targon apt-get Complete Failure — ~$5
**Symptom**: Container network completely down, cannot install python3-pip
**Root cause**: Targon outbound network temporarily blocked
**Fix**: Added apt-get retry (3 times) + pip bootstrap fallback to runner.py

### 10. GAME CoT Conflict (29% Parse Error) — ~$10
**Versions affected**: v5-v6
**Symptom**: 29% of GAME outputs unparseable by eval
**Root cause**: Mixed system prompts (54.4% CoT, 45.6% non-CoT), 13.9% directly contradictory
**Fix**: Unified all system prompts to CoT version in v7 (eval auto-strips think tags)

## Meta-Lessons
1. **Read eval source code before training** — format mismatches are the #1 failure mode
2. **Validate end-to-end** — data format + training + inference + eval parsing, all must align
3. **Small sample eval first** — 20 samples catch most issues before burning $10+
4. **Don't retry blindly** — if 3 attempts fail the same way, switch approach
5. **Infrastructure costs add up fast** — $2.40/hr means $5 per 2-hour debug session
