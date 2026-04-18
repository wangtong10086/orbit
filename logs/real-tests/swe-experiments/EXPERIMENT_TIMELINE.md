# SWE Experiment Timeline

更新时间：`2026-04-18`

## 总体时间线

### 阶段 1：确认最小真实链路能否跑通

- `2026-04-17`
  - remote rental smoke 失败
  - 本地 `five-stage` smoke 成功跑通 `sample -> relabel -> build-buckets`
  - 后续实验记录为本地 CPU + Docker + 真实 R2 task

### 阶段 2：扩大搜索，但仍然没有 success

- `2026-04-17`
  - `cascade`
  - `scale-search`
  - `hippo-search`
  - `recipe-search`
  - `python-recipe`

### 阶段 3：修 collector/runtime 诚实性

- `2026-04-17`
  - `logic-fix`
  - `cleanup-and-fix`
  - `realization-shift`
  - `success-prob-rerun`

### 阶段 4：teacher 更强介入，但仍无 success

- `2026-04-17`
  - `teacher-online-judge`

### 阶段 5：checkpoint-tree 与 hypothesis-tree

- `2026-04-17`
  - `checkpoint-tree`
  - 只做到 partial validation
- `2026-04-18`
  - `hypothesis-tree`
  - 三组 fixed-task 完整闭环

## 当前时间线记录范围

当前时间线记录包含：

- `changed_files`
- `syntax_ok`
- `verify_fail`
- `B/C/O/J` 的真实产量

## 文档入口

1. [08_logic_fix_20260417.md](./experiments/08_logic_fix_20260417.md)
2. [11_success_probability_rerun_20260417.md](./experiments/11_success_probability_rerun_20260417.md)
3. [12_teacher_online_judge_20260417.md](./experiments/12_teacher_online_judge_20260417.md)
4. [13_checkpoint_tree_20260417.md](./experiments/13_checkpoint_tree_20260417.md)
5. [14_hypothesis_tree_20260418.md](./experiments/14_hypothesis_tree_20260418.md)
