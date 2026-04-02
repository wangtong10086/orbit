# Adding Games

## 目标

新增一个 OpenSpiel 棋类任务时，优先复用：

- `BoardMuZeroNet`
- `SearchEngine`
- replay / runtime / online 训练主路径

只在真正需要 family 特化的地方加代码。

## 最小接入步骤

### 1. 注册 `GameSpec`

在 [`affine_registry.py`](../games/affine_registry.py) 中：

- 增加新的 `task_id`
- 增加新的 `GameSpec`
- 确认 `board_h / board_w / pad_h / pad_w / action_dim / baseline_*`

### 2. 动作编码

在 [`action_codecs.py`](../games/action_codecs.py) 中：

- 实现 `encode_dense`
- 实现 `decode_dense`
- 实现 `to_action_planes`
- 如有需要，实现 symmetry / transpose remap

### 3. 状态编码

在 [`encoders.py`](../games/encoders.py) 中：

- 新增对应 family encoder
- 在 `build_state_encoder()` 注册

建议：

- family 特化只放在这里
- 不要把棋盘解析散回 `adapters.py`

### 4. 配置文件

在 [`configs/`](../configs) 下增加对应 base config。

当前约定：

- 文件名使用 `variant_name.yaml`
- `test_configs.py` 会校验每个已注册变体都有配置文件

### 5. 测试

至少补：

- action codec roundtrip / symmetry
- encoder canonicalization
- model forward shape
- search smoke
- config presence

现有参考：

- [`test_action_codecs.py`](../tests/test_action_codecs.py)
- [`test_game_encoders.py`](../tests/test_game_encoders.py)
- [`test_model.py`](../tests/test_model.py)
- [`test_search_smoke.py`](../tests/test_search_smoke.py)
- [`test_configs.py`](../tests/test_configs.py)

## 什么时候需要改 runtime

通常不需要。

只有在下面情况才考虑改 runtime：

- 动作平面形状不再兼容当前 `to_action_planes`
- 搜索请求需要新的 inference lane
- replay sample schema 需要新增字段

如果只是新增一个 board game family，优先只改：

- `games/`
- `configs/`
- `tests/`

## Hex 的特殊点

Hex 当前默认要求：

- white-to-move 时进行 transpose canonicalization
- action remap 需要和 canonicalization 保持一致

这一点已经在 [`encoders.py`](../games/encoders.py) 和 [`action_codecs.py`](../games/action_codecs.py) 里有现成例子。

## 提交前检查

至少运行：

```bash
./.venv-all/bin/python -m compileall projects/openspiel_muzero_pt
./.venv-muzero/bin/python -m pytest -q projects/openspiel_muzero_pt/tests
```
