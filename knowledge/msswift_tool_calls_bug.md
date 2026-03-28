# ms-swift 不支持 OpenAI tool_calls 格式

基于最新代码分析（GitHub main 分支，版本 4.1.0.dev0，2026-03-28 拉取）。

## 结论

ms-swift **设计上不支持 OpenAI 标准 tool_calls 格式**。它有自己的 tool calling 数据格式，使用 `role: "tool_call"` 和 `role: "tool_response"` 代替 OpenAI 标准的 `assistant.tool_calls` 和 `role: "tool"`。

这不是版本问题或 bug——最新代码与 4.0.2 行为一致。

## 代码证据

### 证据 1：消息字段白名单删除 tool_calls

**文件**: `swift/dataset/preprocessor/core.py` → `_check_messages` 方法

```python
# https://github.com/modelscope/ms-swift/blob/main/swift/dataset/preprocessor/core.py
@staticmethod
def _check_messages(row: Dict[str, Any]) -> None:
    if 'messages' not in row:
        return
    messages = row['messages']
    assert len(messages) > 0, f'messages: {messages}'
    # fix swift/SlimOrca
    for message in messages:
        keys = set(message.keys()) - {'role', 'content', 'loss'}
        for key in keys:
            message.pop(key)                          # ← 删除 tool_calls, tool_call_id, name 等

    for message in messages:
        role, content = message['role'], message['content']
        assert role in {'system', 'user', 'tool_call', 'tool_response', 'tool', 'assistant'}, f'message: {message}'
        assert content is not None, f'message: {message}'  # ← content=None 触发 AssertionError
```

白名单只保留 `{'role', 'content', 'loss'}`，所有其他字段（包括 `tool_calls`, `tool_call_id`, `name`）被 `pop` 删除。随后 `assert content is not None` 拒绝 content 为 None 的消息。

OpenAI 格式中 assistant 发起 tool call 时 content 为 None：
```json
{"role": "assistant", "content": null, "tool_calls": [...]}
```
此消息先被删掉 `tool_calls`，然后因 `content is None` 触发 assert 失败。

### 证据 2：assert 失败后静默删除数据

**文件**: `swift/dataset/preprocessor/core.py` → `batched_preprocess` 方法

```python
def batched_preprocess(self, batched_row, *, strict, ignore_max_length_error):
    new_rows = []
    for row in rows:
        try:
            row = self.preprocess(row)
            if row is None:
                row = []
            if isinstance(row, dict):
                row = [row]
            for r in row:
                self._check_objects(r)
                self._check_rejected_response(r)
                self._check_messages(r)                    # ← 触发 assert
                self._cast_mm_data(r)
        except Exception as e:
            if strict:
                raise
            if isinstance(e, MaxLengthError) and ignore_max_length_error:
                pass
            elif self.traceback_limit is not None and self._traceback_counter < self.traceback_limit:
                import traceback
                logger.info(traceback.format_exc())
                logger.warning('👆👆👆There are errors in the dataset, the data will be deleted')
                self._traceback_counter += 1               # ← 只打印前 N 条警告
            row = []                                       # ← 之后静默删除，无任何日志
        new_rows += row
```

`traceback_limit` 默认 10，所以日志中只看到 10 条 "There are errors in the dataset" 警告，但实际被删除的数据远多于 10 条。

### 证据 3：ms-swift 的 tool calling 格式是 role-based

**文件**: `swift/template/base.py` → `_preprocess_function_call` 方法

```python
def _preprocess_function_call(self, inputs: StdTemplateInputs) -> None:
    agent_template = self.agent_template
    ...
    while i < len(messages):
        if messages[i]['role'] == 'tool_call':             # ← 期望 role="tool_call"，不是 tool_calls 字段
            i_start = i
            while i + 1 < len(messages) and messages[i + 1]['role'] == 'tool_call':
                i += 1
            tool_content = self.agent_template._format_tool_calls(messages[i_start:i + 1])
```

ms-swift 通过 `agent_template` 处理 tool calling，期望数据使用 `role: "tool_call"` 格式。

### 证据 4：官方文档确认格式

**文件**: `docs/source_en/Instruction/Agent-support.md`

```
the content section of messages where the role is 'tool_call' or 'tool_response/tool' must also be a JSON string.
```

```
The {"role": "tool_call", ...} part will automatically be converted into corresponding formats
of {"role": "assistant", ...} based on the agent_template.
```

## ms-swift 期望的数据格式

```json
{
  "tools": "[{\"type\": \"function\", \"function\": {\"name\": \"search\", ...}}]",
  "messages": [
    {"role": "user", "content": "搜索北京天气"},
    {"role": "tool_call", "content": "{\"name\": \"search\", \"arguments\": {\"city\": \"北京\"}}"},
    {"role": "tool_response", "content": "{\"result\": \"晴天\"}"},
    {"role": "assistant", "content": "北京晴天。"}
  ]
}
```

关键区别（vs OpenAI 格式）：
| | OpenAI 标准 | ms-swift |
|---|---|---|
| tool call | `role: "assistant"` + `tool_calls` 字段 | `role: "tool_call"` + `content` 是 JSON 字符串 |
| tool result | `role: "tool"` + `tool_call_id` | `role: "tool_response"` + `content` 是 JSON 字符串 |
| content | 可以是 `null` | **必须是字符串，不能是 null** |
| tools | JSON 列表 | **JSON 字符串** |
| 训练参数 | 无需额外参数 | 需要 `--agent_template qwen_en` |
