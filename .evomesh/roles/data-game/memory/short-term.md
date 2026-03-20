# Short-term Memory

## Done (2026-03-20)
- Deep audit: 3316 canonical entries → found 1026 Chinese think, 545 no-think, 685 template thinks
- Fixed liars_dice bot dice parse bug (empty dice → correct parsing)
- Improved gin_rummy bot think diversity (1.4% → 87% unique)
- Installed pyspiel via pip --target=.pylibs
- Cleaned data → game_cleaned.jsonl (2445 entries, -871 removed)
- Generated v4 bot data: 775 entries (leduc 192, gin_rummy 294, goofspiel 94, liars_dice 195)
- Created game_data_clean.py and game_think_regen.py scripts
- Sent P1 inbox to Strategist (quality audit) and Data Agent (v4 data ready)

## In Progress
- Think regen running via GPT-5.4 (~1170 API calls, process PID 381)
- Output will be data/game_cleaned_regen.jsonl

## Blockers
- Anthropic API key 401 — using OpenAI gpt-5.4 as fallback

## Next Focus
- Wait for regen completion → verify quality
- Final quality audit of regen output
- Update knowledge/environments/GAME.md with new data status
