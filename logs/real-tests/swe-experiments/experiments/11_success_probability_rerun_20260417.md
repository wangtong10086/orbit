# 11. Success Probability Rerun

实验目录：`logs/real-tests/swe-success-prob-rerun-20260417/`  
原始记录：[README.txt](../../swe-success-prob-rerun-20260417/README.txt)

## 目标

- 引入更保守但更诚实的 realization 约束：
  - existence-aware shortlist
  - span-catalog realization
  - auto-verify
  - cheap verify funnel
  - 更宽 near-miss / O gate

## 过程

- 固定 task file，不再用漂移 numeric range
- 中途修掉 `_copy_text_from_container()` 读空文件的 runtime bug
- 原始失败命令和下游命令都重跑

## 结果

- `miniswe/rubocop`
  - 仍没进入真实 edit
  - 主要失败变成 `invalid_target`
- `codex/geopy`
  - 最明显改善
  - `2/2` trajectories 命中 `geopy/geocoders/here.py`
  - 至少 `1` 条进入 `cheap verify -> verify_fail`
  - `B=2 C=2 O=2 V=2`
- `codex/rails`
  - 从 `target_file does not exist` 收敛到 `invalid_span`

## 结论

- 这一轮证明 `codex` 在 Python 任务上并不是完全没机会
- runtime file-context / span-catalog 的正确性会直接决定实验结论
