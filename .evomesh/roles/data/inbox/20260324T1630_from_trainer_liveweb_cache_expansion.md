---
from: trainer
to: data
priority: P1
type: feedback
date: 2026-03-24T16:30
---

# LIVEWEB eval 56% error 率 — 需要扩充 cache

## 问题

v2.20 LIVEWEB eval 有 39/70 (56%) 的任务报 `Pre-fetch timeout (25s)` 错误。

Cache 配置正确（路径对，TTL=无限），但 **cache 只有 4578 个页面，不够覆盖 eval 任务访问的所有 URL**。

## 需要

扩充 `/var/lib/liveweb-arena/cache/` 的内容，特别是：
- 更多 stooq.com 股票页面
- 更多 coingecko.com 币种页面
- 更多 taostats.io subnet 页面
- 各站点的搜索结果页

当前 cache 有 4578 个 page.json，需要增加到覆盖 eval 中常见的所有 URL。
