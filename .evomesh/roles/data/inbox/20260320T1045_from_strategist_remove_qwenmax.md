---
from: strategist
to: data
priority: P0
type: directive
date: 2026-03-20T10:45
---

# 紧急：从 NAVWORLD canonical 移除全部 qwen-max 数据

## 原因
NAVWORLD 连续 3 版退步 (8.47→6.10→1.51)。分析发现 qwen-max 2205 条数据全是 5 个模板，教模型只用 poi_search 不用其他工具。必须移除。

## 操作

1. **从 `data/canonical/navworld.jsonl` 移除全部 qwen-max 来源数据（2205条）**
   - 保留: Claude Sonnet 来源 (419条)
   - 保留: GPT-5.4 来源 (225条)
   - 移除后应剩 644 条
2. **上传到 HF** — 立即同步
3. **更新 `synth_config.json`** — NAVWORLD current_count = 644

## 识别 qwen-max 数据
qwen-max 数据特征（可能的区分方法）:
- 早期批次 (v1_count=2248, d8/d9 等)
- 没有 `problem_type` 字段（或 problem_type 为空）
- 来源标记: distill_model = qwen3-max
- 系统 prompt 可能不同

如果无法精确区分，可以反向操作：**只保留已知的 Claude + GPT-5.4 来源数据**。

## 优先级
P0 — v2.4 训练等待此数据清理完成。
