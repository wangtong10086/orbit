# SWE Current Architecture And Status

更新时间：`2026-04-18`

## 当前 active 架构

当前 SWE 数据收集属于 `orbit/data/swe_collection/` 下的数据侧子系统，不属于 ORBIT control-plane core，也不属于 execution-plane core。

active pipeline：

1. `sample`
2. `relabel`
3. `build-buckets`
4. `train-verifier`

其中真正决定成功率和轨迹质量的是 `sample`。

## 当前 `sample` 主路径

当前在线收集结构：

1. 从真实 R2 / task cache 读取 SWE task
2. 创建隔离 Docker workspace
3. 构建 hidden oracle
4. 调一次 issue-level rubric
5. student 做 localization 候选
6. teacher/rule 对 localization shortlist 重排
7. student 做 patch-plan 候选
8. teacher/rule 对 patch-plan shortlist 重排
9. realization 进入 checkpointed tree search
10. 每次 patch 尝试走 verify funnel：
   - syntax
   - cheap targeted verify
   - full verify
11. near-miss 失败进入 `relabel`
12. 最终进入 `A/T/B/C/J/O/V` 分桶

## 当前 realization 搜索形态

最新 active 版本已经是：

- root race
- repair-hypothesis tree
- multi-fidelity backup

具体含义：

- root 不再一开始就完全按 teacher prior 选，而是先轮流 race
- 树上持久化的是 hypothesis，而不是直接持久化 patch edge
- value 不再只看单个 `value_mean`，而是综合：
  - full verify
  - cheap verify
  - syntax
  - progress
  - dead-end

## 当前 teacher 角色

teacher 当前只承担三类职责：

1. issue-level rubric constructor
2. online node summary / prior / value / repair-hypothesis proposer
3. offline near-miss repair annotator

teacher 不再做 end-to-end takeover。

## 当前分桶语义

- `A`: autonomous success
- `T`: teacher-shaped success
- `B`: critical-step correction
- `C`: patch repair
- `J`: online teacher intervention slices
- `O`: oracle-completed near-miss
- `V`: verifier rows

边界：

- `A` 必须保持 pure student
- 任何 teacher-shaped success 只能进 `T`
- `canonical/` 仍只吃 `A`

## 当前最可信的结论

- collector/runtime 诚实性已经显著提升
- 现在大部分失败更像真实 patch 质量问题
- localization 并不是完全失效
- 当前主瓶颈仍然是 realization 最后一跳

## 当前未完成目标

截至现在，固定真实任务验证仍没有采到：

- `A > 0`
- 或 `T > 0`

所以当前状态更像：

- “研究基础设施已经可用”
- 但“搜索策略已经被证明可行”这件事还没有成立

## 主要参考

- [SWE_COLLECTION_ARCH_AND_TEST_STATUS_20260418.md](../SWE_COLLECTION_ARCH_AND_TEST_STATUS_20260418.md)
- [SWE_COLLECTION_RESEARCH_NOTES_20260417.md](../SWE_COLLECTION_RESEARCH_NOTES_20260417.md)
- [14_hypothesis_tree_20260418.md](./experiments/14_hypothesis_tree_20260418.md)
