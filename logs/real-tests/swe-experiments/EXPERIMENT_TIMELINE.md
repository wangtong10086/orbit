# SWE Experiment Timeline

更新时间：`2026-04-18`

## 总体时间线

### 阶段 1：确认最小真实链路能否跑通

- `2026-04-17`
  - remote rental smoke 失败
  - 本地 `five-stage` smoke 成功跑通 `sample -> relabel -> build-buckets`
  - 结论：先放弃远端 rental，改走本地 CPU + Docker + 真实 R2 task

### 阶段 2：扩大搜索，但仍然没有 success

- `2026-04-17`
  - `cascade`
  - `scale-search`
  - `hippo-search`
  - `recipe-search`
  - `python-recipe`
- 结论：
  - 单纯加大 localization / search budget 不够
  - 只换 student 模型也不够

### 阶段 3：修 collector/runtime 诚实性

- `2026-04-17`
  - `logic-fix`
  - `cleanup-and-fix`
  - `realization-shift`
  - `success-prob-rerun`
- 结论：
  - 这一步之后，失败才开始变得可信
  - 很多早期 “完全不会做” 的结论需要重审

### 阶段 4：teacher 更强介入，但仍无 success

- `2026-04-17`
  - `teacher-online-judge`
- 结论：
  - teacher 在线介入显著改变了漏斗
  - 但依然没拿到 `A` 或 `T`

### 阶段 5：checkpoint-tree 与 hypothesis-tree

- `2026-04-17`
  - `checkpoint-tree`
  - 只做到 partial validation
- `2026-04-18`
  - `hypothesis-tree`
  - 三组 fixed-task 完整闭环
- 结论：
  - 新树真实可运行
  - 但 feasibility gate 仍未通过

## 当前阶段判断

当前实验已经进入：

- 不再证明“collector 有没有把轨迹吞掉”
- 而是在证明“哪种搜索策略最有机会把高价值分支扶进 success”

目前最有价值的证据不是 `A`，而是：

- `changed_files`
- `syntax_ok`
- `verify_fail`
- `B/C/O/J` 的真实产量

## 推荐阅读顺序

1. [08_logic_fix_20260417.md](./experiments/08_logic_fix_20260417.md)
2. [11_success_probability_rerun_20260417.md](./experiments/11_success_probability_rerun_20260417.md)
3. [12_teacher_online_judge_20260417.md](./experiments/12_teacher_online_judge_20260417.md)
4. [13_checkpoint_tree_20260417.md](./experiments/13_checkpoint_tree_20260417.md)
5. [14_hypothesis_tree_20260418.md](./experiments/14_hypothesis_tree_20260418.md)
