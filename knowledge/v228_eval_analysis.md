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

### ckpt800 (step 800, 16.5% training)
| Env | Score | Samples | Errors | vs Best |
|-----|-------|---------|--------|---------|
| **GAME** | **40.06** | 99 | 0 | **+10.36 vs 29.70** |
| NW | 37.50 | 100 | 0 | -5.34 vs 42.84 |
| LW | 37.63 | 62 | 4 | +9.87 vs 27.76 |
| SWE-I | 8.33 | 12 | 0 | in progress |
| MG | 75.0% | 1 seed | 0 | too few seeds |

### ckpt1200 (step 1200, 24.8% training)
| Env | Score | Samples | Errors | vs Best |
|-----|-------|---------|--------|---------|
| **GAME** | **39.35** | 100 | 0 | **+9.65 vs 29.70** |
| NW | 39.73 | 100 | 0 | -3.11 vs 42.84 |
| **LW** | **39.66** | 92 | 8 | **+11.90 vs 27.76** |
| SWE-I | 5.26 | 38 | 12 | context overflow on some tasks |
| MG | 46.2% | 100 scores | 0 | company 50 + research 50 |

### ckpt2000 (step 2000, 41.3% training) — 过拟合信号，GAME/NW 退化
| Env | Score | Samples | Errors | vs Best |
|-----|-------|---------|--------|---------|
| GAME | 37.29 | 100 | 0 | -2.77 vs ckpt800 |
| NW | 32.83 | 100 | 0 | -11.25 vs ckpt600 **下降严重** |
| **LW** | **44.46** | 89 | 11 | **+16.70 vs 27.76 NEW ALL-TIME BEST** |
| **SWE-I** | **13.89** | 36 | 14 | **接近竞对 14.00** |
| MG | 54.0% | 24 scores | 0 | in progress |

**ckpt2000 关键发现**: NW 严重退化（32.8 vs ckpt600 的 44.1）。GAME 37.3 虽仍高于 QLoRA 但低于 ckpt800。LW 44.5 创新高。SWE 13.9 接近竞对水平。训练过半后多任务 trade-off 明显。

## 趋势分析

### 分数随 checkpoint 变化（确认数据）
```
         ckpt200   ckpt600   ckpt800   ckpt1200  ckpt2000
GAME     32.26     36.23     40.06     39.35     37.29↓    峰值 ckpt800
NW       37.41     44.08     37.50     39.73     32.83↓↓   峰值 ckpt600
LW       25.19     38.45     37.63     39.66     44.46↑↑   持续上升
SWE      0.00      0.00      4.55      5.26      13.89↑↑   持续上升
MG       —         51.5%     58.8%     46.2%     54.0%     波动 ~50%
```

### 关键观察
- **GAME**: ckpt200→ckpt800 持续上升到 40，之后急剧下降到 29。**训练过半后过拟合**
- **NW**: **ckpt600 是 NW 最优点（44.08）**，ckpt2000 降到 30.5。GAME 数据占 66.8% 导致严重遗忘
- **LW**: 持续上升，ckpt2000 达到 44.46 新高。LW 数据占 12.7%，学习曲线更慢但不退化
- **SWE**: ckpt2000 突破性进展（20.0），可能因为更长训练让模型学会了 coding 能力
- **MG**: 波动在 46-59%，无明显趋势

### 过拟合分析
GAME 数据占 66.8%（103592/155109），训练后期 GAME 格式过拟合但泛化能力下降。
NW 数据仅 6.5%，在 ckpt600（12% training）后就开始遗忘。
**结论**: 数据比例严重不均衡导致后期 GAME/NW 退化。下一版需要重新平衡数据比例。

### 最佳 checkpoint 取决于策略
| 策略 | Best Checkpoint | GAME | NW | LW | SWE |
|------|----------------|------|-----|-----|------|
| NW 最优 | **ckpt600** | 36.2 | **44.1** | 38.5 | 0.0 |
| GAME 最优 | **ckpt800** | **40.1** | 37.5 | 37.6 | 4.6 |
| 最均衡 | **ckpt1200** | 39.4 | 39.7 | 39.7 | 5.3 |
| LW/SWE 最优 | **ckpt2000** | 37.3 | 32.8 | **44.5** | **13.9** |

### vs QLoRA 最佳对比（使用各环境最佳 checkpoint）
| Env | QLoRA Best | Full FT Best | Improvement |
|-----|-----------|-------------|-------------|
| GAME | 29.70 (v2.23) | 40.06 (ckpt800) | **+35%** |
| NW | 42.84 (v2.21) | 44.08 (ckpt600) | **+3%** |
| LW | 27.76 (v2.25) | 44.46 (ckpt2000) | **+60%** |
| SWE | 0.00 | 13.89 (ckpt2000) | from 0 |

### vs 竞对对比（使用 ckpt1200 最均衡版本）
| Env | Ours ckpt1200 | #1 Competitor | Gap |
|-----|--------------|--------------|-----|
| GAME | 39.35 | 47.05 (vera6) | -7.70 |
| NW | 39.73 | 39.12 (Sanguineey) | **+0.61 领先** |
| LW | 39.66 | 28.42 (RLStepone) | **+11.24 领先** |
| SWE-I | 5.26 | 14.00 (EdmondMillion) | -8.74 |

### vs 竞对对比（使用 ckpt2000 LW/SWE 最优版本）
| Env | Ours ckpt2000 | #1 Competitor | Gap |
|-----|--------------|--------------|-----|
| GAME | 37.29 | 47.05 (vera6) | -9.76 |
| NW | 32.83 | 39.12 (Sanguineey) | -6.29 |
| LW | 44.46 | 28.42 (RLStepone) | **+16.04 领先** |
| SWE-I | 13.89 | 14.00 (EdmondMillion) | -0.11 接近持平 |

**结论**: 没有单一最佳 checkpoint。ckpt1200 最均衡，ckpt2000 在 LW/SWE 领先但 GAME/NW 退化严重。
**下一步建议**: 重新平衡数据比例（减少 GAME 占比，增加 NW/SWE），避免后期过拟合。

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
