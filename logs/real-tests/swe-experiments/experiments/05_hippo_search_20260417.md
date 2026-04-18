# 05. Hippo Search

实验目录：`logs/real-tests/swe-hippo-search-20260417/`  
原始记录：[README.txt](../../swe-hippo-search-20260417/README.txt)

## 目标

- 把 student 从 `Qwen/Qwen3-32B-TEE` 切到 `hippo-master/...`
- 检查是否能直接提升真实成功率

## 过程

- Chutes student:
  - `hippo-master/affine-17-5D7H7grKtvLJLy9GJWX8HEx2Z4swukjb9f8jAySR21UQEK9c`
- 继续跑真实扩搜索

## 结果

- 共 `12` 条真实 trajectories
- verified success：`0`

## 结论

- 只换模型，不足以直接采到成功轨迹
- collector/runtime/strategy 仍然是决定性因素
