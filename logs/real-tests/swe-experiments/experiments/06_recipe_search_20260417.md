# 06. Recipe Search

实验目录：`logs/real-tests/swe-recipe-search-20260417/`  
原始记录：[README.txt](../../swe-recipe-search-20260417/README.txt)

## 目标

- 按固定 recipe 严格重跑：
  - 24 localization short rollout
  - 保留 4 个 localization state
  - 每个 state 2 个 patch plan
  - realize top 4
  - 1 次 rubric
  - 最多 2 次 repair

## 过程

- student: `hippo-master/...`
- 任务：`rubocop__rubocop-7660`

## 结果

- `mini-rubocop`: `0` success
- `codex-rubocop`: `0` success
- near-miss 也没有明显增加

## 结论

- 这条固定 recipe 本身并不能解决成功率问题
- 后来的 collector 复查还证明：当时部分“完全无效”的结论被 parser/runtime bug 污染过
