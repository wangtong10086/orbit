# SWE 轨迹收集研究笔记（内部）

更新时间：`2026-04-17`  
私有源码提交：`258ccc31620a7fe01c51e20689772cb4c979d381`

## 保密说明

本文件放在 `logs/real-tests/` 下，当前 public snapshot 导出规则
[`release/public-export.yaml`](/home/ubuntu/orbit/release/public-export.yaml:42)
明确排除了 `logs/**`，因此本文件不会发布到公开仓库。

## 目的

这份文档用于给后续 SWE 轨迹收集方法研究提供连续、可追溯的内部背景，重点记录：

- 当前 ORBIT 中 SWE 收集系统已经演进到什么状态
- 实际跑过哪些真实实验
- 每一轮实验的结果和暴露的问题
- 已经确认并修复了哪些 collector / runtime / environment 问题
- 目前还没解决的核心瓶颈是什么
- 接下来应该如何设计新的研究实验，而不是重复走已经证伪的路径

## 一、当前系统状态

### 1. 收集路径的现状

当前私有仓库中的 SWE 收集主线已经不再是早期的 `affine-swarm` 风格全程 teacher takeover，而是 ORBIT 内部自建的 staged collector：

- `sample`
  - hidden oracle
  - issue-level rubric
  - localization shortlist
  - patch-plan shortlist
  - full realization on shortlisted candidates
- `relabel`
  - 对 near-miss 失败轨迹做 teacher critique / minimal repair
- `build-buckets`
  - 生成 `A/B/C/V`
- `train-verifier`
  - 从 `V` 桶产 verifier / PRM 训练集

核心实现位于：

- [orbit/data/swe_collection/collector.py](/home/ubuntu/orbit/orbit/data/swe_collection/collector.py:1)
- [orbit/data/swe_collection/sessions.py](/home/ubuntu/orbit/orbit/data/swe_collection/sessions.py:1)
- [orbit/data/swe_collection/relabel.py](/home/ubuntu/orbit/orbit/data/swe_collection/relabel.py:1)
- [orbit/data/swe_collection/runtime.py](/home/ubuntu/orbit/orbit/data/swe_collection/runtime.py:1)
- [orbit/foundation/data_contracts.py](/home/ubuntu/orbit/orbit/foundation/data_contracts.py:390)

### 2. 当前已经具备的关键能力

截至 `258ccc3`，以下能力已经在代码和真实运行中被验证：

- student / teacher / Docker probe gating
- teacher 失效时 `sample` 自动降级到 `no-rubric sampling`
- sample-level unique instance id，避免 `swe-sync` 只保留同一 issue 的一条轨迹
- MiniSWE 未闭合 bash fence 兼容
- Codex 文本型 `<tool_call>{...}</tool_call>` 兼容
- `no_patch` 细分为 collector-side failure 与 student-side no-action
- `relabel` 跳过 collector-side failure
- run manifest 记录真实 `localization_candidates` / `patch_plan_candidates`

### 3. 当前还没有做到的事

截至目前，系统仍然**没有采到 verified-correct trajectory**。  
但与早期阶段不同，现在的大部分失败已经可以比较可信地解释为：

- student 质量不够
- prompt / action space 不够好
- teacher availability 波动
- 小步数预算下的策略过于保守或过于粗暴

而不是 collector 本身把正确轨迹吞掉。

## 二、实验时间线与结果

下面按时间顺序记录主要里程碑。

### 1. 远端 rental smoke 失败

记录：

- [SMOKE_LEDGER.md](/home/ubuntu/orbit/logs/real-tests/SMOKE_LEDGER.md:214)

结果：

- remote Mini/Codex smoke 都失败
- 不是方法问题，而是远端环境问题：
  - rental SSH bootstrap 不稳定
  - teacher endpoint 假设不稳定

结论：

- 远端 rental 不是当时合适的主验证路径
- 后续转向本地 CPU + Docker + 真实 R2 task 的小规模真实收集

### 2. 五阶段初版真实 smoke

记录：

- [logs/real-tests/swe-five-stage-smoke-20260417/README.txt](/home/ubuntu/orbit/logs/real-tests/swe-five-stage-smoke-20260417/README.txt:1)

结果摘要：

- MiniSWE:
  - raw=1
  - failure point=1
  - critique=1
  - `B/C/V` 非空
- Codex:
  - raw=1
  - failure point=1
  - critique=1
  - `B/C/V` 非空
- `A=0`

暴露的问题：

- Codex 初版请求格式有协议错误
- relabel / buckets / manifest 的 append/rebuild 语义不合理

结论：

- 五阶段 failure-centric 路径可以在真实任务上跑通
- 但还远不足以证明“能采到正确轨迹”

### 3. hidden-oracle + rubric + cascade 策略 smoke

记录：

- [logs/real-tests/swe-cascade-smoke-20260417/README.txt](/home/ubuntu/orbit/logs/real-tests/swe-cascade-smoke-20260417/README.txt:1)

结果摘要：

- Mini:
  - near-miss repair 成功出现
  - `B/C/V` 非空
- Codex:
  - raw + failure point + `V`
  - 但未过 near-miss gate

暴露的问题：

- Mini student 响应超长导致 timeout
- Codex 可能 plain-text 回复而不发 tool call

结论：

- 新策略在真实任务上比五阶段初版更接近“可控失败”
- 但 Codex 分支仍然很脆弱

### 4. 扩搜索但仍然 0 成功

记录：

- [logs/real-tests/swe-scale-search-20260417/README.txt](/home/ubuntu/orbit/logs/real-tests/swe-scale-search-20260417/README.txt:1)

模型：

- `Qwen/Qwen3-32B-TEE`

结果：

- 总计真实 trajectory：`12`
- verified success：`0`

现象：

- `mini-rubocop` 多次改到正确文件附近，但 patch 质量不够
- Codex 多数仍然 `no_patch`

结论：

- 结构化搜索本身有价值
- 但 student 模型质量已经成为主要瓶颈

### 5. 切换到 `hippo-master/...` 仍无成功

记录：

- [logs/real-tests/swe-hippo-search-20260417/README.txt](/home/ubuntu/orbit/logs/real-tests/swe-hippo-search-20260417/README.txt:1)

模型：

- `hippo-master/affine-17-5D7H7grKtvLJLy9GJWX8HEx2Z4swukjb9f8jAySR21UQEK9c`

结果：

- 总计真实 trajectory：`12`
- verified success：`0`

结论：

- 单纯把 student 从 `Qwen/Qwen3-32B-TEE` 切到 `hippo-master/...`，在当时 collector 状态下并没有直接采到成功轨迹

### 6. 按用户指定 recipe 的固定搜索

记录：

- [logs/real-tests/swe-recipe-search-20260417/README.txt](/home/ubuntu/orbit/logs/real-tests/swe-recipe-search-20260417/README.txt:1)

固定 recipe：

- 24 个 localization short rollout
- 保留 4 个 localization state
- 每个 state 2 个 patch plan
- realize top 4
- 1 次 rubric
- 最多 2 次 repair

结果：

- `mini-rubocop`: `0` success
- `codex-rubocop`: `0` success

当时的直观结论：

- 这套 recipe 依然不工作

但这个结论后来被证明不完全可靠，因为 collector 里当时还存在真实 bug。

### 7. Python 任务验证：首次出现更强信号

记录：

- [logs/real-tests/swe-python-recipe-20260417/README.txt](/home/ubuntu/orbit/logs/real-tests/swe-python-recipe-20260417/README.txt:1)

候选任务：

- `geopy__geopy-388`
- `pre-commit__pre-commit-1299`
- `vega__altair-1958`（排除，baseline 坏）

结果：

- `mini-geopy`: `0` success，`0` near-miss
- `codex-geopy`: `0` success，但有 `1` near-miss 和 `1` repair
- `pre-commit`:
  - Mini 卡在 `503`
  - Codex 卡在 `504`

结论：

- `codex-geopy` 是第一条比较明确的“可能有希望”的真实 signal
- 同时 teacher endpoint 不稳定已经开始实质性影响实验解释

## 三、确认过的 collector / environment 问题

### 1. 已确认的 collector 问题

#### 问题 A：MiniSWE bash 提取过于严格

表现：

- 很多 real response 明明已经输出了 bash 开头
- 但因为没有闭合 fence，被当成空命令
- 结果记录成 `0-step no_patch`

证据：

- [logs/real-tests/swe-logic-fix-20260417/README.txt](/home/ubuntu/orbit/logs/real-tests/swe-logic-fix-20260417/README.txt:7)

修复：

- bash 提取支持未闭合 trailing fence

#### 问题 B：Codex 只认结构化 `tool_calls`

表现：

- Chutes 有时返回的是 content-form `<tool_call>{...}</tool_call>`
- collector 之前直接忽略
- 导致本来应该执行的 shell 动作被丢掉

证据：

- [logs/real-tests/swe-logic-fix-20260417/README.txt](/home/ubuntu/orbit/logs/real-tests/swe-logic-fix-20260417/README.txt:14)

修复：

- 增加对文本 `<tool_call>` 的 fallback 解析

#### 问题 C：realization 响应预算太小

表现：

- `max_tokens=320` 下，realization 很容易被截断
- 尤其是在长 here-doc 或整文件 rewrite 时

修复：

- 提高 realization response budget
- 同时收紧 prompt，避免 giant one-shot whole-file rewrite

#### 问题 D：manifest 统计失真

表现：

- `run.json` 里原先写的是 shortlist 后数量
- 不是实际生成的 localization / plan 数

后果：

- 很难正确比较 recipe 预算
- 容易误判 collector 实际做了多少搜索

修复：

- `localization_candidates` / `patch_plan_candidates` 记录真实生成总数

#### 问题 E：submit 后重复 verify

表现：

- submit 时测一次
- sample 尾部又无条件再测一次

后果：

- 浪费测试预算
- terminal output 可能被第二次测试覆盖

修复：

- 只在从未 verify 过且有 patch 时补跑 terminal verify

### 2. 已确认的环境问题

#### 问题 F：teacher endpoint 不稳定

表现：

- 多次出现 `503` / `504`
- 外部轻量 health check 也会失败

影响：

- rubric / relabel 都可能被外部波动污染

修复：

- 增加 retry/backoff
- `sample` 增加 teacher probe
- teacher 不可用时自动降级为 `no-rubric sampling`
- `relabel` 也做 teacher probe，并在不可用时 graceful degrade

#### 问题 G：本地 Docker 根盘耗尽

表现：

- 一度只剩 `2.7G` 可用，`100%` 使用率

影响：

- 拉镜像不稳定
- workspace create / temp write 可能失败
- 会污染对 collector 行为的判断

修复：

- 清理非白名单临时容器
- prune 无用镜像
- 恢复到 `117G` 可用

证据：

- [logs/real-tests/swe-cleanup-and-fix-20260417/README.txt](/home/ubuntu/orbit/logs/real-tests/swe-cleanup-and-fix-20260417/README.txt:1)

## 四、当前最关键的研究结论

### 1. “完全 0 成功”不能再简单归咎于模型

在 `swe-logic-fix` 之前，确实存在 collector 真实 bug，会把本来已经开始动作的轨迹错误地落成 `0-step no_patch`。  
所以早期一些 “这个模型完全不会做” 的结论不可信。

### 2. 修完 collector 后，失败开始变得“可信”

修复后的 representative rerun，已经出现：

- 真实 state files
- 真实 changed files
- 真实 `verify_fail`
- 真实 `repair_records`

尤其是：

- `mini-geopy-v2`
  - `verify_fail=2`
  - `changed_files=2`
  - `repair_records=2`
- `codex-rubocop-v2`
  - `verify_fail=2`
  - `changed_files=2`
  - `no_patch:truncated_action=1`

这说明当前失败大多已经是：

- 模型只 inspect 不 edit
- edit 方向对但 patch 质量差
- 命令太长再次截断

而不是 collector 偷偷吞轨迹。

### 3. 当前 student 的主要问题不是“完全不会定位”，而是“落 patch 质量不足”

证据：

- `mini-rubocop` 多次改到正确文件邻域
- `codex-geopy` 定位到正确文件，并出现 near-miss
- `mini-geopy-v2` / `codex-rubocop-v2` 都能落到真实 changed-files verify-fail

说明：

- localization 并不是完全失效
- patch realization 质量与动作风格更可能是主瓶颈

### 4. 小步数预算下，prompt 极易把模型推向两个极端

观察到的两个极端：

- 过于激进：直接 giant one-shot rewrite，容易截断或写坏语法
- 过于保守：三步都在 `sed -n` / `cat` / `ls` inspection，最后 `max_steps`

这也是为什么后来要补 budget-aware realization nudge。

## 五、当前系统的“最好结果”

如果问“截至目前最有价值的实验结果是什么”，答案是：

### 1. `codex-geopy`

记录：

- [logs/real-tests/swe-python-recipe-20260417/README.txt](/home/ubuntu/orbit/logs/real-tests/swe-python-recipe-20260417/README.txt:1)

价值：

- 真实 Python 任务
- baseline 健康
- 出现 `near_miss + repair + B/C`

意义：

- 说明这条路径不只是“错误得一塌糊涂”
- 至少能把 student 推到一个 teacher critique 有意义的状态

### 2. `mini-geopy-v2`

记录：

- [logs/real-tests/swe-cleanup-and-fix-20260417/README.txt](/home/ubuntu/orbit/logs/real-tests/swe-cleanup-and-fix-20260417/README.txt:1)

价值：

- `verify_fail=2`
- `changed_files=2`
- `repair_records=2`
- `B/C` 桶真实非空

意义：

- 说明在当前 collector 修复后，MiniSWE 分支已经具备真实 failure-to-repair 的研究价值

## 六、目前还存在的核心问题

### 1. 仍然没有 verified-correct trajectory

这是最核心的事实。

无论五阶段、cascade、固定 recipe、Python 任务、logic fix 还是 cleanup+fix，**到现在还没有真正采到 `A` 桶成功轨迹**。

### 2. teacher availability 仍然是外部扰动源

虽然现在有 probe 和 degrade，但它仍然会影响：

- rubric 是否启用
- relabel 是否产生 repair
- 实验之间的可比性

### 3. 长命令截断问题还没有彻底消失

即使 Mini/Codex 的主解析 bug 已修，仍然会出现：

- 超长 `<tool_call>` 文本未闭合
- 超长 python here-doc 修改命令

这会在真实任务中继续制造：

- `no_patch:truncated_action`
- 语法错误型 `verify_fail`

### 4. `max_steps=3` 的 recipe 可能本身太苛刻

这套 recipe 的价值在于成本低、可快速比较，但它天然会放大两种坏行为：

- inspection-only
- giant edit gamble

如果后续研究目标是“提高 success rate”，不能只靠继续固定 `max_steps=3`。

## 七、对后续研究的建议

### A. 不要再重复做的事情

- 不要在未验证 collector/runtime 健康的前提下直接解释 student 失败
- 不要再把“公开 benchmark 30+”直接等同于“当前 collector 下也应立即采到成功”
- 不要继续把远端 rental SSH 路径当成主要收集验证面
- 不要再把 `max_steps=3` 下的 inspection-only 结果直接当作“模型完全没能力”

### B. 最值得继续研究的方向

#### 方向 1：realization action-space 约束

目标：

- 减少 giant one-shot rewrite
- 提升可执行 patch 的局部性和语法稳定性

建议：

- 强制优先使用小范围 `python - <<'PY'` / `sed -i` 局部 patch
- 加入 action template，而不是只靠自然语言约束
- 对超长命令提前拒绝或切分

#### 方向 2：budget-aware stage policy

目标：

- 让短 budget 下的行为更稳定

建议：

- 对 `max_steps<=3` 使用专门 realization prompt
- 第一步允许 inspect
- 第二步必须 edit
- 第三步必须 verify/submit 或最后一次 revision

#### 方向 3：task selection for research

目标：

- 先在“健康 baseline + 已出现 near-miss”的题目上验证方法，而不是随机扩散

当前推荐研究任务：

- `geopy__geopy-388`
- `rubocop__rubocop-7660`

不推荐当前继续投入：

- `pre-commit__pre-commit-1299`
  - 因为 teacher instability 曾直接把整轮卡死
- baseline 自身不健康的任务

#### 方向 4：teacher 作用形式继续收缩

当前观察支持：

- teacher 更适合做 rubric 和 near-miss repair
- 不适合频繁 takeover

后续建议：

- 继续减少 teacher 在 sample 主路径中的同步依赖
- 把 teacher 进一步限制为：
  - rubric constructor
  - repair annotator
  - candidate reranker / verifier

#### 方向 5：把 research 目标从 “直接采到 success” 分成两层

建议分层指标：

1. 真实性指标
   - 非 fake `0-step no_patch`
   - 有 state files
   - 有 changed files
   - 有真实 `verify_fail`

2. 成功性指标
   - near-miss
   - repair records
   - `B/C` 桶质量
   - verified success

当前系统在第一层已经基本站稳，在第二层还弱。

## 八、建议的下一轮实验矩阵

### 实验组 1：只改 realization prompt / action policy

保持不变：

- student model
- task
- localization recipe

只改：

- realization prompt
- max_steps-specific nudge
- command length constraint

首选任务：

- `geopy__geopy-388`
- `rubocop__rubocop-7660`

### 实验组 2：只改 `max_steps`

对照：

- `max_steps=3`
- `max_steps=5`
- `max_steps=6`

目标：

- 判断当前瓶颈是不是“预算太低导致 inspect/edit/verify 三者无法兼容”

### 实验组 3：固定 collector，替换更强 student

前提：

- 不再改 collector 主逻辑
- 只换 student model

目标：

- 让模型因素和 collector 因素彻底解耦

### 实验组 4：teacher offline-only ablation

比较：

- full rubric + relabel
- no-rubric + relabel only
- rubric only + no relabel

目标：

- 定量看 teacher 在当前 pipeline 中到底带来多少边际收益

## 九、当前最重要的结论

一句话总结：

**SWE 收集系统现在已经从“collector 本身不可信”走到了“collector 基本可信，但 student 仍然采不到成功轨迹”的阶段。**

更具体地说：

- 早期 0 成功里确实混杂了 collector bug
- 这些 bug 已经被定位并修掉了大部分关键部分
- 现在的失败样本更能反映真实模型行为
- 当前最值得研究的不是继续怀疑 collector，而是：
  - realization action-space
  - budget-aware prompting
  - stronger student
  - teacher offline role设计

## 十、索引

关键研究记录：

- [logs/real-tests/swe-five-stage-smoke-20260417/README.txt](/home/ubuntu/orbit/logs/real-tests/swe-five-stage-smoke-20260417/README.txt:1)
- [logs/real-tests/swe-cascade-smoke-20260417/README.txt](/home/ubuntu/orbit/logs/real-tests/swe-cascade-smoke-20260417/README.txt:1)
- [logs/real-tests/swe-scale-search-20260417/README.txt](/home/ubuntu/orbit/logs/real-tests/swe-scale-search-20260417/README.txt:1)
- [logs/real-tests/swe-hippo-search-20260417/README.txt](/home/ubuntu/orbit/logs/real-tests/swe-hippo-search-20260417/README.txt:1)
- [logs/real-tests/swe-recipe-search-20260417/README.txt](/home/ubuntu/orbit/logs/real-tests/swe-recipe-search-20260417/README.txt:1)
- [logs/real-tests/swe-python-recipe-20260417/README.txt](/home/ubuntu/orbit/logs/real-tests/swe-python-recipe-20260417/README.txt:1)
- [logs/real-tests/swe-logic-fix-20260417/README.txt](/home/ubuntu/orbit/logs/real-tests/swe-logic-fix-20260417/README.txt:1)
- [logs/real-tests/swe-cleanup-and-fix-20260417/README.txt](/home/ubuntu/orbit/logs/real-tests/swe-cleanup-and-fix-20260417/README.txt:1)
- [logs/real-tests/SMOKE_LEDGER.md](/home/ubuntu/orbit/logs/real-tests/SMOKE_LEDGER.md:364)
