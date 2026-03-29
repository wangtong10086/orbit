# v2.28 155k Full FT — 评测结果分析

## 训练配置
- **Model**: Qwen3-32B Full Fine-Tuning (32.8B params, 100%)
- **Framework**: ms-swift 4.0.2 + DeepSpeed ZeRO-3 + CPU offload
- **Hardware**: 8x H200 (1144GB VRAM), m3
- **Data**: 155,109 entries (32 filtered, 0.02%)
- **Hyperparams**: lr=2e-5, batch=32 (1×4×8GPU), seq=32768, epochs=1
- **Total steps**: 4846, save_steps=200

## 数据分布
| Env | Count | % |
|-----|-------|---|
| GAME | 103,592 | 66.8% |
| MemoryGym | 20,000 | 12.9% |
| LIVEWEB | 19,776 | 12.7% |
| NAVWORLD | 10,006 | 6.5% |
| SWE-I | 1,735 | 1.1% |

## Checkpoint 评测结果

### ckpt200 (step 200, 4.1% training)
| Env | Score | Samples | Errors | vs Best |
|-----|-------|---------|--------|---------|
| GAME | 32.26 | 98 | 0 | +2.56 vs 29.70 |
| NW | 37.41 | 100 | 0 | from 0 → 37.41 |
| LW (new image) | 25.19 | 63 | 3 | -2.57 vs 27.76 |
| SWE-I | 0.00 | 5 | 5 | context overflow (40960) |
| MG | failed | 0 | 50 | chromadb missing |

**Key findings**: NW tool_call 格式转换修复成功，从 0 恢复到 37.41。LW 新镜像比旧镜像提升 4 倍（6.3→25.2）。

### ckpt600 (step 600, 12.4% training) — 三项历史新高
| Env | Score | Samples | Errors | vs Best | Delta |
|-----|-------|---------|--------|---------|-------|
| **GAME** | **36.23** | 100 | 0 | **+6.53** vs 29.70 | **NEW BEST** |
| **NW** | **44.08** | 100 | 0 | **+1.24** vs 42.84 | **NEW BEST** |
| **LW** | **38.45** | 85 | 15 | **+10.69** vs 27.76 | **NEW BEST** |
| SWE-I | 0.00 | 7 | 7 | context overflow (65536) | agent 上下文膨胀 |
| MG | 51.5% | 27/50 | 0 | 首次评测 | 运行中 |

### ckpt800 (step 800, 16.5% training) — 评测中
| Env | Score | Samples | Status |
|-----|-------|---------|--------|
| GAME | 44.33 | 21 | 运行中，需 50+ 样本 |
| NW | 37.48 | 23 | 运行中 |
| LW | 37.63 | 62 | ✅ 完成 |
| SWE-I | 0.00 | 2 | 不再 overflow，但得 0 |
| MG | — | seed 0 | 刚启动 |

## 趋势分析

### 分数随 checkpoint 变化
```
         ckpt200   ckpt600   ckpt800(partial)
GAME     32.26     36.23     44.33↑
NW       37.41     44.08     37.48↓(早期波动)
LW       25.19     38.45     37.63~
```

- **GAME**: 持续上升，ckpt800 可能突破 40+（竞对 46-47）
- **NW**: ckpt600 达到 44.08 后 ckpt800 暂时回落（样本太少需观察）
- **LW**: ckpt600 后基本稳定在 37-38

### vs QLoRA 最佳对比
| Env | QLoRA Best | Full FT ckpt600 | Improvement |
|-----|-----------|-----------------|-------------|
| GAME | 29.70 (v2.23) | 36.23 | +22% |
| NW | 42.84 (v2.21) | 44.08 | +3% |
| LW | 27.76 (v2.25) | 38.45 | +39% |

Full FT 在所有环境都显著优于 QLoRA。LW 提升最大（+39%）。

### vs 竞对对比 (ckpt600)
| Env | Ours | #1 Competitor | Gap |
|-----|------|--------------|-----|
| GAME | 36.23 | 47.05 (vera6) | -10.82 |
| NW | 44.08 | 39.12 (Sanguineey) | **+4.96 领先** |
| LW | 38.45 | 28.42 (RLStepone) | **+10.03 领先** |
| SWE-I | 0.00 | 14.00 (EdmondMillion) | -14.00 |

**NW 和 LW 大幅领先。GAME 是主要差距（-10.8）。SWE 是零分短板。**

## 关键修复验证

### NW tool_call 格式转换 ✅
- 问题：ms-swift `_check_messages` 删除 `tool_calls` 字段 → NW 10006 条全部无效 → 0 分
- 修复：`scripts/convert_openai_to_msswift.py` 自动转换 tool_calls → role: "tool_call"
- 验证：ckpt200 NW 37.41, ckpt600 NW 44.08 — 修复成功

### LW 数据重生成 ✅
- 问题：旧 LW 数据 multi-turn 格式被 ms-swift 过滤 100%
- 修复：data 角色用 3-msg 格式重新生成 19776 条
- 验证：ckpt200 LW 25.19, ckpt600 LW 38.45 — 修复成功

### LW 新评测镜像 ✅
- 问题：官方 `affinefoundation/liveweb-arena:latest` 评测逻辑过时
- 修复：从 `repos/liveweb-arena` 源码构建 `liveweb-arena:eval`
- 效果：同一模型 6.3 → 25.19（旧 vs 新镜像），4 倍提升

### SWE-INFINITE context overflow ❌ 部分解决
- 问题：SWE agent (miniswe) 多步交互积累历史，上下文膨胀到 42k-69k tokens
- sglang context-length=40960 → overflow; 65536 → 部分仍 overflow
- 根因：agent 没有上下文管理（截断/摘要）— 是 SWE agent 架构问题

## 未解决问题

1. **SWE-I 0 分**: agent 上下文管理缺失，需要 data-swe 角色修改 agent 架构
2. **MG 评测慢**: 每 seed ~5 min，50 seeds ~4h。ckpt600 当前 51.5%
3. **GAME 差距**: 与竞对差 ~10 分，需要更多/更好的 GAME 数据或更多训练步数
4. **最佳 checkpoint**: 待 ckpt800+ 评测完成后确定。ckpt600 目前是最佳已确认版本

## HF 模型存储
| Checkpoint | HF Repo | Private |
|-----------|---------|---------|
| ckpt200 | monokoco/affine-qwen3-32b-v2.28-155k-ckpt200 | ✅ |
| ckpt600 | monokoco/affine-qwen3-32b-v2.28-155k-ckpt600 | ✅ |
| ckpt800 | monokoco/affine-qwen3-32b-v2.28-155k-ckpt800 | ✅ |
| ckpt1000 | monokoco/affine-qwen3-32b-v2.28-155k-ckpt1000 | ✅ |
| ckpt1200 | monokoco/affine-qwen3-32b-v2.28-155k-ckpt1200 | ✅ |
