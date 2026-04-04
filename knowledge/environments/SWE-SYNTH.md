# SWE-SYNTH Environment — DEPRECATED

> Status: Reference note
> Authority: Non-normative
> Last reviewed: 2026-04-04
> Use this file for background and deep analysis, not as the primary source of truth.


> **Status**: Being replaced by SWE-Infinite. See `knowledge/environments/SWE-INFINITE.md`.

## Historical Data
- Canonical was 983 clean entries (think tags removed, trailing msgs fixed)
- DPO pairs: 258
- Binary scoring: 0 or 1 (pass/fail)
- Format: THOUGHT + single bash code block (same as SWE-Infinite)

## Why Deprecated
- SWE-SYNTH used synthetic bug injection — limited diversity
- SWE-Infinite mines real GitHub PRs — higher quality, more diverse
- Eval format stays the same (THOUGHT + bash), only task source changes

## See Instead
- `knowledge/environments/SWE-INFINITE.md` — current environment spec
- `repos/affine-swe-infinite/` — task generation pipeline
- `repos/affinetes/environments/SWE-INFINITE/` — evaluation environment
