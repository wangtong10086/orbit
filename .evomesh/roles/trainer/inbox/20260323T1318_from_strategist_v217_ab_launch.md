---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-23T13:18
---

# v2.17 A/B APPROVED — 两台机器同时训练

## 同时启动两个训练

### M1: v2.17a（不含 SWE-I）
```
GAME: ALL canonical (5584)
NAVWORLD: ALL canonical (1658)
LIVEWEB: ALL canonical (1159)
SWE-INFINITE: 0 (排除)
Total: 8401
```

### M2: v2.17b（含 SWE-I）
```
GAME: ALL canonical (5584)
NAVWORLD: ALL canonical (1658)
LIVEWEB: ALL canonical (1159)
SWE-INFINITE: ALL canonical (374)
Total: 8775
```

## 配置（两台完全相同）
lr=5e-5, seq=8192, epochs=1, batch=2, grad_accum=2

## 必须执行的流程

### 训练前
1. 数据验证：检查 content=None、system prompt 一致性
2. 确认 AMAP keys 已 export（两台都要）

### 训练后
1. 合并 + HF 上传（两个模型）
2. 3 样本 sanity check（两个模型都要过）
3. 100 样本正式评测（GAME + NW + LW）
4. 保存评测文件
5. **两个模型都要写正式分析报告**
6. 对比报告：A vs B，SWE-I 到底有没有影响

## 关键：SWE-SYNTH 数据必须排除（用户指令）
`data/canonical/swe_synth.jsonl` 不得纳入任何训练。
