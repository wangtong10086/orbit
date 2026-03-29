# LIVEWEB Teacher Bot Bugs (需官方修复)

> 发现日期: 2026-03-29
> 代码库: liveweb-arena (training branch)
> 影响: 数据生成质量和覆盖率

---

## Bug 1: Composite 生成包含 disabled 插件

**位置**: `liveweb_arena/training/teacher/generator.py` — `_supported_templates_by_plugin()`

**现象**: 该方法返回所有 57 个注册模板，包括已在评测中禁用的插件 (openmeteo, openlibrary, arxiv)。composite 生成时随机选取所有模板，导致 95% 的 composite 数据包含 disabled 插件子任务。(weather 已永久禁用，不需要关注)

**影响**: 模型学习访问评测中不存在的网站 (openlibrary.org, arxiv.org, open-meteo.com)，浪费训练容量。

**修复建议**:
- 方案 A: `teacher_generate.py` 加 `--plugins` 参数，只从指定插件生成
- 方案 B: `_supported_templates_by_plugin()` 接受 `exclude_plugins` 参数

---

## Bug 2: assistant 消息 content=null

**位置**: `liveweb_arena/training/teacher/generator.py:418` — `_assistant_message()`

```python
return {
    "role": "assistant",
    "content": None,  # ← Bug: 应为 ""
    "tool_calls": [...]
}
```

**现象**: Qwen3 的 `apply_chat_template` 对 `content=None` 报错。

**影响**: 所有训练数据需要后处理 `None → ""`，否则无法用于 Qwen3 训练。

**修复**: 将 `"content": None` 改为 `"content": ""`。

---

## Bug 3: 输出缺少训练必需的顶层字段

**位置**: `liveweb_arena/training/formats.py:38` — `build_teacher_step_record()`

**现象**: 输出结构为:
```json
{
  "messages": [...],
  "metadata": {"score": 1.0, "source": "teacher_v2", ...}
}
```

缺少训练框架要求的顶层字段:
- `env`: 环境标识 (应为 `"LIVEWEB"`)
- `score`: 质量分数 (当前嵌套在 metadata 里)
- `tools`: 工具定义列表 (ms-swift 需要此字段传给 `apply_chat_template`)

**影响**: 所有数据需要后处理添加这三个字段。

**修复**: 在 `build_teacher_step_record` 返回值中直接包含 `env`, `score`, `tools` 顶层字段。

---

## Bug 4: Stooq 插件硬编码缓存路径

**位置**: `liveweb_arena/plugins/stooq/api_client.py:285`

```python
cache_dir = os.environ.get("LIVEWEB_CACHE_DIR", "/var/lib/liveweb-arena/cache")
```

**调用链**:
1. `TeacherGenerator(cache_dir="/tmp/lw_cache/cache")` — 传入自定义缓存路径
2. composite 生成 → `TaskManager.generate_composite_task()` → `plugin.initialize()`
3. stooq `initialize()` → `initialize_cache()` → 读 `LIVEWEB_CACHE_DIR` 环境变量
4. 环境变量未设置 → 使用默认值 `/var/lib/liveweb-arena/cache`
5. `mkdir -p /var/lib/liveweb-arena/cache/_plugin_init` → **PermissionError**

**现象**: `TeacherGenerator` 接受 `cache_dir` 参数但不传递给插件的 `initialize_cache()`。所有包含 stooq 的 composite 在非默认路径环境下全部失败。其他插件无此问题（不需要 `initialize_cache`）。

**影响**: stooq 在数据集中仅 408/19776 (2%)，远低于其他 4 个插件的 ~24%。

**修复建议**:
- 方案 A: `TeacherGenerator.__init__` 中设置 `os.environ["LIVEWEB_CACHE_DIR"] = str(cache_dir)`
- 方案 B: `initialize_cache()` 接受 `cache_dir` 参数而非只读环境变量
- 方案 C: `TaskManager.generate_composite_task()` 将 cache_dir 传递给 `plugin.initialize(cache_dir=...)`

---

## 严重程度

| Bug | 严重程度 | 可绕过 |
|-----|---------|--------|
| Bug 1 (disabled 插件) | **高** | 是 — 手动过滤模板列表 |
| Bug 2 (content=null) | 中 | 是 — 后处理 None→"" |
| Bug 3 (缺顶层字段) | 中 | 是 — 后处理添加字段 |
| Bug 4 (stooq 路径) | **高** | 部分 — 设 LIVEWEB_CACHE_DIR 环境变量，但仍需完整缓存 |

Bug 1 和 4 直接影响数据质量，无法完全通过后处理绕过。
