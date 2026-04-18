# SWE Experiments Index

更新时间：`2026-04-18`  
位置：`logs/real-tests/swe-experiments/`

## 目的

这个目录是 SWE 数据收集实验的专用汇总入口。  
它不替代原始 artifact 目录，而是把分散在 `logs/real-tests/swe-*` 下的实验记录统一收束成：

- 当前架构状态
- 时间线与阶段性结论
- 每轮实验的独立总结文档

## 保密说明

本目录位于 `logs/` 下。当前 public export 规则排除了 `logs/**`，因此这里的文档只会存在于私有仓库。

## 推荐阅读顺序

1. [CURRENT_ARCHITECTURE_AND_STATUS.md](./CURRENT_ARCHITECTURE_AND_STATUS.md)
2. [EXPERIMENT_TIMELINE.md](./EXPERIMENT_TIMELINE.md)
3. 按实验编号阅读 `experiments/`

## 当前状态结论

- 当前 SWE collector 已经演进为 staged data-side subsystem
- active `sample` 路径已经是：
  - hidden oracle
  - issue rubric
  - localization shortlist
  - patch-plan shortlist
  - checkpointed realization-tree search
- 最新一轮 active realization 搜索策略是：
  - root race
  - repair-hypothesis tree
  - multi-fidelity backup
- 当前真实 fixed-task 验证仍然没有采到 `A` 或 `T` success
- 但 collector/runtime 现在已经足够诚实，失败大多能被解释为模型/patch 质量问题而不是采集器吞轨迹

## 文档结构

- [CURRENT_ARCHITECTURE_AND_STATUS.md](./CURRENT_ARCHITECTURE_AND_STATUS.md)
- [EXPERIMENT_TIMELINE.md](./EXPERIMENT_TIMELINE.md)
- `experiments/`
  - [01_remote_rental_smoke_20260417.md](./experiments/01_remote_rental_smoke_20260417.md)
  - [02_five_stage_smoke_20260417.md](./experiments/02_five_stage_smoke_20260417.md)
  - [03_cascade_smoke_20260417.md](./experiments/03_cascade_smoke_20260417.md)
  - [04_scale_search_20260417.md](./experiments/04_scale_search_20260417.md)
  - [05_hippo_search_20260417.md](./experiments/05_hippo_search_20260417.md)
  - [06_recipe_search_20260417.md](./experiments/06_recipe_search_20260417.md)
  - [07_python_recipe_20260417.md](./experiments/07_python_recipe_20260417.md)
  - [08_logic_fix_20260417.md](./experiments/08_logic_fix_20260417.md)
  - [09_cleanup_and_fix_20260417.md](./experiments/09_cleanup_and_fix_20260417.md)
  - [10_realization_shift_20260417.md](./experiments/10_realization_shift_20260417.md)
  - [11_success_probability_rerun_20260417.md](./experiments/11_success_probability_rerun_20260417.md)
  - [12_teacher_online_judge_20260417.md](./experiments/12_teacher_online_judge_20260417.md)
  - [13_checkpoint_tree_20260417.md](./experiments/13_checkpoint_tree_20260417.md)
  - [14_hypothesis_tree_20260418.md](./experiments/14_hypothesis_tree_20260418.md)

## 关联的老文档

- [SWE_COLLECTION_ARCH_AND_TEST_STATUS_20260418.md](../SWE_COLLECTION_ARCH_AND_TEST_STATUS_20260418.md)
- [SWE_COLLECTION_RESEARCH_NOTES_20260417.md](../SWE_COLLECTION_RESEARCH_NOTES_20260417.md)
- [SMOKE_LEDGER.md](../SMOKE_LEDGER.md)
