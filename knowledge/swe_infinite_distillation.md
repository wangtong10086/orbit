# SWE-Infinite 蒸馏方案

## 方法

**真实 Docker 蒸馏**（唯一可用方案）

```
私有 R2 池 (2500+ 任务) → GPU 机器 docker pull → GPT-5.4 agent 多轮交互
→ 提取 patch → 新容器验证测试 → score=1.0 才保留 → JSONL
```

## 为什么不用合成数据

合成轨迹（GPT-5.4 生成的假观察值）**已验证无效**：
- 假终端输出 avg 11K chars vs 真实 36K chars
- 模型学到错误的代码上下文分布
- 可能降低而非提升评测得分

## API 稳定性对策

代理 API (`api.aicodemirror.com`) 返回 520/504 概率 ~50%。当前配置：
- **15 次重试**，15-120s 指数退避
- **1800s 超时**（长 prompt 需要）
- **自动 re-queue**：0-turn 失败的任务 batch 结束后重跑
- **`--resume`**：中断后自动跳过已完成的

## 产出预估

- 私有池 ~2500 任务，patch ≤ 8K 的 ~1841 个可用
- API 有效率 ~50%，模型修复率 ~30% → 预计 **~275 条**
- 当前进度：11 条已验证（batch 刚启动）

## 工具

| 文件 | 用途 |
|------|------|
| `scripts/swe_distill.py` | 真实 Docker 蒸馏（`--task-file` 支持私有池任务） |

## 数据格式

```json
{
  "messages": [system, user(problem), assistant(THOUGHT+bash), user(observation), ...],
  "env": "SWE-INFINITE",
  "score": 1.0
}
```

匹配 `repos/affinetes/environments/SWE-INFINITE/agents/config.yaml` 的完整 eval 模板。
