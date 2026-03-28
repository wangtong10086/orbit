# ms-swift 不支持 OpenAI tool_calls 格式 — 需转换为 ms-swift 专用格式

## 结论

ms-swift（4.0.2 及最新 4.1.0.dev0）**不支持 OpenAI 标准 tool_calls 字段**。它有自己的 tool calling 格式：用 `role: "tool_call"` 代替 `assistant.tool_calls`。这不是 bug，是设计选择。最新代码同样如此。

**数据需要从 OpenAI 格式转换为 ms-swift 格式才能训练。**

## 影响

v2.28 训练 87391 条数据中：
- **43345 条包含 tool_calls + content=None 的 assistant 消息**
- 实际过滤 17168 条（其余被随机替换为其他样本）
- LW 100%, NW 100%, MG 81.2% 的 tool_calls 数据受影响
- 即使未被过滤的样本，tool_calls 字段也被删除 → **模型无法学习 tool calling 行为**

## 源码分析

### 问题代码位置

文件：`swift/dataset/preprocessor/core.py`

#### 问题 1：删除 tool_calls 字段（第 67-69 行）

```python
@staticmethod
def _check_messages(row: Dict[str, Any]) -> None:
    if 'messages' not in row:
        return
    messages = row['messages']
    assert len(messages) > 0, f'messages: {messages}'
    # fix swift/SlimOrca
    for message in messages:
        keys = set(message.keys()) - {'role', 'content', 'loss'}  # ← 只保留这3个字段
        for key in keys:
            message.pop(key)  # ← 删除 tool_calls, tool_call_id, name 等所有字段
```

**效果**：每条消息只保留 `role`, `content`, `loss`。OpenAI 标准的 `tool_calls`, `tool_call_id`, `name` 全部被删除。注释说 "fix swift/SlimOrca"，说明这是为了兼容特定数据集而加的逻辑，但误伤了标准 tool calling 格式。

#### 问题 2：assert content is not None（第 76-77 行）

```python
    for message in messages:
        role, content = message['role'], message['content']
        assert role in {'system', 'user', 'tool_call', 'tool_response', 'tool', 'assistant'}, f'message: {message}'
        assert content is not None, f'message: {message}'  # ← content=None 直接 assertion error
```

**效果**：OpenAI 标准的 tool calling 格式中，assistant 发起 tool call 时 content 通常为 None：
```json
{"role": "assistant", "content": null, "tool_calls": [{"id": "call_1", ...}]}
```
这条 assert 会直接失败。

### 过滤机制（第 167-197 行）

```python
def batched_preprocess(self, batched_row, *, strict, ignore_max_length_error):
    new_rows = []
    for row in rows:
        try:
            row = self.preprocess(row)
            ...
            self._check_messages(r)  # ← 触发上述 assert
        except Exception as e:
            if strict:
                raise
            ...
            logger.warning('👆👆👆There are errors in the dataset, the data will be deleted')
            self._traceback_counter += 1
            row = []  # ← 数据被删除（设为空列表）
        new_rows += row
```

**流程**：
1. `_check_messages` 先删掉 tool_calls 字段
2. 然后 assert content is not None 失败
3. 异常被 except 捕获
4. `row = []`（样本被删除）
5. 只打印前 `traceback_limit=10` 条警告（"👆👆👆There are errors"），之后静默删除

这解释了为什么日志中只有 10 条 "AssertionError: response_role: user" 警告，但实际过滤了 17168 条。

### 额外：运行时 DataLoader 的补偿机制（`swift/dataset/utils.py` 第 86-109 行）

```python
def __getitem__(self, idx):
    for i in range(self.n_try_fetch):
        data = self.dataset[idx]
        try:
            return self.encode_func(data, return_length=True)
        except Exception as e:
            if isinstance(e, MaxLengthError):
                continue  # 超长 → 随机换一条
```

预处理后幸存的样本（tool_calls 已被删除），在 DataLoader 阶段如果 encode 失败（MaxLengthError），会被随机替换为其他样本。这进一步掩盖了实际过滤量。

## 数据影响

| 环境 | 总数 | tool_calls+content=None | 影响率 |
|------|------|------------------------|--------|
| LIVEWEB | 17108 | 17108 | **100%** |
| NAVWORLD | 10006 | 10006 | **100%** |
| MemoryGym | 20000 | 16231 | **81.2%** |
| GAME | 38663 | 0 | 0% |
| SWE-I | 1614 | 0 | 0% |

## ms-swift 的 tool calling 格式

ms-swift 有专门的 agent 训练支持，但用**自己的格式**而非 OpenAI 标准：

### ms-swift 格式（支持）
```json
{
  "tools": "[{\"type\": \"function\", \"function\": {\"name\": \"search\", ...}}]",
  "messages": [
    {"role": "user", "content": "搜索北京天气"},
    {"role": "tool_call", "content": "{\"name\": \"search\", \"arguments\": {\"city\": \"北京\"}}"},
    {"role": "tool_call", "content": "{\"name\": \"search\", \"arguments\": {\"city\": \"上海\"}}"},
    {"role": "tool_response", "content": "{\"result\": \"晴天\"}"},
    {"role": "tool_response", "content": "{\"result\": \"多云\"}"},
    {"role": "assistant", "content": "北京晴天，上海多云。"}
  ]
}
```

关键区别：
- `role: "tool_call"` 代替 `role: "assistant"` + `tool_calls` 字段
- `role: "tool_response"` 代替 `role: "tool"`
- `tools` 字段是 **JSON 字符串**（不是列表）
- `content` 永远是字符串，不是 None
- ms-swift 通过 `agent_template`（如 `qwen_en`）自动转为模型需要的格式

### OpenAI 标准格式（我们的数据，不支持）
```json
{
  "tools": [{"type": "function", "function": {"name": "search", ...}}],
  "messages": [
    {"role": "user", "content": "搜索北京天气"},
    {"role": "assistant", "content": null, "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "search", "arguments": "{\"city\": \"北京\"}"}}]},
    {"role": "tool", "content": "{\"result\": \"晴天\"}", "tool_call_id": "call_1"},
    {"role": "assistant", "content": "北京晴天。"}
  ]
}
```

## 修复方案

### 方案 A：转换数据为 ms-swift 格式（推荐）
将 OpenAI 格式转为 ms-swift 格式：
- `assistant` + `tool_calls` → 拆成多个 `role: "tool_call"` 消息
- `role: "tool"` → `role: "tool_response"`
- `tools` 列表 → JSON 字符串
- 训练时加 `--agent_template qwen_en`
- 需要 data 角色提供转换脚本

### 方案 B：切换 TRL SFTTrainer
TRL 原生支持 OpenAI tool_calls，已验证 87391 条全部接受，0 过滤。

### 方案 C：Monkey-patch ms-swift
修改 `_check_messages` 保留 tool_calls 字段并允许 content=None。风险：可能破坏 ms-swift 后续的 template 处理逻辑。

## 验证

无论哪种方案，验证标准：`train_dataset num_rows` ≈ 输入行数（差 <1000）。
