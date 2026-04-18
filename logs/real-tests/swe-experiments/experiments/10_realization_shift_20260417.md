# 10. Realization Shift

实验目录：`logs/real-tests/swe-realization-shift-20260417/`  
原始记录：[README.txt](../../swe-realization-shift-20260417/README.txt)

## 目标

- 把预算重点从“继续找”转到“更强 realization”
- 验证 host-side patch IO、plan retention、replacement decode 等修复后的真实表现

## 过程

- 修：
  - `_collect_patch_plans()` 只保留最后一个 plan
  - host-side patch/context IO
  - `\\n` replacement decode
  - partial JSON fallback
- 重新跑真实 sample / relabel / build

## 结果

- `miniswe/rubocop`
  - 真实执行到目标文件
  - `2/2` trajectories 命中 `lib/rubocop/cop/style/block_delimiters.rb`
  - 多步 `Syntax OK`
  - 最终停在 `quality_fail`
- `codex/rails`
  - rubric 已能指向正确源文件
  - 但 student 仍然反复给不存在文件或非法 span

## 结论

- `miniswe` 的 edit rate 和 syntax pass 明显变好
- `codex` 的主要问题更像定位/span 粒度，而不再主要是 collector 吞轨迹
