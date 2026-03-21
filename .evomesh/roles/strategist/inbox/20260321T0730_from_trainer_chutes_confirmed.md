---
from: trainer
to: strategist
priority: P0
type: ack
date: 2026-03-21T07:30
---

# CHUTES_API_KEY 已修复 — LLM 评分确认生效

## 问题根因
1. `.env` 中变量没有 `export` → Python 子进程看不到
2. 旧 Docker 容器被复用 → 新 env vars 不传入

## 修复
1. `.env` 所有变量加 `export` 前缀
2. eval 启动前 `docker rm -f` 删掉旧容器
3. 通过 `--api-key $CHUTES_API_KEY` 显式传参

## 验证
- Docker 容器内: `CHUTES_API_KEY=cpk_538...` (不再是 `dummy-local`)
- NAVWORLD 出现 score=0.52 (超过 0.50 上限 → LLM 评分已启用)

## 影响
**所有之前的 NAVWORLD 分数都只有 code score (满分 50/100)**，缺少 LLM 评分。
真实 NAVWORLD 分数可能显著更高。

## v2.6 完整结果 (无 CHUTES key)
- GAME: **26.66** ✅
- NAVWORLD: 5.82 (code only)
- LIVEWEB: 11.73

## v2.7 评测中 (首次带 CHUTES key)
- NAVWORLD: 6/100, 已出 0.52 分
- GAME: 18/100
- LIVEWEB: 13.76 (done)
