# 07. Python Recipe

实验目录：`logs/real-tests/swe-python-recipe-20260417/`  
原始记录：[README.txt](../../swe-python-recipe-20260417/README.txt)

## 目标

- 用相同 recipe 测 Python 任务
- 看是否存在更容易进入正确轨迹的任务族

## 过程

- 候选任务：
  - `geopy__geopy-388`
  - `pre-commit__pre-commit-1299`
  - `vega__altair-1958`（baseline 坏，排除）

## 结果

- `mini-geopy`
  - `0` success
  - `0` near-miss
- `codex-geopy`
  - `0` success
  - `1` near-miss
  - `1` repair
  - `B/C` 非空
- `pre-commit`
  - Mini 卡在 `503`
  - Codex 卡在 `504`

## 记录到的额外情况

- teacher endpoint 返回：
  - Mini: `503`
  - Codex: `504`
