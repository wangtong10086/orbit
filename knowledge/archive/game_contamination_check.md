# GAME Contamination Check — Base Model Knowledge Overlap

**Date**: 2026-03-18
**Status**: Design only (no execution yet)
**Inspiration**: DeepResearcher pass@10 methodology — measure what the base model already knows to identify true SFT value-add

---

## 1. Concept

"Contamination" in this context does not mean data leakage. It means **the base model (Qwen3-32B, no fine-tuning) already knows how to play this game correctly**. If the base model already picks the right action at a decision point, the SFT training sample at that point teaches nothing new.

**Core question**: Of the 2641 GAME canonical entries, how many are just reinforcing what Qwen3-32B already knows?

**Why this matters**:
- SFT budget is limited (~$9/run). Training on redundant samples wastes capacity.
- For Phase 3 GRPO, we need to identify entries where the model genuinely struggles — those are the high-value training targets.
- If base model already handles 60% of games correctly, our 2641 entries effectively shrink to ~1000 in terms of incremental learning signal.

---

## 2. Methodology

### 2.1 Per-Entry Contamination Scoring

For each entry in `data/canonical/game.jsonl`:

1. **Extract the conversation**: system prompt + sequence of (user, assistant) message pairs
2. **Replay the game state**: feed each user message to the base model, collect the base model's predicted action
3. **Compare**: base model action vs training data action at each decision point
4. **Score**: `contamination_rate = matching_actions / total_actions` per entry

### 2.2 Scoring Levels

| Contamination Rate | Label | Meaning |
|---|---|---|
| 0.0 - 0.3 | LOW | Base model struggles here — high SFT value |
| 0.3 - 0.7 | MEDIUM | Partial overlap — some value |
| 0.7 - 1.0 | HIGH | Base model already knows this — low SFT value |

### 2.3 What Counts as a "Match"

The base model's action matches the training action if:
- **Exact match**: base model outputs the same action ID (e.g., both say `3`)
- **Functional match**: both actions map to the same OpenSpiel action string (handles formatting differences)

The base model response is extracted by:
1. Stripping any `<think>...</think>` tags from the response
2. Parsing the first integer found in the remaining text
3. If no valid integer found, score that turn as non-matching

### 2.4 Game-Level Aggregation

After scoring all entries, aggregate by game:

```
Per game:
  - mean contamination rate
  - % of entries with contamination >= 0.7 (high overlap)
  - % of entries with contamination <= 0.3 (high value)
```

Current game distribution in canonical (2641 total):
- goofspiel: 1050
- gin_rummy: 505
- leduc_poker: 428
- liars_dice: 333
- hex: 190
- clobber: 123
- othello: 12

**Hypothesis**: Leduc poker (simple, well-documented game) will show highest contamination. Hex and clobber (niche games) will show lowest.

---

## 3. Implementation Plan

### 3.1 Pseudocode

```python
#!/usr/bin/env python3
"""GAME contamination check — measure base model overlap with training data."""

import json
import re
import asyncio
from openai import AsyncOpenAI

# Config
BASE_URL = "http://127.0.0.1:30000/v1"  # sglang endpoint
MODEL = "Qwen/Qwen3-32B"
CANONICAL = "data/canonical/game.jsonl"
OUTPUT = "data/game_contamination_scores.jsonl"
CONCURRENCY = 4
TEMPERATURE = 0.0  # deterministic for contamination check

client = AsyncOpenAI(base_url=BASE_URL, api_key="none")
semaphore = asyncio.Semaphore(CONCURRENCY)

def extract_action(response_text: str) -> int | None:
    """Extract action ID from model response, stripping think tags."""
    # Remove <think>...</think> blocks
    cleaned = re.sub(r'<think>.*?</think>', '', response_text, flags=re.DOTALL)
    cleaned = cleaned.strip()
    # Find first integer
    match = re.search(r'\d+', cleaned)
    return int(match.group()) if match else None

async def check_entry(entry: dict) -> dict:
    """Check one training entry for base model contamination."""
    messages = entry["messages"]
    system_msg = messages[0]  # {"role": "system", "content": ...}

    total_turns = 0
    matching_turns = 0
    turn_details = []

    # Walk through conversation: user messages are prompts, assistant messages are gold actions
    conversation_so_far = [system_msg]

    for i in range(1, len(messages), 2):
        if i + 1 >= len(messages):
            break
        user_msg = messages[i]    # {"role": "user", "content": ...}
        gold_msg = messages[i+1]  # {"role": "assistant", "content": ...}

        # Extract gold action
        gold_action = extract_action(gold_msg["content"])
        if gold_action is None:
            continue

        # Query base model with conversation history up to this point
        conversation_so_far.append(user_msg)

        async with semaphore:
            try:
                resp = await client.chat.completions.create(
                    model=MODEL,
                    messages=conversation_so_far,
                    temperature=TEMPERATURE,
                    max_tokens=512,
                )
                base_response = resp.choices[0].message.content
                base_action = extract_action(base_response)
            except Exception as e:
                base_action = None

        matched = (base_action == gold_action)
        total_turns += 1
        if matched:
            matching_turns += 1

        turn_details.append({
            "turn": total_turns,
            "gold": gold_action,
            "base": base_action,
            "matched": matched,
        })

        # Add gold response to conversation history (maintain context)
        conversation_so_far.append(gold_msg)

    contamination_rate = matching_turns / total_turns if total_turns > 0 else 0.0

    return {
        "task_id": entry.get("task_id"),
        "game": entry.get("game"),
        "total_turns": total_turns,
        "matching_turns": matching_turns,
        "contamination_rate": round(contamination_rate, 3),
        "turn_details": turn_details,
    }

async def main():
    # Load canonical data
    entries = []
    with open(CANONICAL) as f:
        for line in f:
            entries.append(json.loads(line))

    print(f"Checking {len(entries)} entries...")

    # Process all entries
    results = await asyncio.gather(*[check_entry(e) for e in entries])

    # Write results
    with open(OUTPUT, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    # Summary
    by_game = {}
    for r in results:
        g = r["game"]
        if g not in by_game:
            by_game[g] = []
        by_game[g].append(r["contamination_rate"])

    print("\n=== Contamination Summary ===")
    for game, rates in sorted(by_game.items()):
        avg = sum(rates) / len(rates)
        high = sum(1 for r in rates if r >= 0.7) / len(rates) * 100
        low = sum(1 for r in rates if r <= 0.3) / len(rates) * 100
        print(f"{game:15s}: avg={avg:.2f}  high_overlap={high:.0f}%  high_value={low:.0f}%  n={len(rates)}")

if __name__ == "__main__":
    asyncio.run(main())
```

### 3.2 Key Design Decisions

**Conversation replay vs independent prompts**: We replay the full conversation, adding the gold assistant response to history before querying the next turn. This matches how the eval environment works — the model sees its own prior answers. Using the gold response (not the base model's response) keeps the game state consistent with the training data.

**Temperature 0.0**: We want deterministic answers to measure knowledge overlap. The eval uses temperature=0.7, but for contamination checking we care about "does the model know this?" not "could it randomly get it right?"

**Single pass (not pass@k)**: Unlike DeepResearcher which uses pass@10, we use pass@1 with temperature=0. Rationale: for games, the action space is discrete and small. If the model knows the right action at temp=0, it knows it. pass@k is more useful for open-ended generation where there are many valid approaches.

### 3.3 Resource Requirements

| Resource | Requirement |
|---|---|
| GPU | 1x A100 80GB (or current rental) |
| Model serving | sglang with Qwen3-32B base (NOT fine-tuned), --tp 4 |
| Entries | 2641 |
| Avg turns per entry | ~10 (goofspiel ~11, leduc ~2.5, gin_rummy ~60) |
| Total inferences | ~26,000 |
| Per-inference latency | ~1s with sglang (512 max tokens, short context) |
| Concurrency | 4 (limited by sglang throughput) |
| Estimated wall time | ~1.8 hours |
| Estimated cost | $0 incremental (uses existing rental GPU) |

### 3.4 When to Run

- **Prerequisite**: v2 training must be complete (GPU freed)
- **Sequence**: deploy base Qwen3-32B via sglang -> run contamination check -> analyze results -> inform Phase 3 data strategy
- **Command sequence**:
  ```bash
  forge remote -m m1 kill all
  forge remote -m m1 exec "..."  # start sglang
  # wait for sglang ready
  python3 scripts/game_contamination_check.py
  ```

### 3.5 Infrastructure Reuse

The script reuses the same patterns as `scripts/game_bot_gen.py`:
- Same JSONL format for canonical data (`messages` array with system/user/assistant turns)
- Same action extraction logic (parse integer from response)
- Same OpenSpiel game vocabulary (action IDs are integers)

No dependency on OpenSpiel or pyspiel — the contamination check only needs the training data conversations, not the game engine. The game state is already encoded in the user messages.

---

## 4. Expected Outcomes

### 4.1 Per-Game Contamination Rates

| Game | Expected Contamination | Rationale |
|---|---|---|
| leduc_poker | HIGH (60-80%) | Extremely simple game (3 cards, 2 rounds). Well-studied in game theory literature. Base model likely knows GTO-adjacent play. |
| goofspiel | MEDIUM (30-50%) | Bid-matching heuristic is straightforward. Base model may know "bid high for high prizes" but miss resource management. |
| liars_dice | MEDIUM (30-50%) | Common game but requires probabilistic reasoning about hidden information. |
| gin_rummy | LOW-MEDIUM (20-40%) | Complex card game with many state variables. Current bot data is weak anyway (1.8% win rate). |
| hex | LOW (10-30%) | Niche board game. Requires spatial reasoning that LLMs typically struggle with. |
| clobber | LOW (10-20%) | Obscure game. Unlikely to be in pretraining data. |
| othello | LOW-MEDIUM (20-40%) | Well-known game but board state reasoning is hard for LLMs. Only 12 entries anyway. |

### 4.2 Difficulty-Adjusted Contamination

Cross-reference contamination rate with game complexity:
- **Turns per entry**: more turns = more chances to diverge = lower contamination expected
- **Action space size**: larger action space = harder to guess correctly
- **Win rate in training data**: entries from games with lower win rates may be harder

Expected finding: short simple games (leduc poker, 2-3 turns) will show much higher contamination than long complex games (gin rummy, 60+ turns), but gin rummy contamination is misleading because the training data itself is low quality.

### 4.3 Output Artifacts

1. `data/game_contamination_scores.jsonl` — per-entry scores with turn-level detail
2. Summary table by game (printed to stdout, captured in experiment notes)
3. Filtered dataset recommendations: which entries to keep, which to drop

---

## 5. How to Use Results

### 5.1 Phase 3 GRPO Focus

GRPO (Group Relative Policy Optimization) benefits most from examples where the model has room to improve. Use contamination scores to:

- **GRPO candidates**: entries with contamination < 0.3 (model genuinely struggles)
- **SFT-only candidates**: entries with contamination 0.3-0.7 (partial knowledge, SFT can fill gaps)
- **Drop candidates**: entries with contamination > 0.7 (model already knows this)

### 5.2 Data Efficiency

If we find e.g. 40% of entries are high-contamination:
- Removing them reduces training set from 2641 to ~1585 GAME entries
- Faster training (fewer steps), same effective learning signal
- Can backfill with harder examples (new game configurations, adversarial setups)

### 5.3 Cross-Reference with Existing Analysis

Combine with `game_v3_quality_analysis.md` findings:
- Gin rummy already flagged as broken (single-template thinking, 1.8% win rate) — contamination check may confirm this data is worthless from both quality AND novelty perspectives
- Goofspiel "bid == prize" strategy may show high contamination if base model knows this heuristic — confirming the "one-dimensional strategy" concern
- Leduc poker "never folds" problem: if base model also never folds, contamination will be high AND the training data teaches the same bad habit

### 5.4 Strategic Implications

| Contamination Result | Action |
|---|---|
| Overall > 50% | SFT plateau likely. Prioritize GRPO/DPO over more SFT data. |
| Game-specific spikes | Drop high-contamination games from SFT mix, focus GRPO on them. |
| Uniform low contamination | SFT data is genuinely valuable. Focus on quality improvements (better thinking, diverse strategies). |
| Contamination correlates with eval scores | Confirms that base model knowledge = easy games. Hard games need targeted data. |

---

## 6. Limitations and Caveats

1. **Gold-response replay bias**: By feeding gold assistant responses in the conversation history, we test "does the model know the right action given the correct prior context?" In eval, the model uses its own prior responses, which may diverge. This means contamination scores are an upper bound on real-world overlap.

2. **Temperature sensitivity**: Using temp=0 measures peak capability. At eval temp=0.7, the model may not consistently pick the action it "knows" at temp=0. True overlap during eval is likely lower.

3. **Action-only comparison**: We only compare action IDs, not reasoning quality. A base model might pick the right action for the wrong reason. SFT thinking templates still add value even when the action matches.

4. **Not a substitute for eval**: Contamination checking measures knowledge overlap, not model quality. Even high-contamination entries may contribute to training by reinforcing correct behavior or teaching the right output format.
