#!/usr/bin/env python3
"""Split long MemoryGym trajectories into per-event training samples.

Each trajectory has redaction boundaries (memory summary + "OK.") between events.
Split at these boundaries so each event becomes a self-contained training sample:

  [system_prompt] + [memory_summary, "OK."] + [event_prompt] + [assistant_response(s)]

This ensures every sample fits in seq_len=32K and teaches the model the correct
eval-time behavior: see system + summary → act on event.

Usage:
    python scripts/memorygym_split_events.py -i data/canonical/memorygym.jsonl -o data/canonical/memorygym_split.jsonl
"""
import argparse
import json
from pathlib import Path
from random import Random


def split_trajectory(entry: dict) -> list[dict]:
    """Split one trajectory into per-event samples."""
    messages = entry["messages"]
    if not messages:
        return []

    system_msg = messages[0]  # Always system prompt
    events: list[dict] = []

    # Find redaction boundaries: user message containing "Your memory contains" or "Your memory is empty"
    # followed by assistant "OK."
    # Each event = messages between two consecutive redaction boundaries

    # First, find all redaction boundary indices
    boundaries = []  # indices of the "OK." assistant messages after summaries
    for i, m in enumerate(messages):
        if (m["role"] == "assistant" and m["content"].strip() == "OK."
                and i > 0
                and messages[i-1]["role"] == "user"
                and ("Your memory contains" in messages[i-1].get("content", "")
                     or "Your memory is empty" in messages[i-1].get("content", ""))):
            boundaries.append(i)

    if not boundaries:
        # No redaction found — return as single entry
        return [entry]

    # Each event spans from after one boundary to the next boundary (inclusive)
    # First event: from message[1] to boundaries[0]
    # Subsequent events: from boundaries[k]+1 to boundaries[k+1]

    for k in range(len(boundaries)):
        if k == 0:
            start = 1  # skip system prompt
        else:
            start = boundaries[k-1] + 1

        end = boundaries[k] + 1  # inclusive of the "OK." message

        event_msgs = messages[start:end]
        if not event_msgs:
            continue

        # Build the sample: system + optional prior summary context + event
        sample_msgs = [system_msg]

        # If this is not the first event, the memory summary from the PREVIOUS
        # boundary provides the context. Include it.
        if k > 0:
            # Previous summary + OK = the last 2 messages of the previous boundary
            prev_summary = messages[boundaries[k-1] - 1]  # summary user msg
            prev_ok = messages[boundaries[k-1]]            # "OK." assistant msg
            sample_msgs.append(prev_summary)
            sample_msgs.append(prev_ok)

        # Add the event messages (up to but not including the trailing summary+OK
        # which belongs to this event's redaction)
        # The event content is: event_msgs minus the last 2 (summary + OK)
        if len(event_msgs) >= 2:
            # Last 2 are summary + OK (the redaction of THIS event)
            # Check if they really are
            last_user = event_msgs[-2] if len(event_msgs) >= 2 else None
            last_asst = event_msgs[-1]
            if (last_asst.get("content", "").strip() == "OK."
                    and last_user
                    and ("Your memory contains" in last_user.get("content", "")
                         or "Your memory is empty" in last_user.get("content", ""))):
                # Event content without trailing redaction
                event_content = event_msgs[:-2]
            else:
                event_content = event_msgs
        else:
            event_content = event_msgs

        if not event_content:
            continue

        sample_msgs.extend(event_content)

        # Determine event type from the first user message
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


def main():
    parser = argparse.ArgumentParser(
        description="Split MemoryGym trajectories into per-event samples")
    parser.add_argument("-i", "--input", required=True,
                        help="Input JSONL (full trajectories)")
    parser.add_argument("-o", "--output", required=True,
                        help="Output JSONL (per-event samples)")
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

    # Shuffle
    rng = Random(args.shuffle_seed)
    rng.shuffle(all_samples)

    with open(output_path, "w") as f:
        for s in all_samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    # Stats
    type_counts = {}
    token_lengths = []
    for s in all_samples:
        t = s["event_type"]
        type_counts[t] = type_counts.get(t, 0) + 1
        toks = sum(len(m.get("content", "")) for m in s["messages"]) // 4
        token_lengths.append(toks)

    token_lengths.sort()
    print(f"Split {len(trajectories)} trajectories → {len(all_samples)} event samples")
    print(f"  Output: {output_path}")
    print(f"\nEvent type distribution:")
    for t, c in sorted(type_counts.items()):
        print(f"  {t}: {c} ({c/len(all_samples)*100:.1f}%)")
    print(f"\nToken length (estimated):")
    print(f"  Median: {token_lengths[len(token_lengths)//2]:,}")
    print(f"  P90: {token_lengths[int(len(token_lengths)*0.9)]:,}")
    print(f"  P99: {token_lengths[int(len(token_lengths)*0.99)]:,}")
    print(f"  Max: {token_lengths[-1]:,}")
    print(f"  > 32K: {sum(1 for l in token_lengths if l > 32000)}")


if __name__ == "__main__":
    main()
