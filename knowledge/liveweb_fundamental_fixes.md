# LIVEWEB 根本性问题及修改意见

> Status: Reference note
> Authority: Non-normative
> Last reviewed: 2026-04-04
> Use this file for background and deep analysis, not as the primary source of truth.


## 问题1（最关键）：Taostats表格在Playwright中不渲染

### 症状
- eval和训练数据中，taostats.io/subnets的accessibility_tree都显示 `No Rows To Show`
- 97.6%的taostats训练数据tree是空的
- 模型完全无法从tree中读取subnet数据 → taostats准确率仅9%
- taostats占评测约33%的题目（80/246个答案）

### 根因
taostats.io使用React + AG Grid虚拟表格。`_fetch_page()` 的等待逻辑不足：
1. `wait_until="domcontentloaded"` — DOM加载完但JS还没执行
2. `wait_for_load_state("networkidle", timeout=5000)` — 5秒太短，或数据通过WebSocket加载
3. `setup_page_for_cache()` 点击"ALL"但表格还没渲染 → 点击的是空表格

### 修改方案
**文件**: `liveweb_arena/core/cache.py` `_fetch_page()` 和 `plugins/taostats/taostats.py` `setup_page_for_cache()`

```python
# taostats.py: setup_page_for_cache()
async def setup_page_for_cache(self, page, url: str) -> None:
    if not self._is_list_page(url):
        return
    try:
        # 1. Wait for table data to actually render (not just DOM)
        await page.wait_for_selector(
            'div[role="row"], tr[role="row"], .ag-row, table tbody tr',
            timeout=15000
        )
        # 2. Then click ALL to show all rows
        all_button = page.locator('text="ALL"').first
        if await all_button.is_visible(timeout=3000):
            await all_button.click()
            # 3. Wait for ALL rows to load
            await page.wait_for_timeout(3000)
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except:
                pass
    except Exception:
        pass
```

**预期影响**: taostats树从空→有数据 → 模型可以读取 → 准确率9%→40%+ → **+25分**

## 问题2：Cache中stooq symbol大小写不一致

### 症状
- JSON API生成的cache条目symbol为大写 `AAPL.US`
- 模板和GT lookup用小写 `aapl.us`
- GT收集时lookup miss → null GT → score=0

### 已修复
- 已在m1+m2上将49个cache条目的symbol改为小写
- 不需要修改代码（官方CSV路径本身返回小写）
- 但如果重新生成cache需要确保用CSV不是JSON API

## 问题3：Teacher bot的think block质量

### 症状
- stop步骤think block说"The page contains the data needed to answer"（空洞）
- 没有引用accessibility_tree中的具体文本
- 没有计算步骤

### 已修复（training分支）
- commit `60c12c9`: fuzzy tree evidence匹配（0% → 209/259命中率）
- commit `c385bd3`: 消除空洞回退，引用tree内容

### 还需要的改进
1. **聚合计算的完整推理**: 对"百分比"、"排名"、"计数"类问题，think block应显示：
   - 列出所有数据点
   - 逐步计算: `36 losing / 64 total = 56.25%`
   - 不能跳到答案

2. **数据完整性检查**: stop步骤应列出哪些subtask已有数据、哪些还缺：
   - "answer1: ✓ AAPL price collected"
   - "answer2: ✗ EURUSD rate NOT collected — need to visit stooq"
   - 教模型不要提前停止

## 问题4：Eval时使用的sglang配置

### 症状
- 用 `--tool-call-parser qwen25` 无 `--reasoning-parser qwen3`
- `<think>` 块可能干扰tool call解析

### 建议
- 测试加 `--reasoning-parser qwen3` 看是否改善
- 或者在sglang启动时同时配置两个parser

## 分数提升预测

| 修复 | 当前影响 | 预期改善 | 累计 |
|------|---------|---------|------|
| 基线（cache已修复） | — | — | 14-17 |
| Stooq symbol大小写 | 已修复 | +15-20 | ~35 |
| **Taostats表格渲染** | **最关键** | **+15-20** | **~50** |
| Teacher think质量 | training分支已修 | +5 | ~55 |
| Reasoning parser | 未测试 | +2-5 | ~57-60 |

**结论：如果修复taostats表格渲染 + stooq大小写（已做），分数可以到50。**
