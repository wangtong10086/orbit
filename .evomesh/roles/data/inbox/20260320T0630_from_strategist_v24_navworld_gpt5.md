---
from: strategist
to: data
priority: P1
type: directive
date: 2026-03-20T06:30
---

# v2.4 NAVWORLD GPT-5.4 distillation — replace ALL qwen-max data

## Context
v2.2 NAVWORLD regressed (8.47→6.10). User approved strategy: replace ALL qwen-max distillation data with GPT-5.4. Same-family distillation (Qwen3-max→Qwen3-32B) is limiting generalization.

## Directive

### Phase 1: Build GPT-5.4 NAVWORLD pipeline
- Adapt `forge data navworld-gen` to support `--model gpt-5.4` (currently only Claude Sonnet)
- Use existing navworld-gen architecture: programmatic problem gen → tool calls → GPT-5.4 plan gen → QQR filter
- Quality gate: QQR code score ≥25, no fabrication

### Phase 2: Generate ~1200 GPT-5.4 entries across all 7 types
Target distribution:
- intercity: 200, multiday: 200, hybrid: 200, business: 200
- food_tour: 150, family_study: 150, single_poi: 100

### Phase 3: Rebuild canonical
- Remove ALL 2205 qwen-max entries from canonical
- Keep 419 Claude Sonnet entries
- Add ~1200 GPT-5.4 entries
- New canonical: ~1600 entries (GPT-5.4 + Claude Sonnet only)
- Upload to HF immediately

### Timeline
Start pipeline work NOW during v2.3 training. Data must be ready before v2.3 eval completes.

### Experiment ref: experiments/v2.4-navworld-gpt5.yaml (status: drafting)
