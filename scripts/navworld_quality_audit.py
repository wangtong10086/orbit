"""Score all NAVWORLD canonical entries using the QQR code scorer.

Extracts tool traces and final plans from SFT conversation format,
runs the code-only scorer (IC + Completeness + diversity + fabrication),
and outputs per-entry scores for quality analysis.

Usage:
    python3 scripts/navworld_quality_audit.py [--threshold 20] [--remove-below 15]
"""

import asyncio
import json
import re
import sys
import os
from pathlib import Path
from collections import defaultdict

# Add affinetes to path for scorer imports
sys.path.insert(0, str(Path(__file__).parent.parent / "repos" / "affinetes" / "environments" / "qqr"))

from scorer import TravelScorer, ScoreBreakdown
from config import PROBLEM_TYPES


def extract_scoring_inputs(entry: dict) -> dict:
    """Extract raw_output, tool_trace, and problem info from SFT conversation."""
    msgs = entry.get("messages", [])
    ptype = entry.get("problem_type", "intercity")

    # Extract final plan (last assistant message without tool_calls)
    raw_output = ""
    for msg in reversed(msgs):
        if msg.get("role") == "assistant" and msg.get("content") and not msg.get("tool_calls"):
            raw_output = msg["content"]
            break

    # Extract tool trace: list of {tool, args, result}
    tool_trace = []
    pending_calls = []

    for msg in msgs:
        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                fn = tc.get("function", {})
                pending_calls.append({
                    "id": tc.get("id", ""),
                    "name": fn.get("name", ""),
                    "arguments": fn.get("arguments", "{}"),
                })
        elif msg.get("role") == "tool":
            content = msg.get("content", "")
            # Match tool result to pending call
            call_id = msg.get("tool_call_id", "")
            matched_name = "unknown"
            matched_args = "{}"
            for pc in pending_calls:
                if pc["id"] == call_id:
                    matched_name = pc["name"]
                    matched_args = pc["arguments"]
                    pending_calls.remove(pc)
                    break
                elif not call_id and pending_calls:
                    # Fallback: match by order
                    matched_name = pending_calls[0]["name"]
                    matched_args = pending_calls[0]["arguments"]
                    pending_calls.pop(0)
                    break

            tool_trace.append({
                "tool": matched_name,
                "args": matched_args if isinstance(matched_args, str) else json.dumps(matched_args, ensure_ascii=False),
                "result": content,
                "success": True,
            })

    # Extract user prompt for problem context
    user_prompt = ""
    for msg in msgs:
        if msg.get("role") == "user":
            user_prompt = msg.get("content", "")
            break

    # Extract origin/destination cities from user prompt
    origin = ""
    destination = ""
    city_match = re.search(r"从(.+?)(?:出发|到|去|→)", user_prompt)
    if city_match:
        origin = city_match.group(1).strip()
    dest_match = re.search(r"(?:到|去|→)(.+?)(?:的|，|。|出差|旅|游|$)", user_prompt)
    if dest_match:
        destination = dest_match.group(1).strip()

    return {
        "raw_output": raw_output,
        "tool_trace": tool_trace,
        "problem_type": ptype,
        "user_prompt": user_prompt,
        "origin": origin,
        "destination": destination,
    }


def compute_code_score_simple(entry: dict) -> dict:
    """Compute a simplified code score without the full scorer infrastructure.

    Checks the key scoring dimensions:
    - IC: how many tool facts appear in the plan
    - Completeness: how many required sections are present with grounded facts
    - Tool diversity
    - Fabrication risk
    """
    inputs = extract_scoring_inputs(entry)
    raw_output = inputs["raw_output"]
    tool_trace = inputs["tool_trace"]
    ptype = inputs["problem_type"]

    if not raw_output or len(raw_output) < 200:
        return {"total": 0, "reason": "too_short", "ic": 0, "comp": 0, "div": 0, "fab": 0}

    # --- IC: Extract facts from ALL tool results (robust, no tool name matching) ---
    tool_facts = {
        "flights": [], "trains": [], "pois": [], "prices": [],
        "times": [], "weather": [], "distances": [], "wind": [],
        "travel_durations": [],
    }
    tools_called = set()
    for t in tool_trace:
        tools_called.add(t["tool"])

    # Extract from all tool result messages directly (bypasses tool name matching issues)
    msgs = entry.get("messages", [])
    for msg in msgs:
        if msg.get("role") != "tool":
            continue
        content = msg.get("content", "")
        if not content:
            continue

        # Try parsing as JSON
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            data = content

        # Case 1: List of Chinese transport strings
        if isinstance(data, list) and data and isinstance(data[0], str):
            for s in data:
                # Extract transport IDs
                flight_ids = re.findall(r'航班\s+([A-Z]{2}\d{3,5})', s)
                train_ids = re.findall(r'车次\s+([A-Z]\d{3,5})', s)
                if not flight_ids and not train_ids:
                    # Fallback: any ID pattern
                    all_ids = re.findall(r'([A-Z]{1,3}\d{3,5})', s)
                    if '航班' in s:
                        flight_ids = all_ids
                    else:
                        train_ids = all_ids
                tool_facts["flights"].extend(flight_ids)
                tool_facts["trains"].extend(train_ids)
                # Prices and times from transport strings
                prices = re.findall(r'(\d+)元', s)
                tool_facts["prices"].extend(prices)
                times = re.findall(r'(\d{2}:\d{2})', s)
                tool_facts["times"].extend(times)

        # Case 2: List of POI/restaurant objects
        elif isinstance(data, list) and data and isinstance(data[0], dict):
            for item in data:
                if "name" in item:
                    tool_facts["pois"].append(item["name"])
                # Weather objects
                if "dayweather" in item:
                    tool_facts["weather"].append(item["dayweather"])
                if "nightweather" in item:
                    tool_facts["weather"].append(item["nightweather"])
                if "daywind" in item:
                    tool_facts["wind"].append(item["daywind"])
                if "daytemp" in item:
                    tool_facts["weather"].append(item["daytemp"] + "度")

        # Case 3: Direction result (dict with distance/duration)
        elif isinstance(data, dict):
            if "distance" in data:
                tool_facts["distances"].append(data["distance"])
            if "duration" in data:
                tool_facts["travel_durations"].append(data["duration"])

        # Case 4: Empty list (no results)
        elif isinstance(data, list) and not data:
            pass

        # Case 5: Raw string (fallback extraction)
        elif isinstance(content, str):
            ids = re.findall(r'([A-Z]{1,3}\d{3,5})', content)
            tool_facts["trains"].extend(ids)
            prices = re.findall(r'(\d+)元', content)
            tool_facts["prices"].extend(prices)

    # Count IC categories with matches
    ic_scores = {}
    ic_total = 0
    ic_categories = 0
    for cat, facts in tool_facts.items():
        if not facts:
            continue
        matched = sum(1 for f in facts if f in raw_output)
        ratio = matched / len(facts) if facts else 0
        score = min(1.0, ratio / 0.5)  # 50% overlap threshold
        ic_scores[cat] = {"matched": matched, "total": len(facts), "score": round(score, 2)}
        if matched > 0:
            ic_categories += 1
        ic_total += score

    ic_denominator = max(1, len([c for c in ic_scores if ic_scores[c]["total"] > 0]))
    ic_normalized = (ic_total / ic_denominator) * 25.0 if ic_denominator > 0 else 0

    # Breadth penalty
    available_cats = len([c for c in ic_scores if ic_scores[c]["total"] > 0])
    if ic_categories < 4 and available_cats >= 4:
        ic_normalized *= 0.5

    # --- Completeness: Check required sections ---
    comp_checks = {
        "交通方案": (r"出发|到达|发车|起飞", r"\d{2}:\d{2}"),
        "价格对比": (r"价格|费用|票价", r"\d+元"),
        "推荐理由": (r"推荐|建议|最佳", None),
        "餐饮推荐": (r"餐|吃|美食", r"餐厅|饭店|小吃"),
        "天气穿衣": (r"天气|气温|穿衣", r"晴|阴|度"),
        "预算明细": (r"预算|费用|花费", r"\d+元"),
    }
    if ptype in ("multiday", "hybrid", "business"):
        comp_checks["住宿建议"] = (r"住宿|酒店|宾馆", r"酒店|宾馆|民宿")
    if ptype in ("multiday", "hybrid", "single_poi", "family_study"):
        comp_checks["景点安排"] = (r"景点|游览|参观", r"景区|公园|博物馆|古镇")
    if ptype in ("single_poi", "food_tour"):
        comp_checks["交通路线"] = (r"交通|距离|步行", r"\d+米|\d+公里|\d+分钟")

    comp_total = 0
    comp_details = {}
    for section, (keyword_pat, fact_pat) in comp_checks.items():
        has_keyword = bool(re.search(keyword_pat, raw_output))
        has_fact = bool(re.search(fact_pat, raw_output)) if fact_pat else True
        # Check if grounded in tool data
        has_grounding = False
        for cat_facts in tool_facts.values():
            for f in cat_facts:
                if f in raw_output:
                    has_grounding = True
                    break
            if has_grounding:
                break

        if has_keyword and has_fact and has_grounding:
            score = 1.0
        elif has_keyword and has_grounding:
            score = 0.5
        elif has_keyword:
            score = 0.2
        else:
            score = 0.0
        comp_details[section] = round(score, 2)
        comp_total += score

    comp_normalized = (comp_total / max(1, len(comp_checks))) * 25.0

    # --- Reasoning density ---
    reasoning_words = len(re.findall(r"因为|由于|所以|因此|建议|推荐|考虑到|综合|权衡|对比|相比|优先|适合", raw_output))
    if reasoning_words < 3 and len(raw_output) > 500:
        comp_normalized *= 0.6

    # --- Tool diversity ---
    must_call = {"poi_search"}
    should_call = set()
    nice_to_have = set()
    if ptype in ("multiday", "single_poi", "food_tour", "family_study"):
        must_call.add("weather")
    if ptype in ("multiday", "hybrid", "family_study"):
        should_call.add("direction")
    if ptype in ("single_poi",):
        should_call.add("around_search")
    if ptype in ("hybrid",):
        should_call.add("direction")
    if ptype in ("intercity", "business", "hybrid", "multiday", "food_tour", "family_study", "single_poi"):
        nice_to_have.add("direction")

    div_mult = 1.0
    for tool in should_call:
        if tool not in tools_called:
            div_mult -= 0.25
    for tool in nice_to_have - should_call:
        if tool in tools_called:
            div_mult += 0.05
    div_mult = max(0.3, min(1.1, div_mult))

    # --- Fabrication check (simplified) ---
    fab_penalty = 0.0
    # Check for transport IDs in plan that aren't in tool results
    plan_flight_ids = set(re.findall(r'[A-Z]{1,2}\d{4}', raw_output))
    plan_train_ids = set(re.findall(r'[GDC]\d{3,4}', raw_output))
    tool_transport_ids = set(tool_facts["flights"] + tool_facts["trains"])
    if plan_flight_ids or plan_train_ids:
        all_plan_ids = plan_flight_ids | plan_train_ids
        unverified = all_plan_ids - tool_transport_ids
        if all_plan_ids:
            fab_ratio = len(unverified) / len(all_plan_ids)
            fab_penalty = -12.5 * fab_ratio * 0.5  # simplified

    # --- Final score ---
    import math
    ic_norm = max(0, ic_normalized) / 25.0
    comp_norm = max(0, comp_normalized) / 25.0
    code_score = 50.0 * math.sqrt(ic_norm * comp_norm) * div_mult + fab_penalty
    code_score = max(0, code_score)

    return {
        "total": round(code_score, 2),
        "ic": round(ic_normalized, 2),
        "comp": round(comp_normalized, 2),
        "div": round(div_mult, 2),
        "fab": round(fab_penalty, 2),
        "ic_categories": ic_categories,
        "ic_details": ic_scores,
        "comp_details": comp_details,
        "plan_len": len(raw_output),
        "tools_called": sorted(tools_called),
        "reasoning_words": reasoning_words,
        "around_count": sum(1 for t in tool_trace if t["tool"] == "around_search"),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=20, help="Score threshold for 'low quality'")
    parser.add_argument("--remove-below", type=float, default=0, help="Remove entries below this score")
    parser.add_argument("--output", type=str, default="", help="Output scored entries to file")
    args = parser.parse_args()

    canonical_path = "data/canonical/navworld.jsonl"
    entries = []
    with open(canonical_path) as f:
        for line in f:
            entries.append(json.loads(line))

    print(f"Scoring {len(entries)} NAVWORLD entries...")

    scores = []
    for i, entry in enumerate(entries):
        result = compute_code_score_simple(entry)
        result["index"] = i
        result["problem_type"] = entry.get("problem_type", "unknown")
        scores.append(result)

    # Sort by score
    scores.sort(key=lambda x: x["total"])

    # Summary stats
    all_scores = [s["total"] for s in scores]
    print(f"\n=== Score Distribution ===")
    print(f"Total: {len(scores)}")
    print(f"Mean: {sum(all_scores)/len(all_scores):.1f}")
    print(f"Median: {sorted(all_scores)[len(all_scores)//2]:.1f}")
    print(f"Min: {min(all_scores):.1f}, Max: {max(all_scores):.1f}")

    # Buckets
    buckets = defaultdict(int)
    for s in all_scores:
        if s < 10:
            buckets["0-10"] += 1
        elif s < 20:
            buckets["10-20"] += 1
        elif s < 30:
            buckets["20-30"] += 1
        elif s < 40:
            buckets["30-40"] += 1
        else:
            buckets["40-50"] += 1
    print(f"\nBuckets:")
    for b in ["0-10", "10-20", "20-30", "30-40", "40-50"]:
        print(f"  {b}: {buckets[b]}")

    # Per-type breakdown
    print(f"\n=== Per-Type Scores ===")
    type_scores = defaultdict(list)
    for s in scores:
        type_scores[s["problem_type"]].append(s["total"])
    for t, ts in sorted(type_scores.items(), key=lambda x: sum(x[1])/len(x[1])):
        avg = sum(ts) / len(ts)
        low = sum(1 for x in ts if x < args.threshold)
        print(f"  {t:15s}: avg={avg:5.1f}  count={len(ts):4d}  below_{args.threshold}={low}")

    # Low quality entries
    low_quality = [s for s in scores if s["total"] < args.threshold]
    print(f"\n=== Low Quality (below {args.threshold}) ===")
    print(f"Count: {len(low_quality)} / {len(scores)} ({len(low_quality)*100//len(scores)}%)")
    if low_quality:
        # Common patterns
        low_types = defaultdict(int)
        low_reasons = defaultdict(int)
        for s in low_quality:
            low_types[s["problem_type"]] += 1
            if s["ic"] < 10:
                low_reasons["low_ic"] += 1
            if s["comp"] < 10:
                low_reasons["low_comp"] += 1
            if s["reasoning_words"] < 5:
                low_reasons["low_reasoning"] += 1
            if s["around_count"] > 2:
                low_reasons["excess_around"] += 1
        print(f"By type: {dict(low_types)}")
        print(f"Reasons: {dict(low_reasons)}")

    # Bottom 20 details
    print(f"\n=== Bottom 20 Entries ===")
    for s in scores[:20]:
        print(f"  [{s['index']:4d}] type={s['problem_type']:15s} score={s['total']:5.1f} ic={s['ic']:5.1f} comp={s['comp']:5.1f} div={s['div']:.2f} fab={s['fab']:.1f} plan={s['plan_len']}ch reasoning={s['reasoning_words']} around={s['around_count']}")

    # Remove low quality if requested
    if args.remove_below > 0:
        keep = [e for e, s in zip(entries, [compute_code_score_simple(e) for e in entries]) if s["total"] >= args.remove_below]
        removed = len(entries) - len(keep)
        print(f"\n=== Removing {removed} entries below {args.remove_below} ===")
        print(f"Keeping {len(keep)} entries")
        # Write back
        with open(canonical_path, "w") as f:
            for e in keep:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        print(f"Written to {canonical_path}")

    # Save detailed scores
    if args.output:
        with open(args.output, "w") as f:
            json.dump(scores, f, ensure_ascii=False, indent=2)
        print(f"\nDetailed scores saved to {args.output}")


if __name__ == "__main__":
    main()
