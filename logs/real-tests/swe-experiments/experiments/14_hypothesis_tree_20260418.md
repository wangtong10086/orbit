# 14. Hypothesis Tree

实验目录：`logs/real-tests/swe-hypothesis-tree-20260418/`  
原始记录：[README.txt](../../swe-hypothesis-tree-20260418/README.txt)

## 目标

- 在 checkpoint-tree 基础上继续改成：
  - root race
  - repair-hypothesis tree
  - multi-fidelity backup
- 用三组 fixed-task 直接验证 feasibility

## 过程

- student / teacher / docker probes 正常
- 三组任务全部完成：
  - `sample`
  - `relabel`
  - `build-buckets`
- 新增真实 artifacts：
  - `search/checkpoints.jsonl`
  - `search/hypotheses.jsonl`
  - `search/nodes.jsonl`
  - `search/teacher_state_summaries.jsonl`

## 结果

### mini-rubocop

- `sampled_trajectories=4`
- `success=0`
- `changed_files=3/4`
- `syntax_ok=1/4`
- `verify_fail=1/4`
- `root_nodes_total=4`
- `root_race_rounds_run=2`
- `hypothesis_nodes_total=16`
- `hypothesis_children_total=7`
- `teacher_hypotheses_total=5`
- buckets:
  - `A=0 B=2 C=2 J=12 O=3 T=0 V=4`

### codex-geopy

- `sampled_trajectories=4`
- `success=0`
- `changed_files=0/4`
- `syntax_ok=0/4`
- `verify_fail=0/4`
- `hypothesis_nodes_total=15`
- `hypothesis_children_total=0`
- buckets:
  - `A=0 B=0 C=0 J=11 O=0 T=0 V=4`

### codex-rails

- `sampled_trajectories=4`
- `success=0`
- `changed_files=3/4`
- `syntax_ok=0/4`
- `verify_fail=0/4`
- `hypothesis_nodes_total=16`
- `hypothesis_children_total=6`
- buckets:
  - `A=0 B=2 C=2 J=12 O=3 T=0 V=4`

## 汇总计数

- 三组任务合计：
  - `A=0`
  - `T=0`
