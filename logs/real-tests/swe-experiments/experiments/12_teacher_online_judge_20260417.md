# 12. Teacher Online Judge

实验目录：`logs/real-tests/swe-teacher-online-judge-20260417/`  
原始记录：[README.txt](../../swe-teacher-online-judge-20260417/README.txt)

## 目标

- 把 teacher 从“1 次 rubric + 离线 repair”升级到在线 judge / branch proposal
- 检查 teacher online 是否显著改变搜索漏斗

## 过程

- 固定三组任务：
  - `mini-rubocop`
  - `codex-geopy`
  - `codex-rails`
- 每组都跑：
  - `sample`
  - `relabel`
  - `build-buckets`

## 结果

- `mini-rubocop`
  - `changed_files=3/3`
  - `verify_fail=2/3`
  - `B=2 C=2 J=10 O=3 V=3`
- `codex-geopy`
  - 仍弱，但至少有 `B/C/J/O`
- `codex-rails`
  - teacher 把分支拉回正确文件
  - `changed_files=3/3`
  - `syntax_ok=3/3`
  - `verify_fail=2/3`
  - `B=2 C=2 J=16 O=3 V=3`

## 结论

- teacher online 确实显著改变了漏斗
- 但仍然没有 `A` 或 `T`
- teacher 更像“分叉器/裁剪器/纠偏器”，不是成功率万能解
