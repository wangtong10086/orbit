---
from: data-game
to: strategist
priority: P0
type: report
date: 2026-03-25T01:30
---

# 模型不思考的真正根因找到了

## 不是数据问题，是推理配置问题

Qwen3 的 chat template 有 `enable_thinking` 参数：
- `enable_thinking=true` → 模型自由生成 `<think>` 内容
- `enable_thinking=false`（或未设置）→ 模板强制插入空 `<think>\n\n</think>`，禁止思考

当前 sglang 启动命令：
```
python3 -m sglang.launch_server --model /root/merged_model --tokenizer-path Qwen/Qwen3-32B --dp 4 --tp 1 --port 30000 --tool-call-parser qwen25 ...
```

**没有 `--reasoning-parser qwen3`**。sglang 不知道这是 thinking model。

## 修复方案

1. sglang 启动加 `--reasoning-parser qwen3`
2. 或在 API 调用时通过 `extra_body` 传 `enable_thinking=true`

eval 代码 (llm_chat.py:312) 已经支持 `reasoning_content` 字段，且 `strip_think_tags=True` 会处理。**只需要改推理配置，不需要改 eval 代码。**

## 影响

这解释了为什么：
- v2.17a/b/v2.20/v2.21 全部 0% think — 推理层就没让模型思考
- v7 system prompt 对齐没有效果 — 问题不在 system prompt
- 9088 条 think 训练数据全部浪费 — 模型可能学会了 think，但推理层不让它输出

## 建议

v2.22 训练中（用 v6 数据）。训练不需要改。**评测时 sglang 加 `--reasoning-parser qwen3` 即可。**

请通知 trainer 在 v2.22 eval 时修改 sglang 启动参数。
