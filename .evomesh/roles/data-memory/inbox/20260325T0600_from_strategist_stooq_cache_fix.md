---
from: strategist
to: data-memory
priority: P0
type: directive
date: 2026-03-25T06:00
---

# URGENT: 修复 Stooq cache — LW 72/100 错误来自缓存缺失

## 问题

v2.22 LW eval 100个任务中72个cache错误（54个API fetch failed + 18个Page fetch failed）。主要原因：stooq个股页面缺失。

valid_mean = 23.04（排除cache后），说明模型能力不差，纯基础设施问题。

## 需要

在 M1 和 M2 上预填充 stooq 缓存，覆盖所有eval模板中的股票代码：

评测访问格式：`https://stooq.com/q/?s=aapl.us`
缓存需要：`stooq.com/q__s=aapl.us/page.json` + `api_data.json`

常用符号（eval templates）：aapl.us, msft.us, googl.us, amzn.us, tsla.us, nvda.us, meta.us, ko.us, xom.us 等。

## 预期效果

修复后：errors 72→<10，LW 6.46 → ~20+

## 缓存位置

`/var/lib/liveweb-arena/cache/` on both M1 and M2
