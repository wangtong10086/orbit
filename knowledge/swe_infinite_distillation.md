# SWE-Infinite 蒸馏方案

> Status: Reference note
> Authority: Non-normative
> Last reviewed: 2026-04-04
> Use this file for background and deep analysis, not as the primary source of truth.


## 方法

真实 Docker 蒸馏（唯一可用方案，合成数据已验证无效）

```
私有 R2 池 → m2 docker pull/local build → GPT-5.4 agent → 验证测试 → score=1.0 → JSONL
```

## 运行方式

```bash
# 在 m2 (Targon) 上
ssh -p 22 wrk-2g5l02247zvp@ssh.deployments.targon.com
cd /root && export $(cat .env | xargs)
python3 -u swe_distill.py --task-file swe_private_task_list_v2.jsonl --output real_distill_v3.jsonl --resume
```

## 当前数据

- **38 条已验证** (Go 34, Ruby 3, Rust 1)
- 来源: public R2 (22) + private R2 (16), merged + deduped
- HF `monokoco/affine-sft-data/swe_infinite.jsonl` — 已同步
- Batch 在 val 运行中, hourly sync cron active
- Fix rate ~2-6%, 预计全量 1827 tasks 产出 ~40-50 条

## API + Docker 对策

| 问题 | 解决 |
|------|------|
| API 520/504 | 15x retry, 1800s timeout, 15-120s backoff |
| API 0-turn fail | 自动 re-queue 到 batch 末尾重跑 |
| Docker pull 失败 | 本地构建 (FROM base + git clone) |
| DockerHub 限流 | 预拉基础镜像 (golang/rust/python/ruby/node) |
| 重复采样 | source dedup + seen_ids tracking |
| 格式错误 | quality filter (THOUGHT check + bash block + submit marker) |

## 数据格式

匹配 `SWE-INFINITE/agents/config.yaml` 完整模板:
```json
{"messages": [...], "env": "SWE-INFINITE", "score": 1.0}
```
