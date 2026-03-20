# SWE-Infinite 数据蒸馏方案

## 目标

从 R2 中已有的 ~346 个 SWE-Infinite 任务出发，用强模型（GPT-5.4 / Claude）生成成功修复轨迹，转化为 Qwen3-32B 的 SFT 训练数据。

## 核心约束

1. **训练数据格式必须匹配评估格式**（THOUGHT + 单个 bash 命令，多轮对话）
2. **只保留 score=1.0 的轨迹**（所有 FAIL_TO_PASS 测试通过）
3. **不能用我们自己的 Qwen 模型**生成轨迹（太弱），必须用强教师模型
4. **Docker 容器是必需的**（每个任务有独立的 Docker 镜像）

## 方案选择

### 方案 A: 直接复用 InfiniteActor.evaluate()

调用 `affinetes` 的 `evaluate()` 方法，传入教师模型 API，让它完成整个流程（agent → fix → verify），然后从返回的 `conversation` 字段提取训练数据。

**优点**: 零代码开发，验证逻辑已内置，格式天然对齐
**缺点**: `evaluate()` 设计为评估而非数据生成，无法控制系统 prompt 细节、无批量并行

### 方案 B: 复用 MiniSWE + 自定义外壳 ✅ 推荐

用 `minisweagent` 库（MiniSWE 使用的底层库）+ 自定义脚本来:
1. 从 R2 加载任务
2. 启动 Docker 容器
3. 用教师模型运行 agent loop
4. 验证 patch
5. 导出会话为训练数据

**优点**: 完全控制格式、可并行、可断点续跑、复用成熟的 Docker 交互逻辑
**缺点**: 需要写 ~300 行脚本

### 方案 C: 基于 CodexAugmenter 模式（纯 API 调用）

不依赖 minisweagent 库，直接用 `requests` 调 LLM API + `docker exec` 跑命令（CodexAugmenter 的模式）。

**优点**: 无额外依赖，完全控制，最灵活
**缺点**: 需要自己处理 tool call 解析、重试逻辑

### 决策: 方案 C

理由:
- **零外部依赖** — 不需要安装 minisweagent / litellm
- **格式精确控制** — 可以让 system prompt 与评估环境 config.yaml 完全一致
- **已有参考实现** — `codex_augmenter.py` 已经验证了 LLM-in-Docker 模式
- **并发友好** — ThreadPoolExecutor 即可
- **断点续跑** — 按 task_id 写 JSONL，skip 已完成的

## 架构

```
scripts/swe_distill.py          # 主脚本（单文件，~400行）
  ├── TaskLoader                 # R2 两级缓存加载任务
  ├── AgentRunner                # LLM agent loop (THOUGHT + bash)
  ├── PatchVerifier              # Docker 内验证 patch
  └── TrajectoryExporter         # 导出为训练 JSONL
```

## 详细设计

### 1. 任务加载

复用 `cache.py` 的 `TwoLevelCache`（L1 本地 + L2 R2 HTTP）。

```python
# R2 public URL: https://pub-7882418a56434a479bf9a7febd660b36.r2.dev/bugs/task_NNNNNNNNNNN.json
# 当前 ~346 个任务 (task_1 ~ task_346)
cache = TwoLevelCache()
task = cache.load(str(task_id))  # 返回 dict: instance_id, repo, patch, test_patch, ...
```

### 2. Agent Loop

**系统 prompt**: 直接使用 `repos/affinetes/environments/SWE-INFINITE/agents/config.yaml` 中的 `system_template` + `instance_template`，用 Jinja2 渲染 `{{task}}` 为 `problem_statement`。

**交互协议**:
```
system: [system_template]
user:   [instance_template(task=problem_statement)]
assistant: THOUGHT: ... ```bash cmd ```
user:   <returncode>N</returncode><output>...</output>
assistant: THOUGHT: ... ```bash cmd ```
...
assistant: THOUGHT: ... ```bash echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && git add -A && git diff --cached ```
```

**LLM 调用**: 直接 `requests.post()` 到 OpenAI-compatible API（同 CodexAugmenter）。

**命令执行**: `docker exec <container> bash -c "<cmd>"` + 输出截断(4000 chars)。

**终止条件**:
- Agent 输出包含 `COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`
- 达到 max_steps (50)
- 达到 wall_time (600s)
- Agent 无 bash 块（格式错误 3 次连续）

### 3. Patch 提取与验证

从 agent 最后一次 `git diff --cached` 输出中提取 patch。

验证流程（复用 InfiniteActor._verify() 的逻辑）:
```
1. 启动新容器（同一 Docker 镜像）
2. 应用 test_patch（如果有 augmented_test_patch 也应用）
3. 应用 agent 生成的 fix_patch
4. 运行测试命令
5. 解析测试输出，检查 FAIL_TO_PASS 是否全部通过
6. score = 1.0 if all pass else 0.0
```

### 4. 训练数据格式

输出 JSONL，每行:
```json
{
  "messages": [
    {"role": "system", "content": "<system_template>"},
    {"role": "user", "content": "<instance_template with problem_statement>"},
    {"role": "assistant", "content": "THOUGHT: ...\n\n```bash\n...\n```"},
    {"role": "user", "content": "<returncode>0</returncode>\n<output>...</output>"},
    ...
    {"role": "assistant", "content": "THOUGHT: ...\n\n```bash\necho COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && git add -A && git diff --cached\n```"}
  ],
  "env": "SWE-INFINITE",
  "score": 1.0
}
```

**关键格式规则**:
- `env` 字段: `"SWE-INFINITE"`（不再是 `"SWE-SYNTH"`）
- 最后一条消息必须是 `assistant`
- 不含 `<think>` 标签
- 每个 assistant 消息: THOUGHT + 恰好一个 bash 代码块
- observation 使用 `<returncode>` + `<output>` 包裹（匹配 config.yaml 的 `action_observation_template`）

### 5. 质量过滤

| 过滤器 | 条件 | 原因 |
|--------|------|------|
| score | == 1.0 | 只要成功修复 |
| min_turns | >= 3 assistant turns | 太短的轨迹可能是运气 |
| max_turns | <= 40 assistant turns | 太长的效率低 |
| max_chars | <= 60000 chars total | seq_len 限制 |
| format | 每个 assistant 都有 bash 块 | 格式合规 |
| no_think_tags | 无 `<think>` | 避免污染 |

### 6. 并发与断点续跑

```python
# 并发: 2-3 个任务同时跑（受 Docker 和 API 限制）
# 断点续跑: 每完成一个任务立即 append 到 output.jsonl
#           启动时读 output.jsonl 获取已完成的 task_id set
#           跳过已完成的
```

### 7. 容器生命周期

```
每个任务:
  1. docker pull <dockerhub_tag>          # 拉取任务镜像
  2. docker run -d --name <id> <image>    # 启动容器
  3. git sanitize + timestamp normalize   # 防作弊处理
  4. agent loop (docker exec)             # 多轮交互
  5. docker exec: git diff --cached       # 提取 patch
  6. 验证: 新容器 → apply patches → run tests
  7. docker rm -f <id>                    # 清理

清理: finally 块确保容器始终被删除
```

### 8. 教师模型选择

| 模型 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| GPT-5.4 | SWE-bench 最强，修复率最高 | 成本高，需 OpenAI API key | ⭐⭐⭐ |
| Claude Sonnet 4 | 性价比好，coding 强 | 可能比 GPT-5.4 弱一些 | ⭐⭐ |
| Claude Opus 4 | 最强推理 | 最贵 | ⭐ |

**建议**: 先用 GPT-5.4 跑一轮（修复率最高），再用 Claude Sonnet 补充（成本低可以跑更多）。

### 9. 成本估算

- ~346 个任务
- 假设每个任务平均 15 轮 × 3K tokens/轮 ≈ 45K tokens
- GPT-5.4: ~$0.02/1K tokens → ~$0.90/task → ~$310 total
- 假设 40% 修复率 → ~138 个成功轨迹
- Claude Sonnet: ~$0.006/1K tokens → ~$0.27/task → ~$93 total

**总预算**: ~$400 for 150-200 成功轨迹

### 10. CLI 接口

```bash
# 基本用法
python3 scripts/swe_distill.py \
  --model gpt-5.4 \
  --api-base https://api.openai.com/v1 \
  --api-key $OPENAI_API_KEY \
  --task-range 1-346 \
  --output data/swe_infinite_trajectories.jsonl \
  --workers 2

# 断点续跑（自动跳过已完成）
python3 scripts/swe_distill.py --resume --output data/swe_infinite_trajectories.jsonl

# 只验证（不调 LLM，只检查格式）
python3 scripts/swe_distill.py --validate-only data/swe_infinite_trajectories.jsonl
```

## 实施计划

### Phase 1: 脚本骨架 (Day 1)
- [ ] `scripts/swe_distill.py` 基础结构
- [ ] 任务加载（TwoLevelCache）
- [ ] Docker 容器管理（start/exec/stop）
- [ ] 用简单 echo 命令验证容器交互

### Phase 2: Agent Loop (Day 1-2)
- [ ] LLM API 调用 + tool call 解析
- [ ] THOUGHT + bash 格式提取（regex: `r"```bash\s*\n(.*?)\n```"`)
- [ ] 命令执行 + 输出截断
- [ ] 提交检测（COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT）

### Phase 3: 验证 + 导出 (Day 2)
- [ ] Patch 提取（从 git diff 输出）
- [ ] 测试验证（apply test_patch → fix_patch → run tests）
- [ ] JSONL 导出（messages + env + score）
- [ ] 质量过滤

### Phase 4: 批量运行 (Day 2-3)
- [ ] 并发执行（ThreadPoolExecutor）
- [ ] 断点续跑
- [ ] 统计报告（成功率、语言分布、轮次分布）

### Phase 5: 集成 (Day 3)
- [ ] `forge data ingest` 接入
- [ ] HF 上传
- [ ] 更新 synth_config.json

## 关键参考代码

| 功能 | 参考文件 | 具体位置 |
|------|----------|----------|
| LLM-in-Docker agent loop | `repos/affine-swe-infinite/src/augmenters/codex_augmenter.py` | `_agent_loop()` L457-528 |
| Docker exec 封装 | 同上 | `_exec()` L384-393 |
| API 调用 + 重试 | 同上 | `_call_llm()` L401-455 |
| Model pool + fallback | 同上 | `ModelPool` class L249-297 |
| 系统 prompt 模板 | `repos/affinetes/environments/SWE-INFINITE/agents/config.yaml` | 全文 |
| 测试输出解析 | `repos/affinetes/environments/SWE-INFINITE/utils.py` | `parse_test_output()` |
| Git sanitize 脚本 | 同上 | `SANITIZE_GIT_SCRIPT` |
| Patch 验证流程 | `repos/affinetes/environments/SWE-INFINITE/env.py` | `_verify()` L228-310 |
| 两级缓存 | `repos/affinetes/environments/SWE-INFINITE/cache.py` | `TwoLevelCache` |
| 训练数据清洗 | `forge/data/sft.py` | `_clean_swe_synth()` L78-99 |
| Canonical 验证 | `forge/data/canonical_ops.py` | `validate_entry()` L38-78 |

## 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| Docker 镜像拉取慢/失败 | 无法运行任务 | 预拉取 + 本地缓存 + DockerHub 认证 |
| 教师模型修复率低 | 训练数据量不够 | 多模型组合、调高 temperature 多次尝试 |
| 容器泄漏（未清理） | 磁盘/内存耗尽 | finally 块 + 定期清理 + --memory 4g |
| API 限流 | 速度慢 | 指数退避 + 多 API key |
| 格式不匹配评估 | 训练无效 | 直接用评估环境的 config.yaml 模板 |
