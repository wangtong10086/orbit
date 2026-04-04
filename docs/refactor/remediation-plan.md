# 修复与自测计划

本文档记录当前已经确认、但尚未消除的已知问题，以及修复时必须回跑的自测步骤。

## 已知问题

### RM1. training 测试依赖 `affinetes`

现象：

- `tests/test_training.py` 在 collection 阶段因缺少 `affinetes` 失败

原始失败命令：

```bash
pytest -q tests/test_training.py -q
```

修复方向可二选一：

1. 为训练测试建立可替代的本地 stub / fixture
2. 明确把该测试标记为需要外部依赖的集成测试

修复完成前必须回跑：

1. 原始 pytest 命令
2. 至少一个依赖 `scripts/eval_envs.py` 或训练 bundle 渲染的下游命令

## 自测纪律

任何修复都不能只说“附近单测绿了”。

必须至少回跑：

1. 原始失败命令
2. 一个直接依赖该修复的下游命令

否则修复不能视为完成。
