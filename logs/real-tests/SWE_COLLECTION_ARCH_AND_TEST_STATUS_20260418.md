# SWE 数据收集架构与测试状态（内部）

更新时间：`2026-04-18`  
适用代码状态：当前私有仓库 working tree  
用途：给后续 SWE 数据收集研究、collector 改造、模型/策略 ablation 提供一份集中、可追溯的内部参考

## 保密说明

本文件位于 `logs/real-tests/` 下。当前 public snapshot 导出规则
`release/public-export.yaml`
明确排除了 `logs/**`，因此本文件只会存在于私有仓库，不会进入公开仓库。

## 1. 当前 active 架构概览

### 1.1 总体路径

当前 ORBIT 内部的 SWE 收集主线已经不再是早期 `affine-swarm` 风格的 teacher takeover，也不是最早的单模型 `teacher-guided solve`。当前 active path 是一个分阶段 collector：

1. `sample`
2. `relabel`
3. `build-buckets`
4. `train-verifier`

其中真正最核心的在线执行逻辑在 `sample`。

### 1.2 关键模块

- `orbit/data/swe_collection/collector.py`
  - orchestrator
  - 当前 active `sample` 主路径
  - localization / plan / realization tree orchestration
- `orbit/data/swe_collection/runtime.py`
  - Docker workspace runtime
  - shell exec
  - git diff / patch hash
  - cheap checks
  - checkpoint capture / restore
- `orbit/data/swe_collection/sessions.py`
  - student / teacher 的 OpenAI-compatible 会话
  - MiniSWE / Codex 两套 student schema
  - teacher rubric / teacher state summary / critique
- `orbit/data/swe_collection/relabel.py`
  - near-miss failure point 定位
  - offline repair critique
- `orbit/data/swe_collection/buckets.py`
  - `A/T/B/C/J/O/V` 分桶
- `orbit/foundation/data_contracts.py`
  - raw trajectory / step state / failure point / critique / buckets / checkpoints / nodes / teacher summary 等 contract

### 1.3 当前 `sample` 的实际结构

当前 `sample` 不是简单线性 rollout，而是：

1. task source 从真实 R2 / task cache 读取 SWE task
2. runtime 创建隔离 Docker workspace
3. hidden oracle 从 ground-truth patch 派生离线标签
4. teacher 最多做一次 issue-level rubric 构造
5. student 做 localization 候选
6. teacher/rule 对 localization shortlist 重排
7. student 做 patch plan 候选
8. teacher/rule 对 plan shortlist 重排
9. realization 阶段进入 checkpointed tree search
10. 每个 changed patch 走 verify funnel：
   - syntax
   - cheap targeted verify
   - full verify（预算受限）
11. 失败轨迹进入 `relabel`
12. 最后由 `build-buckets` 生成训练桶

### 1.4 realization 当前的 active 设计

当前 active realization 不是旧的线性队列，而是“checkpoint + teacher state summary”的低成本类树搜索：

- runtime 持有真实可回退状态
- checkpoint 只保存小规模 working tree 文本快照，不做容器克隆
- 每个 search node 都绑定一个真实 checkpoint
- teacher 不定义真实状态，只提供：
  - state summary
  - prior
  - value
  - branch proposals
- student 和 teacher proposal 共用同一 patch action schema
- duplicate patch hash 会被剪枝
- full verify 预算单独受限

当前已经落盘的 search artifacts：

- `search/checkpoints.jsonl`
- `search/nodes.jsonl`
- `search/teacher_state_summaries.jsonl`
- 兼容保留：
  - `search/branches.jsonl`
  - `search/judge_decisions.jsonl`

### 1.5 当前 teacher 介入机制

teacher 现在有三类角色：

1. issue-level rubric constructor
   - 每个 issue 最多 1 次
   - 作用是生成 likely modules / constraints / pseudo-solution warnings
2. online node summary / branch proposal
   - 在 active `sample` tree search 中在线介入
   - 不是逐 token takeover，而是节点级 prior / value / proposal
3. offline near-miss repair annotator
   - 在 `relabel` 阶段做 critique / revised action

当前 purity 边界：

- `A`：纯 student success
- `T`：teacher-shaped success
- `A` 继续是唯一允许进入 canonical 的成功桶

## 2. 当前分桶语义

当前训练桶不是简单的“每条轨迹只进一个桶”，而是按样本类型生成：

- `A`
  - autonomous verified success
- `T`
  - teacher-shaped verified success
- `B`
  - critical-step correction
  - `state -> corrected next step`
- `C`
  - patch repair
  - `failed diff/logs/current state -> minimal repair`
- `J`
  - online teacher judge / node summary / branch intervention slices
- `O`
  - oracle-completed near-miss
- `V`
  - verifier / PRM rows

当前 bucket 设计的重点不是只追 `A`，而是尽量把真实 near-miss 失败转成可训练样本。

## 3. 代码级验证现状

当前 collector 相关 targeted regression 持续跑的是：

```bash
./.venv/bin/python -m pytest -q tests/test_swe_collection.py tests/test_data_cli.py tests/test_env.py tests/test_data_ops.py -q
```

另外还多次跑过：

```bash
./.venv/bin/python -m orbit data swe-collect sample --help
./.venv/bin/python -m py_compile orbit/data/swe_collection/collector.py orbit/data/swe_collection/runtime.py orbit/data/swe_collection/sessions.py orbit/data/swe_collection/buckets.py orbit/data/swe_collection/exporter.py orbit/data/swe_collection/smoke.py orbit/foundation/data_contracts.py orbit/tasks/collection/specs.py orbit/cli_data.py tests/test_swe_collection.py
```

这些验证的目标主要是：

- parser/schema compatibility 不回退
- CLI surface 可见
- checkpoint/tree-search 代码至少语法和局部行为正确

需要强调：

- 代码级验证是通过的
- 但真实可行性验证还没有达到“至少 1 条 `A` 或 `T` success”的门槛

## 4. 真实测试记录摘要

下面只记录对当前研究判断最重要的几轮。

### 4.1 五阶段初版真实 smoke

目录：

- `logs/real-tests/swe-five-stage-smoke-20260417/`

结论：

- `sample -> relabel -> build-buckets` 能在真实 R2 task 上跑通
- `MiniSWE` 和 `Codex` 都能产出 raw failure + critique + `B/C/V`
- 但 `A=0`

意义：

- 证明 failure-centric collector 链路成立
- 还不足以证明能采到正确轨迹

### 4.2 cascade / hidden-oracle 路径

目录：

- `logs/real-tests/swe-cascade-smoke-20260417/`

结论：

- `MiniSWE` 出现了 near-miss repair
- `Codex` 至少能产出 raw + failure point + `V`
- 但 success 仍为 0

意义：

- 表明“纯 student rollout + 离线重标注”比早期 teacher takeover 更可控
- 但 `Codex` 仍然脆弱

### 4.3 recipe / scale search / hippo 切换

目录：

- `logs/real-tests/swe-recipe-search-20260417/`
- `logs/real-tests/swe-scale-search-20260417/`
- `logs/real-tests/swe-hippo-search-20260417/`

结论：

- 单纯扩大 localization/search budget 不能直接带来 success
- 把 student 从 `Qwen/Qwen3-32B-TEE` 换到 `hippo-master/...` 也没有直接出现 verified success

意义：

- 主矛盾不只是“搜索不够大”
- collector/runtime 的诚实性和 patch realization 质量更关键

### 4.4 logic-fix / cleanup-and-fix

目录：

- `logs/real-tests/swe-logic-fix-20260417/`
- `logs/real-tests/swe-cleanup-and-fix-20260417/`

修过的关键问题：

- MiniSWE 未闭合 bash fence 被误判空动作
- Codex 文本 `<tool_call>` 被忽略
- run manifest 统计失真
- submit 后重复 verify
- Docker 根盘耗尽污染实验
- teacher probe / student probe / docker probe 缺失

结论：

- 在这之后，大量失败已经从“fake no_patch”变成“真实 changed-files / verify_fail”
- 从这一轮开始，collector 结论才逐渐可信

### 4.5 success-prob rerun

目录：

- `logs/real-tests/swe-success-prob-rerun-20260417/`

关键变化：

- existence-aware shortlist
- span-catalog realization
- auto-verify / cheap verify funnel
- 更宽的 near-miss / `O` gate

最重要结果：

- `codex-geopy` 明显改善
- 已经从早期的空跑推进到：
  - 真实 edit
  - 真实 cheap verify
  - 真实 verify fail
  - `B/C/O/V` 非空

意义：

- 证明 `codex` 在 Python 任务上不是完全没有希望
- 也证明 runtime file-context / span-catalog bug 会直接决定实验结论

### 4.6 teacher-online-judge

目录：

- `logs/real-tests/swe-teacher-online-judge-20260417/`

这是当前 collector 演进中的一个关键中间态。  
这一轮已经把 teacher 从“1 次 rubric + 离线 repair”升级到了在线分叉/裁剪机制。

可训练样本产出：

- `mini-rubocop`
  - `B=2`
  - `C=2`
  - `J=10`
  - `O=3`
  - `V=3`
- `codex-geopy`
  - `B=1`
  - `C=1`
  - `J=9`
  - `O=1`
  - `V=3`
- `codex-rails`
  - `B=2`
  - `C=2`
  - `J=16`
  - `O=3`
  - `V=3`

结论：

- 这轮仍然没有 `A` 或 `T`
- 但 teacher online 已经显著改变了 funnel，尤其是 `J` / `O` 的产量
- 说明 teacher 在线介入更适合作为“分叉器/裁剪器/纠偏器”，而不是全程带跑

### 4.7 checkpoint-tree search

目录：

- `logs/real-tests/swe-checkpoint-tree-20260417/`

这是当前 active `sample` 主路径的第一次真实验证。  
它的意义大于结果本身，因为这里开始使用 runtime-held checkpoints + teacher state summaries。

当前结论：

- code implementation：通过
- targeted regression：通过
- real fixed-task feasibility validation：仍未完成到满足门槛

已确认的事实：

- 真实 run 能写出：
  - `search/checkpoints.jsonl`
  - `search/nodes.jsonl`
  - `search/teacher_state_summaries.jsonl`
- `mini-rubocop` / `codex-rails` 都已经在真实任务上跑活了 checkpoint-tree 主路径
- 但还没有出现第一条 `A` 或 `T`

阻塞不是本地 Docker/runtime 彻底坏掉，而是：

- repeated localization / plan / summary 请求的 inference RTT 仍然很高
- student/teacher 产出的 patch 仍然经常“方向接近但 patch 质量不足”

## 5. 已确认并修复的关键问题

### 5.1 parser / schema 问题

已修过的真实问题包括：

- MiniSWE 未闭合 bash fence 提取
- Codex content-form `<tool_call>` fallback
- nested `patch` action 兼容
- `patch.actions`
- `patch.edits`
- `patch.hunks`
- `patch=[...]`
- `patch_type=edit_lines`
- `patch_type=edit`
- `before/after`
- `from/to`
- `*** Begin Patch ...` 字符串 patch
- `file_id -> target_file` 回填

这些问题如果不修，会直接把真实 student 动作误判成 `no_action` 或 `invalid_target`。

### 5.2 runtime / workspace 问题

已修过：

- `_copy_text_from_container()` 读空文件，导致 context/span-catalog 实际失效
- `docker rm -f` cleanup 超时会把 sample 命令打崩
- structured patch action 过度依赖目标镜像里有 `python`

### 5.3 orchestration / policy 问题

已修过：

- `_collect_patch_plans()` 只保留最后一个 plan
- auto-verify 之前的 `patch exists + syntax_ok + no_action` 会被误记成 `quality_fail`
- run manifest 统计写成 shortlist 数，不是实际生成数
- `sample` 没有 student/teacher/docker probes
- teacher probe 失败会整题中止，而不是 degraded sampling

### 5.4 checkpoint-tree 阶段新增修复

这一轮又修过：

- root teacher summary eager 串行导致首步过慢
- OpenAI-compatible 请求单次 timeout 过长
- duplicate/no-progress patch 被误当成新 child
- teacher proposal 没过统一 normalization
- teacher proposal 没有足够 guardrail，会在第一步抢占 student 但给出空洞/过大的 replace

## 6. 当前最可信的结论

### 6.1 collector 现在已经比早期诚实得多

早期很多“完全不会做”的判断不可信，因为当时确实存在 parser/runtime bug，会把真实动作吞掉。  
现在 collector 虽然还不完美，但大部分失败已经更像真实失败，而不是采集器伪造的失败。

### 6.2 localization 并不是完全失效

当前反复出现的信号是：

- student/teacher 能多次命中正确文件邻域
- 部分任务能进入真实 changed-files / syntax / verify
- `B/C/O/J` 样本已经稳定产出

所以主瓶颈更像是：

- patch 落地质量
- span 选择粒度
- over-large replace
- teacher proposal 虽然方向对，但经常太粗

### 6.3 当前最弱的一环仍然是 realization 最后一跳

现象包括：

- inspect-only
- invalid target / invalid span
- 大段 replace 语义上偏离最小修复
- syntax 通过但 verify fail
- near-miss 很多，但 autonomous success 还没出来

所以后续继续扩大 localization 通常收益不会最高；更值得花预算的是：

- 更细粒度的 patch emission
- 更好的 span-size 约束
- 更强的 revise/rollback policy

## 7. 当前尚未满足的目标

截至本文件更新时间，仍然没有满足最初的 feasibility 目标：

- 三组 fixed tasks 上至少拿到 1 条 `A` 或 `T`

也就是说：

- code path 已重构
- unit/targeted regression 已经稳定
- 真实运行漏斗明显改善
- 但“至少一条真实成功轨迹”仍未达成

这意味着当前系统更接近“可靠的研究基础设施”，还不是“已经证明确实有效的高成功率采集器”。

## 8. 后续研究优先级建议

按当前证据，下一轮最值得做的不是继续泛化 collector，而是更窄地打 realization：

1. 强化 `replace` 动作与 span-size 的比例约束
   - 避免 teacher/student 用单个 span 承载过大的替换内容
2. 对 `Codex` 单独优化 patch emission
   - 尤其是 `rails` 这类任务，避免正确文件上仍然大块改坏
3. 对 `MiniSWE` 保留专用 fallback
   - 不要简单强行复用和 `Codex` 完全一样的 `file_id/span_id` 约束
4. 保持 `teacher online`，但继续收紧 proposal guardrail
   - teacher 应该更像 prior/value/repair proposer，而不是粗粒度 patch writer
5. 在拿到第一条 `A` 或 `T` 之前，不要把 learned verifier 升级成主优先级

## 9. 相关内部记录

主要参考：

- `logs/real-tests/SWE_COLLECTION_RESEARCH_NOTES_20260417.md`
- `logs/real-tests/SMOKE_LEDGER.md`
- `logs/real-tests/swe-five-stage-smoke-20260417/README.txt`
- `logs/real-tests/swe-cascade-smoke-20260417/README.txt`
- `logs/real-tests/swe-success-prob-rerun-20260417/README.txt`
- `logs/real-tests/swe-teacher-online-judge-20260417/README.txt`
- `logs/real-tests/swe-checkpoint-tree-20260417/README.txt`

本文件的角色是把这些分散记录收束成一份“当前状态总览”，供后续研究直接接手。
