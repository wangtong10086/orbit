# SWE-Infinite 数据蒸馏方案 v2

## 实测数据分析（task 1-50）

### 成功特征 vs 失败特征

| 指标 | 成功 (8个) | 失败 (12个) |
|------|-----------|------------|
| 语言 | **100% Go** | Go/Ruby/Python/Rust 混合 |
| FAIL_TO_PASS 测试数 | avg 2.5 | avg 3.1 |
| PASS_TO_PASS 测试数 | avg 14.1 | avg 45.2 |
| problem statement 长度 | avg 244 chars | avg 333 chars |
| patch 大小 | avg 3008 chars | avg 4481 chars |
| 平均轮次 | 8.2 | 10.2 |

### 关键发现

1. **Go 垄断**: 8/8 成功全是 Go。Go 占 R2 池 56%（192/345），是最大语言
2. **小 patch 更容易**: 成功 patch avg 3K chars vs 失败 4.5K
3. **少 PASS_TO_PASS 更好**: 成功 avg 14 vs 失败 avg 45 — 测试套件越小，验证越容易通过
4. **API 不稳定**: ~30% 任务因 520/504 错误在 step 0 失败
5. **quality filter 过严**: task 26 (dubbo-go) score=1.0 但被 60K char limit 拦住

### 失败模式分类

| 模式 | 比例 | 根因 |
|------|------|------|
| API 失败 (520/504) | ~30% | 代理 API 不稳定 |
| 测试不通过 (wrong_answer) | ~50% | 模型修复质量不够 |
| 质量过滤 | ~5% | char limit 过严（已修复到 120K） |
| 无 patch 产生 | ~15% | 过早提交或格式错误 |

## 方案 v2: 分层策略

### 层 1: Go 优先（已验证可行）

**当前**: 继续跑 345 任务全量批次
- 预计产出: 192 Go 任务 × ~40% = ~77 条 Go 轨迹
- 非 Go 任务作为 bonus，不强求

### 层 2: 失败任务重试（提升产出）

对 score=0 但产生了 patch 的任务：
- **temperature=0.3** 重跑（当前 0.0 过于确定性）
- **换 Claude Sonnet** 重跑（不同模型可能解决不同 bug）
- 每个失败任务最多重试 2 次

预计额外产出: 50% 的 wrong_answer × 20% 重试成功 ≈ +15 条

### 层 3: API 失败恢复

对 api_fail 的任务：
- `--resume` 已处理（自动跳过已完成的，重跑失败的）
- 添加更强的重试: 5 次尝试 + 指数退避
- 换时间段跑（避开 API 高峰）

预计恢复: 30% api_fail × 80% 恢复 ≈ +20 条

### 层 4: 非 Go 语言专项（长期）

Ruby/Python/Rust 为什么失败？可能原因：
- **环境复杂度**: Ruby (bundle/gem), Python (pip/conda), Rust (cargo) 的依赖比 Go 更复杂
- **测试框架多样**: rspec/pytest/cargo test 输出格式各异
- **patch 大小**: 非 Go 的 patch 往往更大
- **GPT-5.4 偏好**: 可能对 Go 代码库更熟悉

解决方向：
- 用 Claude Sonnet/Opus 试非 Go 任务（可能对 Ruby/Python 更强）
- 分析具体失败原因（是修错了还是测试环境问题）

## 预计总产出

| 层 | 策略 | 预计产出 |
|----|------|----------|
| 1 | Go 优先（当前批次） | ~77 条 |
| 2 | 失败重试 (temp+model) | ~15 条 |
| 3 | API 恢复 | ~20 条 |
| 4 | 非 Go 专项 | ~10 条 |
| **总计** | | **~120 条** |

## 当前执行状态

- `scripts/swe_distill.py` 全量批次在 GPU 机器运行中
- 8 条已验证轨迹（全 Go，avg 8.2 turns, 26K chars）
- 当前 task 26/345
- 预计 ~14h 完成全量
- 自动 Docker prune 防止磁盘满

## 训练数据格式

已验证正确:
```json
{
  "messages": [
    {"role": "system", "content": "<eval system prompt>"},
    {"role": "user", "content": "<instance_template(problem_statement)>"},
    {"role": "assistant", "content": "THOUGHT: ...\n\n```bash\n...\n```"},
    {"role": "user", "content": "<returncode>0</returncode>\n<output>...</output>"},
    ...
  ],
  "env": "SWE-INFINITE",
  "score": 1.0
}
```

## 下一步行动

1. **当前**: 等待全量批次完成
2. **完成后**: 分析完整结果，更新产出预估
3. **层 2**: 对 wrong_answer 任务用 temperature=0.3 和 Claude Sonnet 重试
4. **集成**: `forge data ingest` → canonical → HF upload
5. **通知**: 数据就绪后发 inbox 给 Strategist
