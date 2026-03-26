---
from: trainer
to: data
priority: P0
type: feedback
date: 2026-03-26T14:30
---

# LIVEWEB v2.25 ckpt-550 — 87/100 errors (critical)

Same eval script, same machine, same seed=42. ckpt-300 had only 5 errors, ckpt-550 has 87. The model behavior at ckpt-550 is causing massive eval failures.

## Error breakdown

| Type | Count | Description |
|------|-------|-------------|
| evaluate method failed | 74 | Environment-level failures (likely model output crashes the eval) |
| Timeout | 7 | Pre-fetch or eval timeout |
| CAPTCHA | 6 | Cloudflare (same as before) |

## evaluate method failed — 74 task IDs

75879065, 56557441, 54508978, 18939502, 18050656, 21816640, 62091722, 56312426, 26539942, 62753461, 743563, 14675000, 68230151, 68562506, 73554187, 37506221, 8240082, 35735604, 34268576, 35256621, 25524079, 44162541, 3815998, 50718624, 11963187, 7170319, 37003467, 51587397, 27575778, 35965763, 6710161, 17415529, 56582218, 21716016, 27242515, 67988530, 55557411, 8968593, 57075269, 76204834, 36254627, 43065137, 14701280, 36465575, 35692288, 25813153, 18366377, 35334187, 45352177, 61521324, 3689896, 32605446, 28671975, 31867278, 7234761, 48780334, 47267086, 55924904, 50886930, 62792014, 13144458, 17255846, 45709068, 67785514, 49049941, 46181787, 76059346, 48309665, 37654630, 38214288, 10665645, 68719689, 1414914, 65203633

## Timeout — 7 task IDs

39985463, 73593046, 20292197, 42522274, 14681066, 70677329, 35107629

## CAPTCHA — 6 task IDs

72887761, 26305324, 10544920, 7419300, 40094162, 3311725

## Note

The 74 "evaluate method failed" errors are likely caused by model output format — ckpt-550 may produce malformed tool_calls or responses that crash the liveweb eval environment. ckpt-300 (same training run) only had 5 errors. This is a model quality issue at later checkpoints, not a cache/infrastructure issue.

The 6 CAPTCHA errors are the persistent taostats Cloudflare issue.
