# SWE 合成数据 Pipeline（中文算法版）

这是一份**独立的中文文档**，用于解释当前 ORBIT 中 **SWE 合成数据**
pipeline 的实际工作方式。

这份文档的重点不是重新翻译英文版，而是把当前实现中的：

- 状态变量
- 决策逻辑
- prompt 生成逻辑
- student / teacher 切换逻辑
- checkpoint / restore / retry 逻辑
- 常见失败模式

讲清楚，帮助理解当前系统究竟是如何“跑起来”的，以及为什么会生成
某些错误轨迹。

## 文档范围

本文只描述当前 active 路径：

```bash
python3 -m orbit data swe-collect synthesize
```

不描述：

- `evaluate` 模式下的纯黑盒跑分
- 历史本地 staged-search / bucket collector
- RL、训练、评测等其他子系统

## 一句话概括

当前 SWE synth pipeline 是一个**运行在 ORBIT 中的薄控制器**：

- 上游 `affinetes` 提供真实 `SWE-INFINITE` 环境与 OpenEnv 接口
- ORBIT 维护 episode、checkpoint、restore、retry 和日志
- student 始终沿 upstream `affinetes` 主线 prompt 形状生成**下一条 shell action**
- teacher 不再直接生成 action，而只通过两种方式干预：
  - `restore_target`：决定是否从 `CURRENT / BASELINE / ROLLBACK_1..4 / STOP` 继续
  - `teacher_think`：生成一段隐藏引导文本，注入到下一次 student 调用前
- 最终所有事件都落盘成 raw event log 和一个小 manifest

## 总体边界

### ORBIT 负责什么

- CLI 参数解析
- 解析并准备 upstream `affinetes` checkout
- 启动 OpenEnv bridge
- 调 student / teacher 模型
- 决定何时 checkpoint / restore / retry
- 记录 raw event 与最终 manifest

### upstream `affinetes` 负责什么

- `SWE-INFINITE` 环境本身
- `reset / state / checkpoint / restore / step / stop`
- task container 生命周期
- `/app` 工作区中的真实代码修改
- observation / reward / done / truncated 的定义

### student / teacher 负责什么

#### student

- 输入：当前 student message 列表
- 输出：**一条命令**
- 这个 message 列表的起点必须与 upstream `affinetes` 主线一致：
  - `system_template`
  - `instance_template`
- 后续只追加：
  - student 自己上一轮的 action
  - upstream `step()` 返回的 observation
  - 可选的一条隐藏 teacher-think 文本

#### teacher

- 不直接生成 shell action
- 只负责两种干预：
  - `restore_target`
  - `teacher_think`
- 不负责：
  - 任务环境状态管理
  - checkpoint / restore 的执行
  - artifact 写盘

## 环境颗粒度：ORBIT 看到的到底是什么

如果要定位问题，最重要的是把当前系统看成三层状态：

1. **controller 状态**
   - ORBIT 在 `run_openenv_synthesis(...)` 里维护的控制变量
2. **OpenEnv episode 状态**
   - upstream `SWE-INFINITE` 的 `EpisodeState`
3. **task container 工作区状态**
   - Docker 容器里 `/app` 的真实 git working tree

排障时，这三层不能混在一起。

### 三层状态的对应关系

```text
ORBIT controller state
  - baseline_checkpoint_id
  - edit_checkpoint_id
  - student_messages
  - no_progress_commands
  - preferred_runtime
  - root_retries_used / edit_retries_used
            |
            v
OpenEnv episode state
  - episode_id
  - container_id
  - messages
  - step_count
  - done / truncated
  - latest_observation
  - last_patch_hash
  - last_changed_files
  - checkpoints
            |
            v
Task container (/app)
  - repo files
  - current git diff
  - current staged diff
  - command side effects
```

## OpenEnv Bridge 是什么

ORBIT 并不是直接 import `SWE-INFINITE` 然后在本进程里跑 episode。

实际结构是：

- ORBIT 在 per-run runtime 里拉起一个本地 bridge 进程：
  - [openenv_server.py](../orbit/integrations/affinetes_swe/openenv_server.py)
- bridge 通过 Unix socket 暴露几个动作：
  - `reset`
  - `state`
  - `checkpoint`
  - `restore`
  - `step`
  - `stop`
- bridge 内部才真正 import upstream `env.Actor`

所以从 ORBIT 角度看，OpenEnv 是一个**本地 IPC 服务**，不是直接函数调用。

### ASCII：本地 bridge 结构

```text
ORBIT synth controller
  |
  | Client(AF_UNIX)
  v
openenv_server.py
  |
  | asyncio.run(actor.reset/state/checkpoint/restore/step/stop)
  v
upstream env.Actor (SWE-INFINITE)
  |
  v
EpisodeState + Docker task container
```

## upstream `EpisodeState` 的精确定义

当前 upstream `SWE-INFINITE` 在本地检查路径
`/tmp/affinetes-orbit-inspect/environments/SWE-INFINITE/env.py` 的
`EpisodeState` 定义处记录了该状态结构。

核心字段如下：

| 字段 | 含义 | 排障意义 |
|---|---|---|
| `episode_id` | 当前 OpenEnv episode 的唯一 ID | 用于关联所有 `reset/step/state/checkpoint/restore` |
| `task_id` | 当前任务 ID | 对应具体 SWE task |
| `seed` | reset 时使用的随机种子 | 用于复现 |
| `task` | 原始 task payload | 包含 `dockerhub_tag`、`problem_statement` 等 |
| `container_id` | 当前 Docker task container ID | restore 后会变化 |
| `docker_image` | 当前任务镜像 | 用于重建 restore 容器 |
| `messages` | upstream agent conversation 历史 | 这是 upstream 主线 prompt 分布的真实来源 |
| `step_count` | 已经执行了几次 `step()` | 不等于 student_calls，包含格式错误和失败 step 计数 |
| `done` | episode 是否结束 | submit 成功或显式终止后为真 |
| `truncated` | 是否因限制被截断 | 常见于 step_limit 或异常收尾 |
| `submitted_patch` | submit 后缓存的 patch | 只在真正 submit 后有意义 |
| `latest_observation` | 上一次返回给 controller 的 observation | restore 时也会恢复 |
| `checkpoint_counter` | 已创建 checkpoint 数 | 用于生成 `...-ckpt-N` |
| `checkpoints` | checkpoint_id -> checkpoint object | restore 的真实来源 |
| `last_patch_hash` | 当前 working tree hash | 判断 patch 是否真的变了 |
| `last_changed_files` | 当前 changed files 列表 | controller 判断是否进入 patch 阶段的依据 |

## `EpisodeCheckpoint` 保存了什么

当前 checkpoint 不是“整机快照”，而是**working-tree 级快照**。

它保存：

| 字段 | 含义 |
|---|---|
| `checkpoint_id` | checkpoint 唯一 ID |
| `step_count` | 当时的 step 数 |
| `messages` | upstream episode 的消息历史 |
| `done / truncated` | 当时 episode 状态 |
| `submitted_patch` | 当时已提交 patch |
| `latest_observation` | 当时 observation |
| `git_status_short` | 当时 `git status --short` |
| `diff_patch` | unstaged diff |
| `cached_diff_patch` | staged diff |
| `patch_hash` | 由 status + diff 计算的哈希 |
| `changed_files` | 改动文件列表 |
| `file_snapshots` | 每个改动文件的完整内容快照 |
| `staged_paths` | 需要重新 stage 的路径 |

所以 restore 的含义不是：

- 回滚整个容器所有副作用

而是：

- 新起一个同镜像的 task container
- 重新 sanitize git
- 把 checkpoint 中保存的文件内容写回去
- 恢复 staged 状态
- 校验 patch hash 一致
- 再把 `EpisodeState` 中的消息、step_count、latest_observation 等一起恢复

## `reset` 的精确定义

### 输入

- `task_id`
- 可选 `seed`
- `step_limit`
- `command_timeout`

### 实际行为

`reset()` 会做这些事：

1. 从 R2 / cache 加载 task
2. 取出：
   - `dockerhub_tag`
   - `problem_statement`
3. 新起 Docker container
4. 在容器里执行 sanitize：
   - network blocklist
   - git sanitize
   - timestamp normalize
5. 创建 `EpisodeState`
6. 用 upstream `system_template + instance_template` 渲染初始消息
7. 把这两条消息同时写进：
   - `ep.messages`
   - `observation`

### 输出

`reset()` 返回的 `observation` 实际上就是：

- `system_msg`
- 空行
- `instance_msg`

这也是为什么当前 ORBIT 能从 reset observation 里退化重建出 upstream prompt 形状。

### reset 后 controller 会立刻做什么

当前 ORBIT 在 `reset()` 后马上做两件事：

1. `checkpoint(baseline)`
2. 可选 `runtime_probe`

所以看到一条 run 一开始只有：

- `reset`
- `checkpoint`
- `runtime_probe`

是正常的。

## `step` 的精确定义

这是最容易混淆的地方。

### step 的输入不是“裸命令”

upstream `step(action)` 的输入是**完整 action 文本**，而不是裸 bash 命令。

它期望的是类似：

```text
THOUGHT: ...

```bash
your_command_here
```
```

然后 upstream 会用正则去提取其中唯一的 bash block。

### step 内部算法

当前 upstream `step()` 的顺序是：

1. 检查 `episode_id`
2. 检查 episode 是否存在
3. 检查 episode 是否已 `done`
4. 检查 `step_limit`
5. 把原始 action 文本追加为一条 `assistant` 消息
6. `step_count += 1`
7. 解析 bash block
8. 如果格式不对：
   - 返回 format error observation
   - 这次 step 仍然已经计数
9. 如果格式对：
   - 在容器里执行 bash command
10. 如果超时：
   - 返回 timeout observation
11. 如果命中了 submit marker：
   - 提取 patch
   - 跑 verify
   - 返回带 reward 的最终 observation
12. 否则：
   - 用 `action_observation_template` 把输出包成：
     - `<returncode>...</returncode>`
     - `<output>...</output>`
   - 追加为一条 `user` 消息
   - 刷新 `last_patch_hash / last_changed_files`
   - 返回普通 step 结果

### 关键点：一次 `step` 到底算什么

可以把一次 `step` 定义为：

> “向 upstream episode 提交一条 student action 文本，upstream 负责解析、执行、格式化 observation，并把这轮 assistant/user 对话追加到 episode history。”

也就是说，`step` 的原子单位不是：

- 一个 shell token
- 一个编辑操作

而是：

- 一条完整的 upstream agent response

### `step_count` 为什么有时看起来偏大

因为下面这些也会消耗 `step_count`：

- 格式错误 action
- 超时 action
- 没产生 patch 的 search/view action

所以 `step_count != changed_files 阶段数`。

## `state` 的精确定义

`state()` 不会执行命令，它只是把当前 episode 的关键摘要返回给 controller。

### `state().observation` 当前包含

固定几行：

```text
episode_id: ...
task_id: ...
step_count: ...
done: ...
truncated: ...
changed_files: ...
latest_checkpoint_id: ...
```

### `state().info` 当前包含

至少这些字段：

| 字段 | 含义 |
|---|---|
| `task_id` | 当前 task |
| `seed` | 当前 seed |
| `step_count` | 当前 step 数 |
| `instance_id` | task 实例 ID |
| `checkpoint_count` | 已有 checkpoint 数 |
| `checkpoint_capable` | 当前环境支持 checkpoint |
| `latest_checkpoint_id` | 最新 checkpoint |
| `last_patch_hash` | 当前 patch hash |
| `changed_files` | 当前 changed files |

### controller 如何使用 `state`

ORBIT 在每次 `step()` 后几乎都会接一条 `state()`，用于更新：

- `latest_changed_files`
- `last_patch_hash`
- `done / truncated`

这是 controller 判断“是否已进入 patch 阶段”的唯一可信来源。

## `checkpoint` 的精确定义

当前 `checkpoint()` 的真实语义是：

> 捕获当前 episode 的 conversation state + working-tree state，并返回一个 checkpoint_id。

### checkpoint 什么时候会失败

例如：

- 没有 episode_id
- episode 不存在
- changed files 超过当前上限
- 文件快照读取失败

### checkpoint 后哪些字段会更新

在 upstream 侧：

- `ep.checkpoint_counter += 1`
- `ep.checkpoints[checkpoint_id] = checkpoint`
- `ep.last_patch_hash = checkpoint.patch_hash`
- `ep.last_changed_files = checkpoint.changed_files`

所以 checkpoint 本身也会刷新 OpenEnv 层对 patch 状态的认知。

## `restore` 的精确定义

`restore()` 不是简单的“git checkout”。

它的真实顺序是：

1. 找到目标 checkpoint
2. 启动一个新的同镜像 container
3. 对新 container 再做一遍 sanitize
4. 停掉旧 container
5. 把 checkpoint 里的文件内容恢复到新 container 的 `/app`
6. 恢复 staged paths
7. 重新计算 patch hash，必须与 checkpoint 一致
8. 恢复 `EpisodeState` 中这些字段：
   - `step_count`
   - `messages`
   - `done`
   - `truncated`
   - `submitted_patch`
   - `latest_observation`
   - `last_patch_hash`
   - `last_changed_files`

### restore 返回什么

`restore()` 返回的 `observation` 默认是：

- `ep.latest_observation`

所以 controller 在 restore 后看到的 observation，通常是“当时 checkpoint 所对应的上一条 observation”，不是新的 shell 输出。

## 为什么 `runtime_probe` 后要马上 restore

这是一个常见迷惑点。

`runtime_probe` 本身是一次真实 `step()`，它会：

- 增加 `step_count`
- 追加 assistant/user 消息
- 改变 episode history

如果不 restore，student 的真实第一条 action 之前就会多出一轮 probe 历史。

当前 controller 的做法是：

1. `step(runtime_probe_command)`
2. 读取可用解释器
3. `restore(baseline)`

这样：

- controller 得到了 runtime 能力信息
- 但 student 会继续从 baseline 对话状态开始

所以 probe 对 student prompt 分布是“环境外信息”，不会污染 first prompt 形状。

## 从环境角度看，当前最重要的排障方法

如果一条 run 行为不对，建议按下面顺序查：

1. 看 `reset` observation
   - 确认 upstream `system + instance` 是否正常
2. 看 `runtime_probe`
   - 确认 `preferred_runtime`
3. 看第一条 `model_action`
   - 确认 student 看到的 prompt 角色序列
4. 看第一条 `step`
   - 确认真正执行了什么命令
5. 看随后一条 `state`
   - 确认 `changed_files`、`last_patch_hash`
6. 看是否发生 `checkpoint`
   - baseline / post-edit 分别什么时候建
7. 看是否发生 `restore`
   - 是 `post-probe`、`baseline` 还是 `edit`
8. 看 `teacher_decision` / `teacher_think`
   - 是否真的触发
9. 最后再看 manifest 汇总

也就是说，排障时优先级应当是：

```text
raw/synthesis_events.jsonl
    >
OpenEnv state / checkpoint / restore 语义
    >
manifest
```

## 核心思想：这是“单步控制器”，不是树搜索器

当前 active pipeline 的控制粒度是：

- 每次只让 student 输出**一个下一步动作**
- ORBIT 根据执行结果决定下一步：
  - 继续 student
  - 注入 teacher-think
  - 请求 teacher 做 structured restore 决策
  - restore 到 baseline
  - restore 到某个 recent edit checkpoint
  - 结束

所以它不是：

- MCTS
- beam search
- patch tree
- ORBIT 侧 verifier search

而是一个**带 checkpoint / restore / retry 的单轨 OpenEnv 控制器**。

## 主循环中的关键状态变量

当前实现里，最重要的状态变量集中在
`orbit/integrations/affinetes_swe/synthesis.py` 的
`run_openenv_synthesis(...)`。

### 关键运行时状态

- `episode_id`
  - upstream OpenEnv 当前 episode

- `baseline_checkpoint_id`
  - reset 之后立刻创建的基线 checkpoint

- `edit_checkpoint_id`
  - 第一次观察到真实文件改动后创建的 checkpoint

- `current_observation`
  - 当前给下一轮 prompt 的环境反馈

- `latest_changed_files`
  - 当前 state() 返回的 changed files

- `last_patch_hash`
  - 当前 patch hash，用来判断 patch 是否真的变化

- `last_viewed_file`
  - controller 认为“上一轮已经 inspect 过”的文件

- `last_candidate_file`
  - controller 从搜索输出中提取的候选文件

- `preferred_runtime`
  - 当前环境下优先使用的编辑解释器

- `no_progress_commands`
  - 近期被判定为“无进展”的命令列表

- `root_retries_used`
  - 已经用了几次 baseline restore 重开首步

- `edit_retries_used`
  - 已经用了几次 restore(edit checkpoint) 重试 follow-up

- `student_calls / teacher_calls / teacher_branch_calls / teacher_think_calls`
  - 四类调用计数
  - 注意：
    - `teacher_calls` 现在统计的是 teacher structured controller decision 调用次数
    - `teacher_branch_calls` 现在主要是兼容字段；active 路径里真正的决策字段是 `restore_target`
    - `teacher_think_calls` 统计 think 注入事件次数
    - 不再表示“teacher 直接生成 action 的次数”

## 主循环伪代码

可以把当前控制逻辑抽象成下面的伪代码：

```text
reset(task)
checkpoint(baseline)
student_messages = upstream(system_template, instance_template)

if probe_runtime:
    step(runtime_probe_command)
    restore(baseline)
    preferred_runtime = derive_from_probe()

for step_index in range(max_steps):
    decision = teacher_controller_decision(full_privileged_context)
               or heuristic_fallback_if_no_teacher(...)

    if decision.restore_target == STOP:
        break

    if decision.restore_target == BASELINE:
        restore(baseline)
        student_messages = messages_at_baseline
        continue

    if decision.restore_target startswith ROLLBACK_:
        restore(recent_edit_checkpoint)
        student_messages = messages_at_rollback_checkpoint
        continue

    teacher_think_text = decision.teacher_think_text if decision.inject_teacher_think else ""

    messages = copy(student_messages)
    if teacher_think_text:
        messages.append(hidden_teacher_guidance_as_user_message)

    action = call_student(messages)
    action = normalize_action(action)

    step_payload = step(action)
    state_payload = state()

    student_messages.append(assistant_action)
    student_messages.append(user_observation)

    update(latest_changed_files, patch_hash, viewed_file, candidate_file, ...)

    if latest_changed_files and not edit_checkpoint_id:
        checkpoint(post-edit)

    if done or truncated:
        break

stop()
write_manifest()
```

## 初始化阶段算法

### 1. reset

首先调用 upstream OpenEnv 的 `reset(task_id)`。

这一步返回：

- 任务描述
- issue / PR 文本
- episode_id
- 初始 observation

这个 observation 里通常包含完整的任务说明。

### 2. baseline checkpoint

reset 成功后，立即创建 baseline checkpoint。

用途：

- 如果第一步探索完全没用，可以直接回到干净状态
- 支持 `root retry`

### 3. runtime probe

如果开启 `--probe-runtime`，controller 会先在容器里跑一条轻量命令：

```text
command -v python3
command -v python
command -v ruby
command -v perl
```

然后把可用解释器解析成：

```text
python3 > perl > python > ruby > sed
```

这个顺序决定了后续 prompt 里优先鼓励哪种编辑方式。

probe 做完后，会 restore 到 baseline，避免 probe 自身污染后续状态。

## Prompt 构造算法

当前 student prompt 的**基础模板**是固定的 upstream 形状；ORBIT 只是在这个固定模板之上追加对话历史和可选的 teacher-think 引导消息。

### 当前 prompt 构造算法

这里是当前实现最关键的变化之一：

- student prompt **不再**由 ORBIT 自己重新拼一套动态模板
- student prompt 的基础形状来自 upstream `affinetes`：
  - `system_template`
  - `instance_template`

当前实现的 `_render_upstream_student_messages(...)` 会按两种模式工作：

1. 如果 per-run runtime 里能读到 upstream `agents/config.yaml`，并且本地有
   `yaml + jinja2`
   - 就直接渲染真实 upstream 模板
2. 如果轻量远端 runtime 缺少 `jinja2` 等依赖
   - 就从 `reset()` 返回的 observation 中切出：
     - `<pr_description>` 之前作为 `system`
     - `<pr_description>` 开始到结尾作为 `user`

因此，当前 student prompt 的核心约束是：

- **首轮一定是 upstream `system + instance` 形状**
- 后续不再“重写模板”，而是在这个序列上继续追加对话历史

### 后续 student prompt 的组成

从第二轮开始，student 实际看到的是：

1. 初始 upstream `system_template`
2. 初始 upstream `instance_template`
3. student 上一轮输出的 action，作为 `assistant`
4. upstream `step()` 返回的 observation，作为 `user`
5. 如果本轮启用了 teacher-think：
   - 额外再追加一条 `user` 消息：
     - `Teacher guidance for your next THOUGHT only: ...`

这意味着：

- 基础模板保持 upstream 一致
- teacher 干预不通过替换模板，而是通过：
  - restore_target 决策
  - 或一条额外的隐藏 guidance 消息

## controller 判断来源

这是当前实现里最重要的一条事实：

- **controller 的策略判断默认来自 teacher 模型**
- teacher 返回的是**结构化 JSON 决策**
- 本地硬编码主要只负责：
  - 事实提取
  - 运行时能力探测
  - 动作归一化
  - 在没有 teacher model 时提供保底 fallback

### teacher decision 的结构

当前 teacher controller decision 的输出结构是：

```json
{
  "restore_target": "CURRENT | BASELINE | ROLLBACK_1 | ROLLBACK_2 | ROLLBACK_3 | ROLLBACK_4 | STOP",
  "inject_teacher_think": false,
  "teacher_think_text": "short hidden guidance",
  "stall_class": "none | no_action | repeat_read_loop | repeat_search_loop | stuck_patch | bad_patch_loop | verify_loop",
  "reason": "why this decision was made"
}
```

约束是：

- 如果 `restore_target != CURRENT`
  - 则不允许同时注入 think
- 如果 `inject_teacher_think = false`
  - 则 `teacher_think_text` 必须为空

### teacher decision 使用的上下文

teacher 在做 controller 判断时，看到的是一份 privileged context，而不只是当前 observation。

这份上下文至少包括：

- `task_id`
- `step_index / max_steps`
- `issue_context / problem_statement`
- `current_observation`
- `latest_changed_files`
- `last_patch_hash`
- `last_viewed_file`
- `last_candidate_file`
- `no_progress_commands`
- `preferred_runtime`
- `runtime_availability`
- `baseline_checkpoint_id`
- `edit_checkpoint_id`
- `root_retries_used / max_root_retries`
- `edit_retries_used / max_edit_retries`
- `edited_stall_count`
- `post_edit_stall_steps`
- `last_followup_signature`
- `student_messages` 全历史
- `last_step_payload`
- `last_state_payload`

所以当前 controller 的决策不是：

- “本地 if/else 决定所有东西”

而是：

- “本地先抽取事实，再把事实和完整历史交给 teacher 做结构化判断”

## Student / Teacher 干预算法

当前已经没有“teacher 直接 takeover 生成 action”的 active 路径。

### student 的职责

- 每一步真正执行前，只有 student 生成 shell action
- `model_action` 事件里的 `actor` 现在应当始终是 `student`

### restore_target 的语义

teacher 会在 structured decision 里给出一个 restore 决策：

- `CURRENT`
- `BASELINE`
- `ROLLBACK_1`
- `ROLLBACK_2`
- `ROLLBACK_3`
- `ROLLBACK_4`
- `STOP`

controller 再根据这个结构化输出决定：

- 继续当前状态
- restore baseline
- restore 某一个 recent edit checkpoint
- 或者停止 run

### teacher_think 触发条件

teacher-think 是另一条独立支路，也不等于 action takeover。

当 structured decision 判断“当前应继续 student，但需要额外引导”时，会请求：

- 一段短 reasoning 文本
- 不含命令
- 不含代码块

然后把它注入为下一轮 student 调用前的一条隐藏 guidance 消息。

### 当前真实结果

在当前 active 路径中，真实会观察到：

- `teacher_decision`
- `teacher_think`
- 并且没有任何 `model_action(actor=teacher)`

所以当前 active 路径的事实是：

- teacher 负责 controller 决策
- 但 teacher 的输出被限制成结构化 restore/think
- 真正执行 action 的仍然只有 student

## 动作归一化算法

模型返回的原始文本不一定干净。controller 会做几层归一化。

### 1. 提取 bash block

如果模型返回多个 bash block，会根据当前阶段打分选一个：

- `prefer_verify`
- `prefer_edit`
- `prefer_view`

也就是说 controller 不只是“取最后一个 block”，而是按阶段偏好做选择。

### 2. `<SUBMIT>` 物化

如果模型返回 `<SUBMIT>`，controller 会把它变成 upstream 识别的实际提交命令：

```bash
echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && git add -A && git diff --cached
```

### 3. runtime rewrite

如果 preferred runtime 是 `python3`，而模型输出 `python - <<'PY'`，controller 会自动改写成 `python3 - <<'PY'`。

### 4. runtime rejection

如果当前环境 preferred runtime 是 `perl`，但模型又输出 `ruby` 或 `python3`，controller 可以直接拒绝这条命令，不执行，只更新 observation 然后进入下一轮。

## 执行后状态更新算法

每次 `step(action)` 之后，controller 会立刻再调一次 `state()`。

这一步更新以下关键变量：

- `latest_changed_files`
- `last_patch_hash`
- `step_count`
- `done / truncated`

另外还会根据 command 类型更新：

- `last_viewed_file`
- `last_candidate_file`

### viewed file 更新

当上一条命令被判定为 file-view command，且有输出时：

- `last_viewed_file = _extract_viewed_file(executed_command) or last_candidate_file`

### candidate file 更新

当上一条命令被判定为 search command，且输出里有 `file:line:` 样式结果时：

- `last_candidate_file = _extract_first_candidate_file(output_text)`

## checkpoint / restore 算法

### baseline checkpoint

创建时机：

- reset 之后立即创建

作用：

- root retry 的回滚点

### post-edit checkpoint

创建时机：

- 第一次发现 `latest_changed_files` 非空时

作用：

- follow-up 重试的回滚点

### edit restore 触发条件

当已经有 patch 时，如果：

- follow-up 命令没有改变 patch hash
- 或者反复在 verify / view 上打转
- 或者无输出 verify / view 重复出现

controller 会：

- `restore(edit_checkpoint)`
- `edit_retries_used += 1`
- 重新提示“从上一个已编辑状态继续，但换一个 follow-up 动作”

### baseline restore 触发条件

如果当前还没有 patch，且首步探索明显无用，同时 `root_retries_used < max_root_retries`：

- `restore(baseline_checkpoint)`
- `root_retries_used += 1`
- 清空 `last_viewed_file` / `edit_checkpoint_id`
- 重新尝试不同的首步

## no-progress 判定算法

当前 no-progress 仍然由本地规则抽取，但它的作用已经变成：

- 给 teacher structured decision 提供特权上下文特征

而不是：

- 本地直接据此决定 restore / takeover

### 被硬编码判成 no-progress 的命令

- `ls`
- `ls -la`
- `pwd`
- `git status`
- `git log --oneline ...`

### 失败命令也会进入 no-progress 历史

例如：

- command not found
- syntax error
- rc != 0

这些命令会被记入 `no_progress_commands`，随后作为 privileged context 提供给
teacher 的 structured decision。

## 什么时候认为“进入 patch 阶段”

判定标准很朴素：

- 只要 `state()` 返回的 `changed_files` 非空

一旦进入这个状态，controller 会：

- 创建 `post-edit checkpoint`
- 后续 prompt 从“找文件 / 直接 edit”切换成“修 patch / verify / submit”

## 当前 pipeline 的几个关键弱点

### 1. 文件提取启发式太弱

`_extract_viewed_file()` 仍然主要靠 token 启发式判断文件名。即使 teacher 不再直接出 action，
这个弱点仍然会污染：

- `last_viewed_file`
- `last_candidate_file`
- 以及后续 branch / think 的上下文质量

### 2. 缺少 candidate 存在性校验

controller 在把 `last_viewed_file` / `last_candidate_file` 喂进下一轮 prompt 之前，没有验证这个路径是否真存在于 repo。

### 3. student 容易停在 search / view，而不落 patch

最近几轮真实结果表明：

- prompt-match 修好后，student 的首轮 prompt 已经正常
- 但 student 仍然经常停在：
  - 搜索
  - 查看目录
  - 查看文件
- 不一定能自然推进到最小 patch

### 4. 模型服务兼容性差异很大

当前 student endpoint 之间有明显差异：

- 有的实现 `/v1/responses`
- 有的不实现，只能走 `/v1/chat/completions`
- 有的拒绝 `enable_thinking`
- 有的 `responses` 会直接 5xx

controller 已经补了多层 fallback，但服务差异本身仍然影响轨迹质量。

### 5. teacher_think 是否能触发，与 teacher decision + 模型行为共同相关

当前代码路径支持 `teacher_think`，但最近批次里没有自然触发。

这说明：

- 功能开关已经在
- 但真正是否出现，取决于：
  - no-progress 模式
  - 当前 branch 决策
  - 模型本身的 rollout 行为

## 当前如何读一条轨迹

最重要的文件是：

- `raw/synthesis_events.jsonl`

建议按这个顺序读：

1. `reset`
2. `checkpoint(baseline)`
3. `runtime_probe`
4. `restore(post-probe)`
5. 第一条 `model_action`
6. 第一条 `step`
7. 第一条 `state`
8. 是否创建了 `post-edit checkpoint`
9. 是否出现 `restore(scope=edit)` 或 `restore(scope=baseline)`
10. 最后的 `stop`

其次看：

- `manifests/synthesis_run.json`

重点字段：

- `student_calls`
- `teacher_calls`
- `teacher_branch_calls`
- `teacher_think_calls`
- `root_retries_used`
- `edit_retries_used`
- `runtime_availability`
- `preferred_runtime`
- `latest_changed_files`
- `final_reward`
- `verified_success`
- `final_test_stats`
- `model_stop_reason`
- `student_transport`
- `student_finish_reason_type`
- `student_finish_reason_length`
- `student_max_new_tokens`
- `final_observation`

补充说明：
- `final_reward` 来自 upstream OpenEnv 最终 `step(done=true|truncated=true)` 返回的 `reward`。
- `final_done=true` 只表示 episode 走到了上游终止/提交，不等于 `verified_success=true`。

## 当前最实用的理解方式

把当前 pipeline 理解为下面这句话最准确：

> ORBIT 维护一组控制状态变量；每一步根据这些状态变量决定该不该 restore、该不该重试、该不该请求 teacher 做 branch 或 think 干预；真正的环境推进由 upstream OpenEnv 执行，真正的下一步 action 始终由 student 输出。

## 与英文文档的关系

建议这样使用两份文档：

- 英文版：
  - [swe-synthesis-pipeline.md](swe-synthesis-pipeline.md)
  - 用于看系统边界、部署形态、artifact

- 中文版：
  - 本文
  - 用于理解算法、状态变量、决策逻辑和错误轨迹为什么会发生
