#!/usr/bin/env python3
"""Split long MemoryGym trajectories into per-event training samples.

Each trajectory has redaction boundaries (memory summary + "OK.") between events.
Split at these boundaries so each event becomes a self-contained training sample:

  [system_prompt] + [memory_summary, "OK."] + [event_prompt] + [assistant_response(s)]

This ensures every sample fits in seq_len=32K and teaches the model the correct
eval-time behavior: see system + summary → act on event.

v4: balanced distribution, token length filtering, target count support.

Usage:
    python scripts/memorygym_split_events.py -i data/memorygym_v4.jsonl -o data/canonical/memorygym.jsonl --target 20000
    python scripts/memorygym_split_events.py -i data/memorygym_v4.jsonl -o /tmp/test.jsonl --target 5000 --balance
"""
import argparse
import json
from pathlib import Path
from random import Random


# Target distribution matching eval event proportions
# Eval: ~40% ingest + ~10% correction + ~40% question + ~10% noise
# But we weight question slightly higher since that's where scoring happens
TARGET_DISTRIBUTION = {
    "ingest": 0.30,       # Storage Breadth (30% of score)
    "correction": 0.20,   # Memory Maintenance (25% of score)
    "question": 0.45,     # Reasoning + Efficiency (45% of score) — highest loss signal
    "noise": 0.05,        # Teaches model to ignore irrelevant info (low loss per sample)
}

MAX_TOKENS = 30000  # Hard cap at 30K to stay well under 32K seq_len


def _est_tokens(messages: list[dict]) -> int:
    """Estimate token count (chars / 4)."""
    return sum(len(m.get("content", "")) for m in messages) // 4


def split_trajectory(entry: dict) -> list[dict]:
    """Split one trajectory into per-event samples."""
    messages = entry["messages"]
    if not messages:
        return []

    system_msg = messages[0]  # Always system prompt
    events: list[dict] = []

    # Find redaction boundaries: user message containing "Your memory contains"
    # or "Your memory is empty" followed by assistant "OK."
    boundaries = []
    for i, m in enumerate(messages):
        if (m["role"] == "assistant" and m["content"].strip() == "OK."
                and i > 0
                and messages[i-1]["role"] == "user"
                and ("Your memory contains" in messages[i-1].get("content", "")
                     or "Your memory is empty" in messages[i-1].get("content", ""))):
            boundaries.append(i)

    if not boundaries:
        return [entry]

    for k in range(len(boundaries)):
        if k == 0:
            start = 1
        else:
            start = boundaries[k-1] + 1

        end = boundaries[k] + 1

        event_msgs = messages[start:end]
        if not event_msgs:
            continue

        sample_msgs = [system_msg]

        if k > 0:
            prev_summary = messages[boundaries[k-1] - 1]
            prev_ok = messages[boundaries[k-1]]
            sample_msgs.append(prev_summary)
            sample_msgs.append(prev_ok)

        if len(event_msgs) >= 2:
            last_user = event_msgs[-2] if len(event_msgs) >= 2 else None
            last_asst = event_msgs[-1]
            if (last_asst.get("content", "").strip() == "OK."
                    and last_user
                    and ("Your memory contains" in last_user.get("content", "")
                         or "Your memory is empty" in last_user.get("content", ""))):
                event_content = event_msgs[:-2]
            else:
                event_content = event_msgs
        else:
            event_content = event_msgs

        if not event_content:
            continue

        sample_msgs.extend(event_content)

        # Determine event type
        first_user = next((m for m in event_content if m["role"] == "user"), None)
        event_type = "unknown"
        if first_user:
            content = first_user.get("content", "")
            if "[DOCUMENTS]" in content:
                event_type = "ingest"
            elif "[CORRECTION]" in content:
                event_type = "correction"
            elif "[QUESTION]" in content:
                event_type = "question"
            elif "[INFO]" in content:
                event_type = "noise"

        # Fix role: "Tool results:" messages should be role="tool" for ms-swift compat
        for msg in sample_msgs:
            if msg["role"] == "user" and msg["content"].startswith("Tool results:"):
                msg["role"] = "tool"

        # Merge consecutive same-role messages
        merged = [sample_msgs[0]]
        for msg in sample_msgs[1:]:
            if merged and msg["role"] == merged[-1]["role"]:
                merged[-1]["content"] += "\n\n---\n\n" + msg["content"]
            else:
                merged.append(msg)

        sample = {
            "messages": merged,
            "env": "MemoryGym",
            "source": entry.get("source", "hybrid"),
            "template": entry.get("template", ""),
            "seed": entry.get("seed", 0),
            "event_type": event_type,
            "event_idx": k,
            "total_events": len(boundaries),
        }
        events.append(sample)

    return events


def balance_samples(
    samples: list[dict],
    target: int,
    rng: Random,
    distribution: dict[str, float] | None = None,
) -> list[dict]:
    """Downsample/upsample to target count with balanced distribution.

    Returns exactly `target` samples with event types matching `distribution`.
    """
    dist = distribution or TARGET_DISTRIBUTION

    # Filter out over-length samples
    valid = [s for s in samples if _est_tokens(s["messages"]) <= MAX_TOKENS]
    dropped = len(samples) - len(valid)
    if dropped:
        print(f"  Dropped {dropped} samples exceeding {MAX_TOKENS} token limit")

    # Group by event type
    by_type: dict[str, list[dict]] = {}
    for s in valid:
        t = s["event_type"]
        by_type.setdefault(t, []).append(s)

    result = []
    for etype, frac in dist.items():
        pool = by_type.get(etype, [])
        needed = int(target * frac)
        if not pool:
            print(f"  WARNING: no {etype} samples available, need {needed}")
            continue
        rng.shuffle(pool)
        if len(pool) >= needed:
            result.extend(pool[:needed])
        else:
            # Upsample: repeat pool as needed
            repeats = needed // len(pool)
            remainder = needed % len(pool)
            for _ in range(repeats):
                result.extend(pool)
            result.extend(pool[:remainder])
            print(f"  {etype}: upsampled {len(pool)} → {needed} ({repeats+1}x)")

    # Fill remaining slots with highest-value type (question)
    shortfall = target - len(result)
    if shortfall > 0:
        questions = by_type.get("question", [])
        if questions:
            rng.shuffle(questions)
            extra = questions[:shortfall] if len(questions) >= shortfall else questions * (shortfall // len(questions) + 1)
            result.extend(extra[:shortfall])

    rng.shuffle(result)
    return result[:target]


def main():
    parser = argparse.ArgumentParser(
        description="Split MemoryGym trajectories into per-event samples")
    parser.add_argument("-i", "--input", required=True,
                        help="Input JSONL (full trajectories)")
    parser.add_argument("-o", "--output", required=True,
                        help="Output JSONL (per-event samples)")
    parser.add_argument("--target", type=int, default=0,
                        help="Target sample count (0 = keep all)")
    parser.add_argument("--balance", action="store_true",
                        help="Balance event type distribution")
    parser.add_argument("--shuffle-seed", type=int, default=42)
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    all_samples = []
    trajectories = [json.loads(l) for l in open(input_path)]

    for entry in trajectories:
        samples = split_trajectory(entry)
        all_samples.extend(samples)

    print(f"Split {len(trajectories)} trajectories → {len(all_samples)} event samples")

    # Raw distribution
    type_counts = {}
    for s in all_samples:
        t = s["event_type"]
        type_counts[t] = type_counts.get(t, 0) + 1
    print(f"\nRaw event type distribution:")
    for t, c in sorted(type_counts.items()):
        print(f"  {t}: {c} ({c/len(all_samples)*100:.1f}%)")

    # Balance if requested
    rng = Random(args.shuffle_seed)
    if args.target > 0 or args.balance:
        target = args.target if args.target > 0 else len(all_samples)
        all_samples = balance_samples(all_samples, target, rng)
        print(f"\nAfter balancing → {len(all_samples)} samples")
    else:
        rng.shuffle(all_samples)

    with open(output_path, "w") as f:
        for s in all_samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    # Final stats
    type_counts = {}
    token_lengths = []
    for s in all_samples:
        t = s["event_type"]
        type_counts[t] = type_counts.get(t, 0) + 1
        toks = _est_tokens(s["messages"])
        token_lengths.append(toks)

    token_lengths.sort()
    print(f"\nFinal distribution:")
    for t, c in sorted(type_counts.items()):
        print(f"  {t}: {c} ({c/len(all_samples)*100:.1f}%)")
    print(f"\nToken length (estimated):")
    print(f"  Median: {token_lengths[len(token_lengths)//2]:,}")
    print(f"  P90: {token_lengths[int(len(token_lengths)*0.9)]:,}")
    print(f"  P99: {token_lengths[int(len(token_lengths)*0.99)]:,}")
    print(f"  Max: {token_lengths[-1]:,}")
    print(f"  > 32K: {sum(1 for l in token_lengths if l > 32000)}")
    print(f"\n  Output: {output_path}")


if __name__ == "__main__":
    main()
