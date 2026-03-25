---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-25T02:00
---

# CRITICAL: v2.22 eval 必须加 --reasoning-parser qwen3

## 已验证的根因

Qwen3 chat template 有 `enable_thinking` 参数。当前 sglang 启动命令**没有 `--reasoning-parser qwen3`**，导致模板强制插入空 `<think>\n\n</think>`，模型被禁止思考。

这解释了所有版本 GAME think rate = 0% — 不是数据问题，不是 prompt 问题，是**推理配置问题**。

## sglang 0.5.9 已支持

```
--reasoning-parser {deepseek-r1,deepseek-v3,glm45,gpt-oss,kimi,kimi_k2,qwen3,...}
```

## v2.22 eval 时的 sglang 启动命令

```bash
python3 -m sglang.launch_server \
  --model /root/merged_model \
  --tokenizer-path Qwen/Qwen3-32B \
  --dp 4 --tp 1 --port 30000 \
  --tool-call-parser qwen \
  --reasoning-parser qwen3 \
  --host 0.0.0.0 \
  --disable-cuda-graph
```

**唯一变化**：加 `--reasoning-parser qwen3`。其他参数不变。

## 预期效果

- GAME think rate: 0% → 50%+ (模型终于可以输出 think 了)
- GAME score: 28 → 32+? (think 提升决策质量)
- NW: 应该也改善 (think 也帮助 NW 规划)

## 重要

- v2.22 训练不需要改（正在进行中）
- 只需要在训练完成后启动 sglang 时加这个参数
- 这可能是我们最大的单一改进机会
