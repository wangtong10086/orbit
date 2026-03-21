# Data-QQR — Active Tasks

## Done This Session
- [x] Transport format fix (JSON objects → Chinese text strings, matching eval)
- [x] navworld_gen.py isinstance guards for transport string items
- [x] Chinese prompt alignment (system prompt + tool schema + user prompts)
- [x] V5 test generation (2 intercity entries, 100% success)
- [x] V5 full regeneration launched (3 batches, 7 types)

## In Progress
- [ ] V5 batch generation running (~1610 entries across 7 types)
- [ ] After V5 complete: QQR score all entries
- [ ] After QQR: replace canonical with V5 data
- [ ] After canonical: sync HF

## Next
- [ ] Send V5 status report to Strategist
- [ ] Analyze V5 per-type QQR scores vs V3 baseline
- [ ] Wait for v2.4+ eval with V5 data

## Backlog
- [ ] Expand city diversity (eval has 80+ cities, we use ~40)
- [ ] Add group_type/group_size variation to match eval's problem generator
- [ ] Investigate if adding eval's DifficultyProfile improves training
