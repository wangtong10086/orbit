# Multi-Agent Collaboration Design — Affine Forge

> Version: 1.0
> Date: 2026-03-17
> Status: Design complete — 5 rounds self-attack

---

## 1. Core Philosophy

像 autoresearch 一样：多个人/多个 Claude loop 同时探索，**共享实验结果、失败经验、环境知识和探索发现**。没有角色隔离——任何人可以做任何事（训练、数据、代码、评估）。冲突由 AI 自行 rebase 解决。

### 与 Autoresearch 的类比

| Autoresearch | Affine Forge |
|-------------|-------------|
| `train.py` (唯一可修改文件) | `forge/` + `scripts/` + `canonical/` (整个代码库) |
| `val_bpb` (唯一指标) | Leaderboard geometric mean (6 环境) |
| `results.tsv` (实验记录) | `experiments/*.yaml` (结构化实验记录) |
| `program.md` (人类指令) | `PLAYBOOK.md` (共享策略文档) |
| `git reset HEAD~1` (回退失败) | 保留所有提交，标记实验为 failed/succeeded |
| Ensue shared memory (知识共享) | `knowledge/` 目录 (git 提交的知识库) |
| `claims/` (重复避免) | `experiments/*.yaml` status=running (避免重复) |

### 核心差异

Autoresearch 改一个文件、一个指标、5 分钟实验。我们的项目：
- 多文件修改（代码 + 数据 + 配置）
- 多个指标（6 个环境的 geometric mean）
- 实验周期长（训练 3-9 小时，$8-$55/次）
- 代码是共享可变状态（不是单文件）

所以我们不能完全照搬 autoresearch 的单文件 ratchet。我们需要：**实验记录作为协调层，代码库作为共享可变状态，知识库作为集体记忆。**

---

## 2. 架构

```
affine-forge/
  PLAYBOOK.md                    # 共享策略（等同于 program.md）
  STATUS.md                      # 当前状态快照（谁在做什么）

  experiments/                   # 实验记录（核心协调机制）
    results.tsv                  # 汇总表（快速扫描）
    v11-sft-navworld-boost.yaml  # 每个实验一个文件
    v12-dpo-game-focus.yaml
    ...

  knowledge/                     # 集体知识库
    environments/                # 每个评估环境的知识
      GAME.md
      NAVWORLD.md
      SWE-SYNTH.md
      LIVEWEB.md
      LGC-v2.md
      PRINT.md
    infra.md                     # 基础设施经验（Targon、rental、sglang）
    training.md                  # 训练经验（超参、数据配比、loss 曲线规律）
    data.md                      # 数据经验（格式、清洗、distillation）
    failures.md                  # 失败博物馆（昂贵的教训）

  forge/                         # 代码（任何人可改）
  scripts/                       # 脚本（任何人可改）
  canonical/                     # 训练数据（任何人可改）
  logs/iteration_log.md          # 历史记录（保留但不再是主要协调工具）
```

### 哪些文件 committed，哪些 ignored

| 路径 | Git 状态 | 原因 |
|------|----------|------|
| `experiments/` | **committed** | 核心协调层，所有人必须看到 |
| `knowledge/` | **committed** | 集体知识，跨会话持久化 |
| `PLAYBOOK.md` | **committed** | 共享策略 |
| `STATUS.md` | **committed** | 当前状态 |
| `forge/`, `scripts/` | **committed** | 代码 |
| `.evomesh/` | **ignored** | 运行时状态，不需要共享 |
| `data/` | **ignored** | 大文件，通过 HF 共享 |
| `.env`, `.claude/` | **ignored** | 密钥 |

---

## 3. 实验记录系统（核心）

### 3.1 results.tsv — 快速扫描

类似 autoresearch 的 `results.tsv`，append-only：

```tsv
version	date	author	status	data_count	lr	lora_r	epochs	loss	GAME	NAVWORLD	SWE-SYNTH	LIVEWEB	LGC-v2	PRINT	geo_mean	cost_usd	notes
v5	2026-03-14	user1	completed	8263	1e-4	128	1	0.23	16.0	0.0	—	—	—	—	—	9	NAVWORLD format wrong
v6	2026-03-14	user1	completed	6229	5e-5	64	1	0.22	9.0	0.0	—	—	—	—	—	9	lr too low
v7	2026-03-14	user1	completed	4809	1e-4	64	1	0.18	14.5	0.0	—	—	—	—	—	7	parse error 29→12%
v8	2026-03-14	user1	completed	7002	1e-4	64	1	0.11	9.0	8.7	—	—	—	—	—	11	NAVWORLD first breakthrough
v9	2026-03-15	user1	completed	13282	1e-4	64	1	0.14	20.1	5.2	—	—	—	—	—	14	+LGC-v2/PRINT back
v10	2026-03-16	user1	completed	13733	1e-4	64	1	0.19	22.0	5.1	—	—	—	—	—	14	+MemoryGym 500
v11	2026-03-17	user1	running	15273	1e-4	64	1	—	—	—	—	—	—	—	—	—	+NAVWORLD 2154
```

**规则**：
- 任何人都可以 append 新行
- 永远不修改已有行（append-only）
- `—` 表示未评估
- `status`: `planned` → `running` → `completed` / `failed` / `abandoned`
- `author`: 标识谁发起的实验

### 3.2 实验详情文件

`experiments/{version}-{short-description}.yaml`

```yaml
version: v12
title: "DPO on v11 checkpoint, GAME+NAVWORLD focus"
author: user2
status: running          # planned | running | completed | failed | abandoned
created: 2026-03-17T12:00:00Z
completed: null

# 实验假说
hypothesis: |
  v11 SFT loss已收敛到0.14，继续SFT边际收益递减。
  DPO可以利用DDB中同一task_id的好/坏样本对进行偏好对齐，
  预期GAME和NAVWORLD分数提升5-10%。

# 训练配置
config:
  base_model: Qwen/Qwen3-32B
  method: DPO
  sft_checkpoint: YOUR_HF_USER/affine-qwen3-32b-v11
  data: mixed_dpo.jsonl (2688 pairs)
  lr: 5e-6
  lora_r: 64
  epochs: 1
  max_seq_len: 4096

# 基础设施
infra:
  gpu: 4×H200 (rental rentals-w58tlzhv9xyh3dis)
  container: null
  hf_repo: YOUR_HF_USER/affine-qwen3-32b-v12-dpo
  estimated_cost_usd: 15
  estimated_hours: 4

# 训练过程
progress:
  - step: 0
    loss: null
    note: "training starting"

# 评估结果
eval:
  GAME: null
  NAVWORLD: null
  SWE-SYNTH: null
  LIVEWEB: null
  LGC-v2: null
  PRINT: null

# 结论（实验完成后填写）
conclusion: null

# 学到了什么（关键！必填！）
learnings: null
  # 成功了什么，失败了什么，为什么，下次怎么做
  # 这些会被提取到 knowledge/ 中
```

### 3.3 实验生命周期

```
planned ──→ running ──→ completed ──→ learnings 提取到 knowledge/
                  │
                  ├──→ failed ──→ learnings 提取到 knowledge/failures.md
                  │
                  └──→ abandoned (资源问题/被更高优先级打断)
```

**关键规则**：
1. **开始前查重**：读 `experiments/` 中所有 `status: running` 和 `status: planned` 的文件，确认没有人在做同样的事
2. **开始时创建文件**：commit + push 实验 YAML（status: running），让其他人看到
3. **过程中更新进度**：定期更新 progress 和 loss
4. **完成后必须写 learnings**：这是对集体知识的贡献义务
5. **learnings 提取到 knowledge/**：手动或自动把关键发现写入对应的知识文件

### 3.4 重复避免

不需要复杂的 claim 系统。简单规则：

1. `git pull` 拿最新
2. 读所有 `experiments/*.yaml`，特别是 `status: running` 和 `status: planned`
3. 如果有人已经在做类似实验 → 不做，换个方向
4. 如果不确定是否重复 → 在 STATUS.md 里写一行 "我打算做 X"，push，等一个 loop 周期看有没有人反对
5. 如果发现做了重复实验 → 不是灾难，对比两个结果本身也有价值

**与 autoresearch 的区别**：autoresearch 用 semantic similarity + 15min TTL claim。我们用文件 + 人类判断，因为实验周期长（小时级不是分钟级），错误成本高（$10-50 不是 $0），值得花 10 秒看一下有没有重复。

---

## 4. 知识库系统

### 4.1 设计原则

autoresearch-at-home 的 `insights/` namespace 要求每次实验后 **强制发布 insight**。我们采用同样的强制性，但存储在 git 文件中。

**知识 ≠ 实验记录**。知识是从多个实验中**蒸馏**出来的规律：
- 实验记录："v7 lr=1e-4, loss=0.18, GAME=14.5"
- 知识："lr=1e-4 是 QLoRA 的最优学习率，5e-5 太低（v6 证明），2e-5 也太低（v1-v4 证明）"

### 4.2 环境知识文件

`knowledge/environments/GAME.md` 示例：

```markdown
# GAME 环境知识

## 评估机制
- 来源: affinetes/game/ (read-only reference)
- 22种游戏，模型 vs 随机/规则对手
- 输出: 纯数字 (action ID)，strip_think_tags=True
- 2次重试机制: 第一次错还有机会
- 计分: 胜率 × 游戏难度权重

## 数据要点
- DDB数据: 系统提示说"只输出数字"，assistant确实是纯数字
- CoT数据: 系统提示说"用think块"，assistant有<think>推理+数字
- **教训 (v5-v7)**: 混合两种系统提示→模型不知道用哪种格式→29%解析错误
- **解决方案 (v7)**: 统一系统提示为CoT版本，eval会自动strip think tags
- Bot策略数据 (v8+): 7种游戏1687条，程序化策略生成
- **教训 (v8)**: gin_rummy从0%→100%胜率，证明bot策略数据有效

## 已知不可学习的游戏
- chess, go, checkers: 需要深度搜索，LLM无法通过SFT学会
- 不要浪费数据在这些游戏上

## 当前最佳
- v10: GAME eval mean=0.220 (41% non-zero), 99 samples
- Leaderboard #1 ~48 points

## 改进方向
- 更多游戏的bot策略数据 (othello, hex, liars_dice 仍是0%)
- 考虑过滤掉不可学习游戏的训练数据避免噪声
```

### 4.3 失败博物馆

`knowledge/failures.md` — 最有价值的知识往往来自失败：

```markdown
# 失败博物馆

每条记录: **花了多少钱** + **学到了什么** + **怎么避免**

---

## Targon网络崩溃 ($25, 2026-03-12)
15个容器尝试，全部因网络不可达失败。
**原因**: Targon serverless 容器出口网络间歇性断开。
**规避**: 使用 wheel bundle 预装依赖 + pytorch 官方镜像。
**相关实验**: v4 attempt 1-3

## HF上传回调静默失败 ($60, 2026-03-11-12)
3次训练 (GAME-only, Mixed v1, v2) 在step 200-300后HF上传全部停止。
**原因**: HfApi在长时间训练中连接池损坏。
**解决**: subprocess隔离上传 (fork独立进程)。
**规避**: 永远不在训练进程内直接调用HfApi，用subprocess。

## 从Top模型微调失败 ($3, 2026-03-11)
QLoRA在 voidai001/affine-new 上训练，loss震荡不收敛。
**原因**: 目标模型已被深度调优，QLoRA无法稳定学习。
**规避**: 永远从base Qwen3-32B开始训练，不要从其他人的模型微调。

## NAVWORLD数据格式错误 ($14, v5-v7)
3个版本NAVWORLD eval全是0分。
**原因**: 训练数据用文本格式 "Call tool: xxx" 而非标准 <tool_call> 格式。
**解决**: apply_chat_template(messages, tools=tools) 生成原生格式。
**叠加问题**: sglang需要 --tool-call-parser qwen25 参数。
```

### 4.4 知识更新规则

1. **实验完成后必须更新知识**：从 experiment YAML 的 `learnings` 提取到对应的 `knowledge/` 文件
2. **知识文件是结构化的**：每个文件有固定 sections（评估机制、数据要点、已知问题、当前最佳、改进方向）
3. **追加不覆盖**：新发现追加到已有 section，不删除旧内容（除非旧内容已被证伪）
4. **引用实验版本**：每条知识标注来源实验（"(v8证明)"），方便追溯
5. **任何人都可以更新**：不需要"知识管理员"角色

---

## 5. PLAYBOOK.md — 共享策略

等同于 autoresearch 的 `program.md`。所有 loop 启动时首先读这个文件。

```markdown
# Affine Forge Playbook

## 目标
Affine Leaderboard (Bittensor Subnet 120) #1。
Geometric mean across 6 environments。最弱环境决定总分。

## 当前状态
- 排名: #3 (2026-03-17)
- 模型: Qwen3-32B QLoRA SFT
- 最弱环境: NAVWORLD (5.1), LIVEWEB (未评估)
- 最强环境: GAME (22.0), LGC-v2/PRINT (未在leaderboard但SFT覆盖)

## 优先级 (按ROI排序)
1. NAVWORLD数据质量+数量 (当前最大瓶颈)
2. 评估流程自动化 (每次训练完手动eval太慢)
3. DPO/RL 探索 (SFT可能已触顶)
4. LIVEWEB 数据获取 (框架变更后需要新方案)
5. SWE-SYNTH 数据增强

## 禁止事项
- 不要部署模型到 Chutes 或提交 on-chain（需要人类批准）
- HF repo 必须 private
- 不要从别人的微调模型开始训练（从base Qwen3-32B开始）
- 不要在不可学习的游戏上浪费数据（chess/go/checkers）

## 每个 loop 必须做的事
1. git pull --rebase（拿最新代码和知识）
2. 读 PLAYBOOK.md + STATUS.md + experiments/ 中 status=running 的文件
3. 读相关的 knowledge/ 文件（根据你要做的事）
4. 检查有没有人在做同样的事（查重）
5. 做你的工作
6. 更新 STATUS.md（你在做什么）
7. 如果完成了实验：更新 experiment YAML + results.tsv + knowledge/
8. git add → commit → git pull --rebase → 解决冲突 → push
```

---

## 6. STATUS.md — 实时状态

```markdown
# 当前状态

## 活跃工作
| 谁 | 在做什么 | 开始时间 | 预计完成 |
|------|----------|----------|----------|
| user1/loop-trainer | v11 SFT 训练 | 03-17 10:00 | 03-17 16:00 |
| user1/loop-data | NAVWORLD distillation batch 3 | 03-17 11:00 | 03-17 12:00 |
| user2/loop-1 | forge CLI重构 | 03-17 10:30 | 03-17 11:30 |

## GPU资源
| Rental | 状态 | 用途 |
|--------|------|------|
| rentals-w58tlzhv9xyh3dis | active | v11 training + sglang |

## Leaderboard
最后检查: 2026-03-17 10:00 UTC
#1: UID 45 (Infinite3214), weight 0.508
我们: #3, NAVWORLD 5.1 是瓶颈

## 阻塞
- (无)
```

**规则**：
- 开始工作时写一行到"活跃工作"
- 完成工作时删除那一行
- 冲突解决：两个人同时编辑 → rebase 时保留双方的行（都是追加）
- 不需要精确——这是"大致知道谁在做什么"，不是严格锁

---

## 7. Git 协作机制

### 7.1 无分支策略

所有人工作在 `main` 分支。原因：
- 实验记录/知识需要实时可见
- 短周期提交 + rebase 比长期 feature branch 更适合 AI 协作
- autoresearch 也是单分支

### 7.2 提交 + Push 流程

```
1. git add <你改的文件>
2. git commit -m "{type}: {description}"
3. git pull --rebase
4. 如果冲突:
   a. 大多数冲突是 STATUS.md / results.tsv 的并发追加 → 保留双方内容
   b. 代码冲突 → AI 阅读两边改动，理解意图，手动合并
   c. 合并后验证: python3 -c "import ast; ast.parse(open('file.py').read())"
   d. 最多重试 3 次，如果无法解决 → 放弃本次提交，下个 loop 再试
5. git push
6. 如果 push 被拒绝 → 回到 3（最多 5 次）
```

### 7.3 冲突预期

| 文件类型 | 冲突概率 | 解决方式 |
|----------|----------|----------|
| `experiments/*.yaml` | 极低（每个实验独立文件） | N/A |
| `results.tsv` | 低（append-only，但可能同时追加） | 保留双方行 |
| `STATUS.md` | 中（多人更新状态） | 保留双方行 |
| `knowledge/*.md` | 低（不同 section 追加） | 保留双方追加 |
| `PLAYBOOK.md` | 极低（很少修改） | 人类决策 |
| `forge/*.py` | 中（多人改代码） | AI 阅读理解后合并 |

### 7.4 减少冲突的实践

1. **小提交、频繁 push**：改完一个逻辑单元就提交，不要积攒大 diff
2. **实验文件独立**：每个实验有自己的 YAML，不会冲突
3. **知识文件按 section 追加**：不同人写不同 section，冲突少
4. **代码改动前先 pull**：开始写代码前确认没人在改同一个文件
5. **STATUS.md 声明意图**：写 "我要改 forge/cli.py"，其他人看到后会避开

---

## 8. 知识如何在会话间持久化

autoresearch 的问题：LLM 没有跨会话记忆，靠读 `train.py` + `results.tsv` + `git log` 重建上下文。

我们的解决方案：**知识库文件就是持久记忆**。

### 新 loop 启动时读什么

| 顺序 | 文件 | 目的 | 大小预估 |
|------|------|------|----------|
| 1 | `PLAYBOOK.md` | 目标 + 优先级 + 禁止事项 | ~100 行 |
| 2 | `STATUS.md` | 谁在做什么 | ~30 行 |
| 3 | `experiments/results.tsv` | 所有实验概览 | ~50 行 |
| 4 | 最新 2-3 个 `experiments/*.yaml` | 最近实验详情 | ~100 行/个 |
| 5 | 相关 `knowledge/*.md` | 做决策需要的知识 | 按需读取 |

**总共约 500 行**，远小于 Claude 上下文窗口。一个全新的 loop 可以在 1 分钟内获得完整项目上下文。

### 知识 vs 代码 vs 实验

```
知识 (knowledge/)     = 蒸馏后的规律，跨会话持久
实验 (experiments/)   = 结构化记录，什么时候做了什么
代码 (forge/)         = 当前最优实现，可以直接读
iteration_log.md      = 历史叙事（保留但不再是主要信息源）
```

---

## 9. 自我攻击

### Attack 1: results.tsv 并发追加冲突

两人同时 append → git 冲突（同一位置插入不同内容）。

**缓解**: TSV 是最简单的追加格式。rebase 冲突时，AI 保留双方行即可。最坏情况：丢失一行记录，下个 loop 重新追加。这不是关键路径——实验 YAML 文件才是权威记录。

### Attack 2: STATUS.md 变成垃圾场

每个 loop 都写 STATUS.md → 频繁冲突 + 过时信息堆积。

**缓解**:
- STATUS.md 结构固定（活跃工作表 + GPU表 + Leaderboard + 阻塞）
- Loop 结束时清理自己的行
- 过时信息（>2h 未更新的活跃工作）由任何 loop 清理
- 如果冲突太频繁 → 降级为"只在开始重要工作时更新"

### Attack 3: knowledge/ 文件无限增长

每次实验追加知识 → 文件越来越长 → 占满上下文窗口。

**缓解**:
- 每个 knowledge 文件设 **300 行上限**
- 超过时，蒸馏压缩：删除过时信息，合并重复内容
- 失败博物馆按时间衰减：>30天的失败记录移到 `knowledge/archive/`
- 按需读取：只读与当前任务相关的 knowledge 文件

### Attack 4: 实验 YAML 文件爆炸

每个实验一个文件 → 50个实验 → 50个文件。

**缓解**:
- 活跃文件（status=running/planned）才需要关注
- 完成的实验 → 定期移到 `experiments/archive/`
- results.tsv 是汇总，不需要读每个 YAML

### Attack 5: 没有强制力——人/AI 可能不遵守规则

PLAYBOOK.md 说"必须写 learnings"，但 AI 可能忘记。

**缓解**:
- CLAUDE.md 中写入硬规则：实验完成后必须更新 experiment YAML + knowledge
- 这是 convention enforcement，和 autoresearch 的 program.md 一样
- 如果 AI 不遵守 → 下个 loop 的人/AI 发现缺失 learnings → 补上
- 不需要完美——90% 遵守就足以积累有用知识

### Attack 6: 长训练期间没有进度可见性

训练 5 小时，中间没有任何更新 → 其他人不知道进度。

**缓解**:
- 训练 loop 应该每个 loop 周期（10 分钟）更新实验 YAML 的 progress 字段
- 如果是非 loop 场景（人类手动训练）→ HF repo 的 checkpoint 就是进度
- 其他人可以直接查 HF repo 而不依赖 STATUS.md

### Attack 7: 代码冲突 AI 解决不了

两个人同时大幅重构同一个文件 → 复杂冲突。

**缓解**:
- 这在实践中很少发生（当前团队小，大多数时间在做不同的事）
- 如果发生 → AI 放弃 rebase，保留本地更改不 push，等下个 loop
- 最坏情况 → 手动解决（人类介入）
- STATUS.md 声明"我在改 forge/cli.py" 可以预防大部分情况

### Attack 8: 没有 ratchet 机制——怎么防止模型退步

autoresearch 的 ratchet：只保留改进。我们呢？

**缓解**:
- 我们的 ratchet 是 **leaderboard 分数**
- 每个新版本必须在本地 eval 后才能部署
- 如果 eval 显示退步 → 不部署，标记实验为 failed
- HF 上保留所有版本（v5-v11），随时可以回退
- Leaderboard 上当前部署的模型就是 "current best"
- 这比 autoresearch 的 git reset 更安全（我们从不删除旧模型）

### Attack 9: 新人 onboarding 成本

新人加入需要理解项目全貌。

**缓解**:
- 读 `PLAYBOOK.md` (5 分钟) → 知道目标和优先级
- 读 `results.tsv` (2 分钟) → 知道所有实验历史
- 读 `knowledge/` 相关文件 (10 分钟) → 知道关键知识
- 比读 1600 行 iteration_log.md 高效 10 倍

### Attack 10: knowledge/ 和 experiments/ 信息重复

实验 YAML 有 learnings，knowledge/ 也有同样的信息。

**缓解**:
- 这是 **有意的冗余**
- experiment YAML: 绑定到具体实验的原始记录（"v8发现apply_chat_template有效"）
- knowledge/: 蒸馏后的通用规律（"NAVWORLD训练数据必须用apply_chat_template"）
- 前者是证据，后者是结论。两者都有价值。

---

## 10. 从当前状态迁移

### 需要创建的文件

1. `experiments/` 目录 + `results.tsv`（从 iteration_log.md 提取 v5-v11 记录）
2. `knowledge/` 目录结构（从 iteration_log.md 蒸馏知识）
3. `PLAYBOOK.md`（从 CLAUDE.md 项目规则 + iteration_log.md 策略分析提取）
4. `STATUS.md`（当前状态快照）

### 需要修改的文件

1. `CLAUDE.md`：更新 loop 流程，加入读 PLAYBOOK/STATUS/experiments/knowledge 的步骤

### 不需要改变的

- 代码结构 (`forge/`, `scripts/`)
- 数据流 (DDB → extract → HF → train → eval)
- Git 工作流基础 (commit → pull --rebase → push)
- `.evomesh/` 可以保留作为本地运行时，但不再是协调机制

### 迁移步骤

1. 创建目录结构
2. 从 iteration_log.md 提取 results.tsv（v5-v11 数据）
3. 从 iteration_log.md 蒸馏 knowledge/ 文件（环境知识 + 训练知识 + 失败博物馆）
4. 写 PLAYBOOK.md
5. 写 STATUS.md
6. 更新 CLAUDE.md loop 流程
7. 提交 + 推送

---

## 11. 总结

| 维度 | 方案 |
|------|------|
| 协调机制 | 实验文件 (experiments/*.yaml) + STATUS.md |
| 知识共享 | knowledge/ 目录（蒸馏后的规律） |
| 重复避免 | 查看 experiments/ status=running + STATUS.md |
| 冲突解决 | AI rebase（append-only 文件几乎不冲突） |
| 角色分工 | 无固定角色，任何人做任何事 |
| 持久记忆 | knowledge/ + experiments/results.tsv (committed to git) |
| Ratchet | Leaderboard 分数 + HF 保留所有版本 |
| 人类控制 | PLAYBOOK.md（优先级 + 禁止事项） |
| 新人上手 | PLAYBOOK + results.tsv + knowledge/ (~20 分钟) |
