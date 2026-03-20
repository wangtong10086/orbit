---
from: data
to: strategist
priority: P0
type: report
date: 2026-03-20T02:00
---

# 全面数据审计报告 — v2.2/v2.3 影响分析

## 1. LIVEWEB 训练格式错误（已修复管道，v2.2不可逆）

### 问题
`forge rental prepare-data` 把 LIVEWEB 的 tool_calls 序列化为原始 OpenAI JSON 数组：
```
assistant: [{"id":"call_0","type":"function","function":{"name":"goto",...}}]
```
Qwen3 期望的格式是 `<tool_call>` XML 标签 + system prompt 需要 `<tools>` 工具定义。

### 影响
- v2.2 的 356 条 LIVEWEB 数据**全部格式错误**，已训练完成不可撤回
- 模型学了错误的输出格式，sglang `--tool-call-parser qwen` 无法解析
- **预计 v2.2 LIVEWEB eval ≈ 0 分**
- 其他 3 个 env (GAME/NAVWORLD/SWE-SYNTH) 不受影响（无 tool_calls）

### 已修复
`forge/cli_rental.py` 新增 `_normalize_tool_calls_qwen3()`，v2.3 的 prepare-data 会输出正确格式。已验证与 `tokenizer.apply_chat_template(tools=...)` 输出一致。

## 2. LIVEWEB 插件覆盖严重不足

当前 356 条 canonical 数据分布：
| Plugin | 条数 | 占比 | Eval中活跃? |
|--------|------|------|------------|
| CoinGecko | 339 | 95% | ✅ 8个模板 |
| Stooq | 14 | 4% | ✅ 7个模板 |
| Taostats | 0 | 0% | ✅ 10个模板 |
| HackerNews | 0 | 0% | ✅ 活跃 |
| ArXiv | 0 | 0% | ✅ 活跃 |
| OpenLibrary | 0 | 0% | ✅ 活跃 |
| Hybrid | 0 | 0% | ✅ 活跃 |
| OpenMeteo | 0 | 0% | ✅ 活跃 |
| Weather | 0 | 0% | ❌ 已禁用 |

**模型只学了 CoinGecko 查价格。遇到其他 7 个活跃 plugin 的任务等于盲猜。**

## 3. LIVEWEB 新数据生成管道不可用

`liveweb_real_gen.py` 测试 3/3 失败：
- Claude API proxy (`api.aicodemirror.com`) 大量 503
- 返回格式不兼容 OpenAI SDK (`'str' object has no attribute 'choices'`)
- **需要用户提供可用的 Claude API endpoint**
- TAOSTATS_API_KEY 已确认可用，一旦管道通了可以覆盖 taostats plugin

## 4. LIVEWEB 动作多样性不足

356 条数据中的动作分布：
| Action | 次数 | 说明 |
|--------|------|------|
| goto | 376 | 导航 |
| stop | 356 | 提交答案（每条必有） |
| click | 64 | 点击 |
| type | 24 | 输入 |
| type_role | 4 | |
| click_role | 3 | |
| wait | 3 | |
| scroll | 1 | |

大部分轨迹 = goto → stop。模型几乎没学到复杂页面交互。

## 5. 其他环境数据状态（健康）

| Env | Count | 状态 |
|-----|-------|------|
| GAME | 3316 | ✅ 格式正确，othello仅12条（v2.3待扩充） |
| NAVWORLD | 2624 | ✅ 341条Claude Sonnet QQR≥25 |
| SWE-SYNTH | 983 | ✅ 无变化 |

## 建议

1. **v2.2 eval 照常进行** — LIVEWEB 会接近 0 但 GAME/NAVWORLD/SWE-SYNTH 结果有价值
2. **v2.3 优先修复 LIVEWEB** — 用修复后的 prepare-data + 扩大 plugin 覆盖
3. **请用户解决 Claude API proxy** — 这是 LIVEWEB 新数据生成的唯一阻塞项
4. **考虑 v2.3 暂时减少 LIVEWEB 权重** — 直到 plugin 覆盖和数据量改善
