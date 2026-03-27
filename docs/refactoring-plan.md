# Affine-Swarm 重构计划：三层解耦架构

## 一、问题分析：当前耦合现状

### 1.1 核心问题

```
当前 forge/ 是一个单体 CLI 包，所有关注点混在一起：
├── 环境逻辑散落在 data/sft.py(6个cleaner)、data/navworld_gen.py、scripts/game_distill.py 等
├── Prompt 模板硬编码在各生成脚本和 data/navworld_prompts.py 中
├── 训练配置在 training/config.py 中以字符串拼接方式生成完整 Python 脚本
├── 评估是 scripts/eval_envs.py 这一个大脚本
├── 实验管理完全靠 YAML 文件 + 人工操作
└── Agent 工作流是文档驱动（ROLE.md），无代码自动化
```

### 1.2 具体耦合点

| 耦合点 | 问题描述 |
|--------|---------|
| 环境 ↔ 数据清洗 | `sft.py` 中 `_clean_game()/_clean_navworld()` 等环境专属逻辑与通用数据管道混在一起 |
| 环境 ↔ 生成脚本 | 每个环境的数据生成散落在 `forge/data/` 和 `scripts/` 两处，无统一接口 |
| 训练 ↔ 计算 | `training/runner.py` 直接操作 Targon/SSH 细节，嵌入了 wheel 下载、pip 安装等部署逻辑 |
| 训练 ↔ 配置 | `training/config.py` 的 `to_train_script()` 把超参、模型加载、回调全部拼成一个字符串 |
| 评估 ↔ 环境 | `eval_envs.py` 内部 hardcode 了各环境的 task 生成和评分逻辑 |
| Prompt ↔ 环境 | `navworld_prompts.py` 的 system prompt、tool schema 与生成逻辑耦合 |

---

## 二、目标架构：三层分离

参考 ALE 生态（ROCK 环境管理 + ROLL 训练框架 + iFlow 智能编排）的设计理念，将系统分为：

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 2: Agent 层 — 自动化编排                               │
│  ┌────────────┐ ┌────────────┐ ┌──────────────┐            │
│  │ AutoExper- │ │ AutoEval   │ │ SelfEvolu-   │            │
│  │ iment      │ │            │ │ tion         │            │
│  └────────────┘ └────────────┘ └──────────────┘            │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: Application 层 — 业务流程                          │
│  ┌────────────┐ ┌────────────┐ ┌──────────────┐            │
│  │ DataPipe-  │ │ Evaluator  │ │ Experiment   │            │
│  │ line       │ │            │ │ Tracker      │            │
│  └─────┬──────┘ └──────┬─────┘ └───────┬──────┘            │
│        │               │               │                    │
├────────┼───────────────┼───────────────┼────────────────────┤
│  Layer 0: Foundation 层 — 基础原语（三者分离）                  │
│  ┌────────────┐ ┌────────────┐ ┌──────────────┐            │
│  │ Environ-   │ │ Prompt     │ │ Training     │            │
│  │ ment       │ │ Engine     │ │ Backend      │            │
│  └────────────┘ └────────────┘ └──────────────┘            │
└─────────────────────────────────────────────────────────────┘
```

### 依赖规则

- **Layer 0 各模块之间零依赖**（Environment 不知道 Training 的存在，Training 不知道 Prompt 的存在）
- **Layer 1 可依赖 Layer 0 的任意模块**（DataPipeline 使用 Environment + Prompt）
- **Layer 2 可依赖 Layer 1 和 Layer 0**
- **上层通过 Protocol/Interface 调用下层**，不直接依赖实现

---

## 三、Layer 0：Foundation 层详细设计

### 3.1 Environment（环境抽象）

借鉴 ROCK 的 GEM Protocol，为每个评估环境定义统一接口。

```
forge/
  env/
    __init__.py          # 导出 EnvRegistry、BaseEnv
    base.py              # Protocol 定义
    registry.py          # 环境注册表
    game.py              # GAME 环境实现
    navworld.py          # NAVWORLD 环境实现
    liveweb.py           # LIVEWEB 环境实现
    swe.py               # SWE-INFINITE 环境实现
```

**核心接口设计：**

```python
# forge/env/base.py
from typing import Protocol, Any
from dataclasses import dataclass

@dataclass
class EnvSpec:
    """环境元数据"""
    name: str                    # "GAME", "NAVWORLD" 等
    version: str                 # "v1.0"
    task_count: int              # 预估 task 数量
    completeness_threshold: float # 0.8~0.9
    scoring_weight: float        # 调度权重

class EnvProtocol(Protocol):
    """统一环境协议 — 受 GEM Protocol 启发"""

    @property
    def spec(self) -> EnvSpec: ...

    def validate_entry(self, entry: dict) -> tuple[bool, str]:
        """验证一条数据是否符合该环境格式"""
        ...

    def clean_entry(self, entry: dict) -> dict | None:
        """清洗一条数据，返回 None 表示丢弃"""
        ...

    def score_response(self, task_id: str, response: str) -> float:
        """对模型回复打分 (0-100)"""
        ...

    def sample_tasks(self, n: int, seed: int = 42) -> list[str]:
        """采样 n 个 task_id"""
        ...
```

**迁移映射：**

| 当前位置 | 迁移到 | 说明 |
|---------|--------|------|
| `sft.py::_clean_game()` | `env/game.py::GameEnv.clean_entry()` | 环境专属验证逻辑归环境自己 |
| `sft.py::_clean_navworld()` | `env/navworld.py::NavworldEnv.clean_entry()` | 同上 |
| `sft.py::_clean_liveweb()` | `env/liveweb.py::LivewebEnv.clean_entry()` | 同上 |
| `sft.py::_clean_swe_synth()` | `env/swe.py::SweEnv.clean_entry()` | 同上 |
| `canonical_ops.py::VALID_ROLES` | 各环境的 spec 配置 | 每个环境自己定义合法 roles |
| `eval_envs.py` 中的评分逻辑 | 各环境的 `score_response()` | 评分归环境 |

**环境注册表：**

```python
# forge/env/registry.py
class EnvRegistry:
    _envs: dict[str, type[EnvProtocol]] = {}

    @classmethod
    def register(cls, name: str):
        def decorator(env_cls):
            cls._envs[name] = env_cls
            return env_cls
        return decorator

    @classmethod
    def make(cls, name: str, **kwargs) -> EnvProtocol:
        return cls._envs[name](**kwargs)

    @classmethod
    def list_envs(cls) -> list[str]:
        return list(cls._envs.keys())
```

### 3.2 Prompt Engine（Prompt 编排引擎）

将 prompt 构建从数据生成脚本中抽离出来，形成独立的模板引擎。

```
forge/
  prompt/
    __init__.py         # 导出 PromptBuilder、ToolSchema
    builder.py          # Prompt 组装器
    templates/          # 按环境和用途组织的模板
      game/
        system.md
        few_shot.md
      navworld/
        system.md
        tools.json      # tool calling schema
      liveweb/
        system.md
      swe/
        system.md
    tools.py            # Tool schema 定义和验证
```

**核心接口：**

```python
# forge/prompt/builder.py
from dataclasses import dataclass

@dataclass
class Message:
    role: str           # system / user / assistant / tool
    content: str
    tool_calls: list | None = None
    tool_call_id: str | None = None

class PromptBuilder:
    """构建符合各环境要求的 prompt 序列"""

    def __init__(self, env_name: str):
        self.env_name = env_name
        self._messages: list[Message] = []

    def system(self, template_name: str, **kwargs) -> 'PromptBuilder':
        """加载系统 prompt 模板并填充变量"""
        ...

    def user(self, content: str) -> 'PromptBuilder':
        ...

    def assistant(self, content: str) -> 'PromptBuilder':
        ...

    def tool_result(self, tool_call_id: str, content: str) -> 'PromptBuilder':
        ...

    def build(self) -> list[dict]:
        """输出 OpenAI 格式的 messages 列表"""
        ...

    @classmethod
    def from_messages(cls, env_name: str, messages: list[dict]) -> 'PromptBuilder':
        """从已有 messages 重建 builder（用于数据后处理）"""
        ...
```

**迁移映射：**

| 当前位置 | 迁移到 | 说明 |
|---------|--------|------|
| `navworld_prompts.py::SYSTEM_PROMPT` | `prompt/templates/navworld/system.md` | 模板文件化 |
| `navworld_prompts.py::TOOLS_SCHEMA` | `prompt/templates/navworld/tools.json` | Schema 文件化 |
| 各脚本中硬编码的 system prompt | `prompt/templates/{env}/system.md` | 统一管理 |
| `navworld_add_think.py` 的 think 链注入 | `PromptBuilder.inject_thinking()` | Prompt 后处理 |

### 3.3 Training Backend（训练后端）

将训练从"生成脚本字符串 → 远程执行"改为声明式配置 + 可插拔执行器。

```
forge/
  training/
    __init__.py
    config.py           # TrainConfig (纯数据，不生成脚本)
    backend.py          # TrainBackend Protocol
    sft.py              # SFT 训练器
    dpo.py              # DPO 训练器
    executor/
      __init__.py
      local.py          # 本地执行
      remote.py         # 远程 SSH 执行（从 runner.py 拆出）
      targon.py         # Targon 容器执行
    model.py            # 模型管理（加载/合并/上传）
```

**核心接口：**

```python
# forge/training/backend.py
from typing import Protocol
from dataclasses import dataclass

@dataclass
class TrainConfig:
    """声明式训练配置 — 纯数据，不含逻辑"""
    method: str = "sft"              # "sft" | "dpo" | "distill"
    base_model: str = "Qwen/Qwen3-32B"
    dataset_path: str = ""
    # LoRA
    lora_r: int = 64
    lora_alpha: int = 128
    lora_target_modules: list[str] | None = None
    # Training
    learning_rate: float = 1e-4
    num_epochs: int = 1
    per_device_batch_size: int = 2
    gradient_accumulation_steps: int = 8
    max_seq_length: int = 4096
    warmup_ratio: float = 0.03
    # Quantization
    quantization: str = "nf4"        # "nf4" | "none"
    # Saving
    save_steps: int = 100
    hf_repo: str = ""

class TrainBackend(Protocol):
    """训练后端接口"""
    def launch(self, config: TrainConfig) -> str:
        """启动训练，返回 job_id"""
        ...

    def status(self, job_id: str) -> dict:
        """查询训练状态"""
        ...

    def stop(self, job_id: str) -> None:
        """停止训练"""
        ...
```

**迁移映射：**

| 当前位置 | 迁移到 | 说明 |
|---------|--------|------|
| `training/config.py::to_train_script()` | `training/sft.py` + `executor/*.py` | 配置与执行分离 |
| `training/runner.py::launch_on_targon()` | `training/executor/targon.py` | 执行器独立 |
| `training/runner.py::launch_on_ssh()` | `training/executor/remote.py` | 执行器独立 |
| `compute/` 整个目录 | `training/executor/` 合并 | 计算资源是训练的实现细节 |
| `deploy.py::merge_lora_adapter()` | `training/model.py` | 模型管理独立 |

---

## 四、Layer 1：Application 层详细设计

### 4.1 DataPipeline（数据管道）

组合 Environment + Prompt 实现数据的生成→清洗→验证→存储全流程。

```
forge/
  pipeline/
    __init__.py
    data.py            # DataPipeline 主流程
    canonical.py       # 规范数据存储（从 canonical_ops.py 精简）
    generator/
      __init__.py
      base.py          # DataGenerator Protocol
      game.py          # GAME 数据生成（从 scripts/game_distill.py 迁移）
      navworld.py      # NAVWORLD 数据生成（从 forge/data/navworld_gen.py 迁移）
      liveweb.py       # LIVEWEB 数据生成（从 scripts/liveweb_real_gen.py 迁移）
      swe.py           # SWE 数据生成（从 scripts/swe_distill.py 迁移）
```

**核心流程：**

```python
# forge/pipeline/data.py
class DataPipeline:
    def __init__(self, env_name: str):
        self.env = EnvRegistry.make(env_name)
        self.store = CanonicalStore(env_name)

    def generate(self, n: int, **kwargs) -> list[dict]:
        """调用对应 generator 生成 n 条数据"""
        gen = GeneratorRegistry.make(self.env.spec.name, **kwargs)
        return gen.generate(n)

    def ingest(self, entries: list[dict]) -> IngestReport:
        """清洗 → 验证 → 去重 → 存储"""
        results = []
        for entry in entries:
            cleaned = self.env.clean_entry(entry)
            if cleaned is None:
                results.append(("dropped", entry))
                continue
            valid, reason = self.env.validate_entry(cleaned)
            if not valid:
                results.append(("invalid", reason))
                continue
            self.store.append(cleaned)
            results.append(("accepted", cleaned))
        return IngestReport(results)

    def upload(self) -> str:
        """同步到 HuggingFace"""
        return self.store.upload_to_hf()
```

### 4.2 Evaluator（评估器）

```
forge/
  pipeline/
    eval.py            # 统一评估流程
```

```python
# forge/pipeline/eval.py
class Evaluator:
    def __init__(self, model_path: str, envs: list[str] | None = None):
        self.model_path = model_path
        self.envs = envs or EnvRegistry.list_envs()

    def run(self, samples_per_env: int = 100) -> EvalReport:
        """对每个环境运行评估"""
        results = {}
        for env_name in self.envs:
            env = EnvRegistry.make(env_name)
            tasks = env.sample_tasks(samples_per_env)
            scores = []
            for task_id in tasks:
                response = self._generate(task_id)
                score = env.score_response(task_id, response)
                scores.append(score)
            results[env_name] = EnvResult(
                mean=sum(scores)/len(scores),
                scores=scores,
                task_ids=tasks
            )
        return EvalReport(results)
```

### 4.3 ExperimentTracker（实验管理）

```
forge/
  pipeline/
    experiment.py      # 实验定义、追踪、对比
```

```python
# forge/pipeline/experiment.py
@dataclass
class Experiment:
    id: str
    variable: str          # 改变了什么
    hypothesis: str        # 预期效果
    train_config: TrainConfig
    data_config: dict      # 各环境数据配置
    status: str = "draft"  # draft → approved → running → done

class ExperimentTracker:
    def create(self, exp: Experiment) -> str: ...
    def approve(self, exp_id: str) -> None: ...
    def record_result(self, exp_id: str, eval_report: EvalReport) -> None: ...
    def compare(self, exp_a: str, exp_b: str) -> ComparisonReport: ...
```

---

## 五、Layer 2：Agent 层详细设计

### 5.1 概述

Agent 层将现有的 Strategist/Trainer/Data Agent 文档驱动工作流转化为可编程的自动化流程。

```
forge/
  agent/
    __init__.py
    base.py            # AgentProtocol
    strategist.py      # 策略制定自动化
    trainer.py         # 训练执行自动化
    data_agent.py      # 数据准备自动化
    loop.py            # 主循环编排
```

### 5.2 AutoExperiment（自动实验）

```python
# forge/agent/strategist.py
class StrategistAgent:
    """自动化策略制定 — 替代人工读 PLAYBOOK → 设计实验的过程"""

    def __init__(self, tracker: ExperimentTracker, evaluator: Evaluator):
        self.tracker = tracker
        self.evaluator = evaluator

    def analyze_gap(self) -> GapAnalysis:
        """读取最新排行榜 + 历史实验，识别最大提升空间"""
        leaderboard = Leaderboard.fetch()
        history = self.tracker.list_completed()
        # 找到几何均值中的最弱环境（木桶效应）
        return self._compute_gaps(leaderboard, history)

    def propose_experiment(self, gap: GapAnalysis) -> Experiment:
        """基于差距分析，自动提出下一个实验"""
        # 规则引擎：
        # 1. 最弱环境优先
        # 2. 检查 SFT 停滞 → 是否该切 DPO
        # 3. 一次只改一个变量
        ...

    def should_switch_method(self, env: str) -> str | None:
        """检查是否需要切换训练方法"""
        history = self.tracker.get_env_history(env)
        if self._is_plateau(history):
            return "dpo"
        if self._is_structural_zero(history):
            return "flag_unlearnable"
        return None
```

### 5.3 AutoEval（自动评测）

```python
# forge/agent/trainer.py
class TrainerAgent:
    """自动化训练 + 评测循环"""

    def __init__(self, backend: TrainBackend, evaluator: Evaluator):
        self.backend = backend
        self.evaluator = evaluator

    def execute(self, experiment: Experiment) -> EvalReport:
        """执行完整的 训练 → checkpoint 选择 → 评测 流程"""
        job_id = self.backend.launch(experiment.train_config)
        self._wait_for_completion(job_id)

        # 对多个 checkpoint 评测，选最优
        checkpoints = self._list_checkpoints(job_id)
        best_report = None
        for ckpt in checkpoints:
            report = self.evaluator.run(model_path=ckpt)
            if best_report is None or report.geo_mean > best_report.geo_mean:
                best_report = report
        return best_report
```

### 5.4 SelfEvolution（模型自进化）

```python
# forge/agent/loop.py
class EvolutionLoop:
    """完整的自进化循环 — 对应论文中的 Agentic Crafting"""

    def __init__(self, strategist: StrategistAgent,
                 trainer: TrainerAgent,
                 data_agent: DataAgent):
        self.strategist = strategist
        self.trainer = trainer
        self.data_agent = data_agent

    def step(self) -> StepResult:
        """执行一轮进化"""
        # 1. 策略分析
        gap = self.strategist.analyze_gap()

        # 2. 提出实验
        experiment = self.strategist.propose_experiment(gap)

        # 3. 数据准备
        self.data_agent.prepare(experiment)

        # 4. 执行训练+评测
        report = self.trainer.execute(experiment)

        # 5. 记录结果
        self.strategist.tracker.record_result(experiment.id, report)

        # 6. 自我反思
        return StepResult(gap=gap, experiment=experiment, report=report)

    def run(self, max_steps: int = 10):
        """多轮自进化"""
        for i in range(max_steps):
            result = self.step()
            if result.report.geo_mean >= target_score:
                break
```

---

## 六、目标目录结构

```
forge/
  __init__.py
  __main__.py
  config.py                    # 全局配置（精简，仅 API keys + 路径）
  cli.py                       # Click CLI 入口（thin wrapper）

  # === Layer 0: Foundation ===
  env/                         # 环境抽象 (独立，零外部依赖)
    __init__.py
    base.py                    # EnvProtocol, EnvSpec
    registry.py                # EnvRegistry
    game.py                    # GAME 环境
    navworld.py                # NAVWORLD 环境
    liveweb.py                 # LIVEWEB 环境
    swe.py                     # SWE-INFINITE 环境

  prompt/                      # Prompt 编排 (独立，零外部依赖)
    __init__.py
    builder.py                 # PromptBuilder
    tools.py                   # ToolSchema 定义
    templates/                 # 模板文件
      game/
      navworld/
      liveweb/
      swe/

  training/                    # 训练后端 (独立，零外部依赖)
    __init__.py
    config.py                  # TrainConfig (声明式)
    backend.py                 # TrainBackend Protocol
    sft.py                     # SFT 训练方法
    dpo.py                     # DPO 训练方法
    model.py                   # 模型管理 (load/merge/upload)
    executor/                  # 执行器（计算资源管理）
      __init__.py
      local.py
      remote.py
      targon.py

  # === Layer 1: Application ===
  pipeline/                    # 业务流程 (依赖 Layer 0)
    __init__.py
    data.py                    # DataPipeline
    canonical.py               # 规范存储
    eval.py                    # Evaluator
    experiment.py              # ExperimentTracker
    generator/                 # 数据生成器（依赖 env + prompt）
      __init__.py
      base.py
      game.py
      navworld.py
      liveweb.py
      swe.py

  # === Layer 2: Agent ===
  agent/                       # 自动化编排 (依赖 Layer 0 + 1)
    __init__.py
    base.py                    # AgentProtocol
    strategist.py              # 策略 Agent
    trainer.py                 # 训练 Agent
    data_agent.py              # 数据 Agent
    loop.py                    # 自进化循环

  # === 基础设施 ===
  monitoring/                  # 排行榜监控
    leaderboard.py
```

---

## 七、迁移策略：渐进式重构

### 原则

1. **不停线重构** — 每一步都保持系统可运行，不中断正在进行的训练
2. **先抽接口，后迁实现** — 先定义 Protocol，然后逐步把现有代码迁入
3. **双写过渡** — 新旧代码共存，通过 feature flag 切换
4. **测试先行** — 每个环境写 3-5 个 golden test case 验证迁移正确性

### Phase 1: 抽象 Environment 层（最高优先级，~2天）

**目标**：把 6 个环境的验证/清洗逻辑从 `sft.py` 抽离到 `env/` 下。

```
Step 1: 创建 env/base.py + env/registry.py（接口定义）
Step 2: 把 sft.py::_clean_game() → env/game.py::GameEnv.clean_entry()
Step 3: 把 sft.py::_clean_navworld() → env/navworld.py::NavworldEnv.clean_entry()
Step 4: 重复 liveweb, swe, lgc, print
Step 5: 让 sft.py 的 ENV_CLEANERS 指向 EnvRegistry（兼容层）
Step 6: 验证 `forge data validate` 产出不变
```

### Phase 2: 抽象 Prompt Engine（~1天）

**目标**：把 prompt 模板从代码中抽离到文件。

```
Step 1: 创建 prompt/builder.py + prompt/templates/ 目录结构
Step 2: 把 navworld_prompts.py → prompt/templates/navworld/
Step 3: 各生成脚本中的 system prompt → prompt/templates/{env}/
Step 4: PromptBuilder 可从模板文件加载并填充变量
```

### Phase 3: 重构 Training Backend（~2天）

**目标**：把训练从"拼脚本字符串"改为声明式配置 + 可插拔执行器。

```
Step 1: TrainConfig 改为纯数据 dataclass（去掉 to_train_script()）
Step 2: 创建 training/sft.py 封装 SFT 训练逻辑
Step 3: 创建 executor/targon.py、executor/remote.py
Step 4: 把 compute/ 中的资源管理逻辑合入 executor/
Step 5: runner.py 瘦身为 thin dispatcher
```

### Phase 4: 构建 Application 层（~2天）

**目标**：DataPipeline、Evaluator、ExperimentTracker。

```
Step 1: pipeline/data.py 组合 EnvRegistry + CanonicalStore
Step 2: pipeline/eval.py 重构 eval_envs.py
Step 3: pipeline/experiment.py 替代 YAML 手动管理
Step 4: CLI 命令指向新 pipeline
```

### Phase 5: 构建 Agent 层（~3天，可迭代）

**目标**：自动化实验循环。

```
Step 1: agent/strategist.py — gap analysis 自动化
Step 2: agent/trainer.py — 训练+checkpoint选择自动化
Step 3: agent/data_agent.py — 数据准备自动化
Step 4: agent/loop.py — EvolutionLoop 主循环
```

---

## 八、接口隔离约束（强制执行）

为确保解耦，每层的 import 规则如下：

```python
# Layer 0: 只能 import stdlib + 自己的子模块
# forge/env/*.py     → import json, re, typing (NO forge.prompt, NO forge.training)
# forge/prompt/*.py  → import json, pathlib    (NO forge.env, NO forge.training)
# forge/training/*.py → import dataclasses     (NO forge.env, NO forge.prompt)

# Layer 1: 可以 import Layer 0
# forge/pipeline/*.py → import forge.env, forge.prompt, forge.training

# Layer 2: 可以 import Layer 0 + Layer 1
# forge/agent/*.py → import forge.pipeline, forge.env, forge.training
```

可通过 CI lint 规则（如 `import-linter`）自动检查违规。

---

## 九、与 ROCK/ROLL/iFlow 理念的关系

| 本项目模块 | 对应 ALE 生态 | 借鉴的关键设计 |
|-----------|-------------|--------------|
| `forge/env/` | ROCK | GEM Protocol (make/reset/step/close)，环境注册表 |
| `forge/prompt/` | — | 独立抽象，ROCK/ROLL 均未专门处理 |
| `forge/training/` | ROLL | 声明式 pipeline config，多后端支持 (DeepSpeed/Megatron) |
| `forge/pipeline/` | ROLL Pipeline | RLVR/Agentic/Distill Pipeline 的统一入口 |
| `forge/agent/` | iFlow | SubAgent 理念，agent 编排自动化 |
| EvolutionLoop | ALE 的 Agentic Crafting | 自动化 rollout → reward → train 循环 |

---

## 十、风险与应对

| 风险 | 应对 |
|------|------|
| 迁移过程中数据格式不兼容 | 每个环境写 golden test cases，CI 自动验证 |
| Agent 层过早自动化导致失控 | Phase 5 先做 human-in-the-loop，关键决策（如训练启动）需人工确认 |
| 计算资源管理与训练过度绑定 | executor/ 子包保持独立，可被训练以外的场景复用（如评测部署） |
| Prompt 模板化后灵活性下降 | 模板支持 Jinja2 级别的变量替换和条件逻辑 |
| 重构周期过长影响竞赛进度 | Phase 1-2 可立即产出价值，Phase 5 可后置 |

