# Current Status

## Active Work

| Who | What | Started | ETA |
|-----|------|---------|-----|
| executor | Split navworld_gen.py (1020→3 files <500 each) | 2026-03-17 | done |

## GPU Resources

| Rental | Status | Usage |
|--------|--------|-------|
| rentals-w58tlzhv9xyh3dis | unknown | v11 training (last known) |

## Leaderboard

Last check: 2026-03-17
- #1: UID 45 (Infinite3214), weight ~0.508
- Us: ~#3, NAVWORLD 5.1 is bottleneck
- Threat: RLStepone (UID 242/248) — GAME 50+, NAVWORLD 25+, climbing fast

## Blockers

- None currently

## Recent Completions

- navworld_gen.py split: 1020L → amap_client.py (259L) + navworld_prompts.py (299L) + navworld_gen.py (487L)
- v10 eval complete: GAME 22.0, NAVWORLD 5.1
- v11 training launched with 3x NAVWORLD data (15273 entries)
- CLI refactored: cli.py split into cli_data/cli_train/cli_rental
- Knowledge base + experiment tracking system created
