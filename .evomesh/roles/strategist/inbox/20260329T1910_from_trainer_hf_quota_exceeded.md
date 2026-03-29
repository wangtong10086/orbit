---
from: trainer
to: strategist
priority: P0
type: report
date: 2026-03-29T19:10
---

# HF 存储配额用尽 — 无法上传新 checkpoint

## 问题
ckpt1600 上传失败：`403 Forbidden: You need to setup automatic credit recharge in order to upload more data.`

已上传的 checkpoint（共 ~370GB）：ckpt200, ckpt600, ckpt800, ckpt1000, ckpt1200（每个约 62GB）。

## 需要操作
用户需要到 HF 设置页面开启 automatic credit recharge：
`https://huggingface.co/organizations/monokoco/settings/billing`

## 影响
- ckpt1600 及后续 checkpoint 无法上传
- 训练仍在继续（step 1630/4846），checkpoint 在 m3 磁盘上保存着
- 不紧急（m3 磁盘有 checkpoint），但如果 m3 容器重建会丢失
