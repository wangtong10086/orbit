---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-22T10:05
---

# 全面重新评测 + 分析报告（按新规则执行）

## 背景

1. 发现 M2 缺失 AMAP API key，v2.10/v2.11 的 NAVWORLD 评测全部无效
2. Trainer ROLE.md 已新增规则：评测必须保留完整文件 + 写详细分析报告
3. v2.12 训练即将完成（~10:15 UTC）

## 第一步：修复 AMAP API key（最紧急）

M2 `/root/.env` 添加：
```bash
export AMAP_MAPS_API_KEY=f8da77e10334e089a4a5b2ca66273f88
export AMAP_API_KEY=f8da77e10334e089a4a5b2ca66273f88
```

M1 `/root/.env` 添加（M1 缺 AMAP_MAPS_API_KEY）：
```bash
export AMAP_MAPS_API_KEY=f8da77e10334e089a4a5b2ca66273f88
```

修完后验证：`source /root/.env && echo $AMAP_MAPS_API_KEY`

## 第二步：v2.12 评测（训练完成后立即执行）

v2.12 训练即将完成。按标准流程：
1. merge LoRA → start sglang → `source /root/.env` → 确认 AMAP key 已加载
2. 三个环境并行评测：GAME, NAVWORLD, LIVEWEB × 100 samples
3. **保留完整评测文件**：所有 eval JSON 和 log 文件保存在 `/root/logs/eval_v212_*.log`

## 第三步：对最近模型写完整分析报告

检查以下模型是否有完整的评测文件（eval JSON 含每个 sample 的详细输出）：

| 版本 | 需要检查 | 如果缺评测文件 |
|------|---------|--------------|
| v2.7 (BEST) | M1 上是否有完整 eval JSON？ | 用 M1 重新评测（AMAP key 修好后） |
| v2.10 | M2 上有文件但 AMAP 坏了 | **必须用修好的 AMAP key 重新评测** |
| v2.11 | M2 上有文件但 AMAP 坏了 | 如果 v2.11 merged_model 还在，重新评测 NW |
| v2.12 | 即将评测 | 正常评测 |

**优先级**：v2.12 评测 > v2.7 重新评测（确认 baseline）> v2.10 NW 重测

## 第四步：写分析报告

对每个评测完成的版本，在 `eval/v{版本}/report.md` 写详细分析报告：

**每个环境必须单独分析**：
1. 得分统计：均分、非零率、错误率、分数分布
2. 失分原因分析：
   - 零分样本具体是什么原因？（工具调用失败？格式错误？超时？循环重试？）
   - 低分样本为什么低？（缺少哪些信息？哪个 hard constraint 触发了？）
3. 高分样本分析：模型做对了什么？
4. 与前一版本对比：哪些任务进步了，哪些退步了？
5. **具体改进建议**：针对该环境，下一步应该怎么改进数据或训练？

**报告完成后**：
- rsync 所有评测文件到本地 `eval/v{版本}/`
- 通过 inbox 把关键发现发给 Strategist

## 评测文件保存规范

```
eval/
  v2.7/
    eval_game.json        # 完整的每个 sample 详细输出
    eval_navworld.json
    eval_liveweb.json
    eval_v27_game.log     # 评测日志
    eval_v27_navworld.log
    eval_v27_liveweb.log
    report.md             # 分析报告
  v2.12/
    ...（同上）
```

## 关键提醒

- NAVWORLD 评测前必须确认 `echo $AMAP_MAPS_API_KEY` 有输出
- 评测前 `docker rm -f` 旧的 qqr 容器，避免复用带错误配置的容器
- eval base-url 用 `http://172.17.0.1:30000/v1`（Docker bridge）
- `source /root/.env` 必须在启动 eval 的 shell 中执行
