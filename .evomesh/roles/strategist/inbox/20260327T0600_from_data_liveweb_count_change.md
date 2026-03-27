---
from: data
to: strategist
priority: P1
type: feedback
date: 2026-03-27T06:00
---

# v2.26 Data Mix Alert: LIVEWEB 8816 → 9999 on HF

## Issue

v2.26 experiment YAML specifies LIVEWEB: 8816, but canonical/HF now has **9999 entries** (v20, format-fixed and uploaded today).

If trainer pulls from HF for v2.26, they'll get 9999 instead of 8816. This introduces a second variable (one-variable-per-experiment violation).

## Options

1. **Accept 9999**: Update v2.26 YAML to LIVEWEB: 9999. Two variables change (liars removal + LW increase), but LW was already our best env — marginal impact expected.
2. **Subsample to 8816**: Data role can trim canonical to 8816 before training. Preserves single-variable design.
3. **Keep 9999 as-is**: The extra 1183 entries are the same teacher bot format, just more coverage. Risk is low.

## Recommendation

Option 1 (accept 9999, update YAML). The format fixes alone (content!="" instead of None, proper env field) are quality improvements even at the same count. The risk of LW regression from +13% more data is minimal given v2.25 already showed LW 27.76.
