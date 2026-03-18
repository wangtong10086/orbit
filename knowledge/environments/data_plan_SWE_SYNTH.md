# SWE-SYNTH 数据方案

> 最后更新: 2026-03-18 | 优先级: P0 (免费午餐)

## 现状

| 指标 | 值 |
|------|-----|
| canonical 条数 | 1,351 (含 334 污染) |
| 清洁条数 | 1,017 |
| 分数 | ~31 |
| 榜首 | ~44 (AnastasiaFantasy) |
| GM 贡献潜力 | 31→38 = **+1.2 GM** |
| 数据格式 | multi-turn, THOUGHT + bash code block |
| 无法本地 eval | 需 breaker service |

## 数据质量审计结果

- **Think tag 污染**: 334/1351 (24.7%) 含 `<think>` 标签 — **已清理到 /tmp/swe_synth_cleaned.jsonl**
- 清洁后 1,017 条，全部 score=1.0
- 不支持 think tags (与 THOUGHT 前缀格式冲突)

### 序列长度分析 (清洁数据)

| seq_len | 可完整容纳 | 比例 |
|---------|-----------|------|
| 4,096 tokens | 32 | 3.1% |
| 8,192 tokens | 499 | **49.1%** |
| 16,384 tokens | 1,017 | 100% |

## 瓶颈分析

1. **seq=4096 时 97% 数据被截断**: 模型只学到对话开头，从未见过修复过程
2. **seq=8192 解锁一半数据**: 499 条完整对话 vs 32 条，15.6 倍提升
3. **seq=16384 解锁全部**: 但训练成本翻倍+，需评估 ROI
4. **无法本地验证**: 只能部署后观察排行榜

## 数据行动方案

### 短期 (v1: 清洁数据)
- [x] **清除 think tag 污染**: 1,351 → 1,017 条 (已完成, `/tmp/swe_synth_cleaned.jsonl`)
- [ ] **待 chown 后替换 canonical 文件**
- [ ] 更新 `synth_config.json` count: 1351 → 1017

### 中期 (v2: seq=8192)
- [ ] **训练时改 seq_len=8192**: 可用数据从 32→499 条 (15.6x)
- [ ] 仅用 ≤8192 token 的条目，避免截断
- [ ] 这是"免费午餐" — 仅改训练参数，不需新数据

### 长期 (v3: DPO + 更多数据)
- [ ] 258 对偏好对可用
- [ ] DDB 持续积累更多高分样本
- [ ] 考虑对话压缩: 移除冗余中间输出，保留关键修复步骤

## 格式要求

```
System: [task description]
User: [error/bug description]
Assistant: THOUGHT
[reasoning about the issue]

```bash
[command to investigate/fix]
```

[repeat multi-turn until fix]
```

- 不允许 `<think>` 标签
- Assistant 用 THOUGHT 前缀做推理
- 每轮一个 bash code block
- 最后一条消息必须是 assistant

## 准备文件

| 文件 | 位置 | 条数 | 状态 |
|------|------|------|------|
| canonical (污染) | `data/canonical/swe_synth.jsonl` | 1,351 | root-owned, 需替换 |
| 清洁版 | `/tmp/swe_synth_cleaned.jsonl` | 1,017 | **已就绪**, 待 chown 后复制 |
| 污染备份 | `/tmp/swe_synth_contaminated.jsonl` | 334 | 参考用 |
