#!/usr/bin/env python3
"""Generate hybrid MemoryGym SFT data: deterministic actions + real tool results.

Combines the correctness of simulation-based trajectories with realistic
ChromaDB search results and selective redaction (matching real eval behavior).

Key differences from generate_sft_trajectory():
1. Real ChromaDB backend — search results match what eval produces
2. Real execute_tool() — Write/Edit/memory_search return actual formatted results
3. Selective redaction — context reset between events (system + memory summary)
4. Budget tracking via MemoryBudget

Output: JSONL with {"messages": [...], "env": "MemoryGym", "score": 1.0, ...}

Usage:
    python scripts/memorygym_hybrid_gen.py -o data/memorygym_hybrid.jsonl --seeds 10
    python scripts/memorygym_hybrid_gen.py --template company --seeds 5 --tier lite
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from pathlib import Path
from random import Random

# Setup paths
ROOT = Path(__file__).parent.parent
PYLIBS = ROOT / ".pylibs"
MEMORYGYM = ROOT / "repos" / "MemoryGym"
sys.path.insert(0, str(PYLIBS))
sys.path.insert(0, str(MEMORYGYM))

CACHE_DIR = ROOT / ".cache" / "huggingface"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ["HF_HOME"] = str(CACHE_DIR)
os.environ["TRANSFORMERS_CACHE"] = str(CACHE_DIR)
os.environ["SENTENCE_TRANSFORMERS_HOME"] = str(CACHE_DIR)

from memorygym.agents._tool_helpers import execute_tool
from memorygym.memory.backends.chromadb_backend import ChromaDBBackend
from memorygym.memory.budget import MemoryBudget
from memorygym.protocol import TIERS
from memorygym.simulation import TEMPLATES


SYSTEM_PROMPT = """You are participating in a memory management evaluation.
Write budget: {budget} total writes. Be selective — you'll see more entities than you can store.

## Event Types
1. DOCUMENTS: Entity data to read and store selectively.
2. CORRECTIONS: Updated data. You MUST update stored memories.
3. QUESTIONS: Answer from stored memories only.

## Tools

Call tools by outputting JSON blocks:

**Write** — Append to your memory file (costs 1 write, budget: {budget}):
<tool_call>{{"name": "Write", "arguments": {{"content": "info to store"}}}}</tool_call>

**Edit** — Update existing content in your memory file when data changes (costs 1 write; free during correction events):
<tool_call>{{"name": "Edit", "arguments": {{"old_text": "text to find", "new_text": "replacement text"}}}}</tool_call>

**Read** — Read your memory file (free):
<tool_call>{{"name": "Read", "arguments": {{}}}}</tool_call>

**memory_search** — Semantic search over your memory (free):
<tool_call>{{"name": "memory_search", "arguments": {{"query": "entity name"}}}}</tool_call>

**submit_answer** — Submit your final answer:
<tool_call>{{"name": "submit_answer", "arguments": {{"answer": "your answer"}}}}</tool_call>

## Memory Budget
- You have limited write operations — plan your usage carefully
- Each Write costs 1 write; Edit also costs 1 write except during correction events (free)

## Answering Questions
- Search by entity name, then submit_answer with the value
- For comparison/synthesis: answer as "EntityName (value)"
- If data not in memory: submit "I don't have enough information"
- Do NOT guess or fabricate values
- ALWAYS call submit_answer for every question
"""


def _build_reasoning(
    question: str, answer: str, competency: str,
    search_result: str, entity_name: str,
    correction_ctx: dict | None = None,
) -> str:
    """Build a reasoning chain grounded in visible context.

    For retrieval: references specific field from search results.
    For delta/counterfactual: references the correction event values.
    For count/filter: describes the filtering logic.
    """
    if not answer:
        return ""

    # Parse search result to find the field containing the answer
    matching_field = ""
    if search_result:
        for segment in search_result.split("|"):
            segment = segment.strip()
            if answer in segment and ":" in segment:
                matching_field = segment
                break

    if competency == "retrieval":
        if matching_field:
            return f"From my memory: {matching_field}. The answer is {answer}."
        return f"Found {entity_name} in memory. The value is {answer}."
    elif competency == "update":
        if matching_field:
            return f"After the correction, my memory shows: {matching_field}. Current value: {answer}."
        if correction_ctx:
            return (f"The correction changed {correction_ctx.get('attr', 'the value')} "
                    f"from {correction_ctx.get('old', '?')} to {correction_ctx.get('new', '?')}. "
                    f"Current value: {answer}.")
        return f"The corrected value for {entity_name} is {answer}."
    elif competency == "delta":
        if correction_ctx:
            return (f"The correction changed the value from {correction_ctx.get('old', '?')} "
                    f"to {correction_ctx.get('new', '?')}. "
                    f"Difference: {correction_ctx.get('new', '?')} - {correction_ctx.get('old', '?')} = {answer}.")
        return f"Computing the difference: {answer}."
    elif competency == "counterfactual":
        if correction_ctx:
            return (f"The correction notice said: old value was {correction_ctx.get('old', '?')}, "
                    f"new value is {correction_ctx.get('new', '?')}. "
                    f"Before the correction: {answer}.")
        return f"Before the correction, the value was {answer}."
    elif competency in ("synthesis", "comparison", "cross_category"):
        if matching_field:
            return f"Comparing entities — {matching_field}. Answer: {answer}."
        return f"After comparing the relevant entities: {answer}."
    elif competency in ("aggregation", "multi_constraint", "enum_filter"):
        return f"Counting entities matching the criteria: {answer}."
    elif competency == "abstention":
        return f"This entity is not in my memory."
    else:
        if matching_field:
            return f"From memory: {matching_field}. Answer: {answer}."
        return f"Based on stored data: {answer}."


def _build_memory_summary(backend, budget, event_idx: int, total: int) -> str:
    """Build a memory summary message — matches eval's redaction format exactly.

    Must match stream_agent.py lines 739-752 so SFT data matches eval context.
    """
    stored_entries = backend.list()
    if stored_entries:
        stored_names_list = [
            e["content"].split("|")[0].strip() for e in stored_entries
        ]
        return (
            f"[{event_idx}/{total} done]\n\n"
            f"Your memory contains {len(stored_entries)} entries: "
            + ", ".join(stored_names_list[:30])
            + (f" ... (+{len(stored_names_list)-30} more)"
               if len(stored_names_list) > 30 else "")
            + f"\nBudget: {budget.remaining()} writes remaining."
        )
    return (
        f"[{event_idx}/{total} done]\n"
        f"Your memory is empty. Budget: {budget.remaining()} "
        f"writes remaining."
    )


def generate_hybrid_trajectory(
    template_name: str,
    seed: int,
    strategy: str = "perfect",
    n_entities: int = 30,
    n_questions: int = 10,
    n_corrections: int = 3,
    write_budget: int = 15,
) -> tuple[list[dict], dict]:
    """Generate a trajectory with real ChromaDB results and selective redaction.

    Returns (messages, metadata).
    """
    tmpl = TEMPLATES[template_name]()
    world = tmpl.generate_world(seed=seed, n_entities=n_entities, eval_salt=1)

    # Storage decisions (same logic as generate_sft_trajectory)
    rng_doc = Random(seed)
    all_docs = [(e, tmpl.render_document(e, world.active_attrs, rng_doc))
                for e in world.entities]

    rng_store = Random(seed + 111)
    if strategy == "perfect":
        ranked = sorted(
            range(len(all_docs)),
            key=lambda i: tmpl.entity_importance(all_docs[i][0], world),
            reverse=True,
        )
        stored_indices = sorted(ranked[:write_budget])
    else:
        n_store = min(max(1, int(len(all_docs) * 0.7)), write_budget)
        stored_indices = sorted(rng_store.sample(range(len(all_docs)), n_store))

    stored_names = {all_docs[i][0].name for i in stored_indices}
    original_attrs = {e.name: copy.deepcopy(e.attrs) for e in world.entities}

    # Corrections
    rng_correct = Random(seed + 3333)
    corrections = tmpl.generate_corrections(world, rng_correct, n_corrections)

    # Ensure corrected entities are stored
    corrected_not_stored = [
        c.entity_name for c in corrections if c.entity_name not in stored_names
    ]
    if corrected_not_stored:
        name_to_imp = {
            all_docs[i][0].name: tmpl.entity_importance(all_docs[i][0], world)
            for i in range(len(all_docs))
        }
        evictable = sorted(
            [n for n in stored_names if n not in {c.entity_name for c in corrections}],
            key=lambda n: name_to_imp.get(n, 0),
        )
        for cname in corrected_not_stored:
            if len(stored_names) >= write_budget and evictable:
                stored_names.discard(evictable.pop(0))
            stored_names.add(cname)

    # Contradictions + stream
    n_contras = max(1, n_corrections // 3)
    exclude_corrected = {c.entity_name for c in corrections}
    rng_contra = Random(seed + 7373)
    contradictions = tmpl.generate_contradictions(
        world, rng_contra, n_contras, exclude_entities=exclude_corrected)

    rng_stream = Random(seed + 5555)
    stream = tmpl.generate_stream(
        world, rng_stream, corrections, stored_names,
        n_questions=n_questions, entities_per_batch=10,
        contradictions=contradictions,
    )

    # Real ChromaDB backend + budget
    backend = ChromaDBBackend()
    budget = MemoryBudget(total_writes=write_budget)

    system_prompt = SYSTEM_PROMPT.format(budget=write_budget)
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    total_events = len(stream)

    # Track corrections that fire before their entity is ingested
    fired_corrections: dict[str, list[dict]] = {}
    # Track all correction events for reasoning context
    correction_history: dict[str, dict] = {}  # entity_name → {attr, old, new}
    correct_count = 0
    total_questions = 0

    for event_idx, event in enumerate(stream):
        event_type = event["type"]

        # Selective redaction between events — matches eval's context wipe
        # (stream_agent.py:733-754). Each event starts from: system + summary + OK.

        if event_type == "ingest":
            is_contradiction = event.get("is_contradiction", False)
            docs = event["documents"]
            docs_text = "\n\n".join(
                f"[Document {i+1}]\n{doc}" for i, doc in enumerate(docs))
            remaining = budget.remaining()
            entities_seen = sum(
                1 for e in stream[:event_idx] if e["type"] == "ingest"
                for _ in e.get("entity_names", []))
            user_msg = (
                f"=== Event {event_idx+1}/{total_events} [DOCUMENTS] ===\n\n"
                f"⚠️ Budget: {remaining}/{write_budget} writes remaining. "
                f"Entities seen so far: {entities_seen} (more may follow). "
                f"Be selective — store what matters most.\n\n"
                f"**Documents:**\n{docs_text}\n\n"
                "No question. Store important entity data."
            )
            messages.append({"role": "user", "content": user_msg})

            # --- Contradiction detection: Search → Edit existing memory ---
            if is_contradiction:
                for ename in event.get("entity_names", []):
                    if ename not in stored_names:
                        continue
                    # Search for entity in memory
                    search_result, _ = execute_tool(
                        "memory_search", {"query": ename}, backend, budget)
                    search_tc = (
                        f'<tool_call>{{"name": "memory_search", '
                        f'"arguments": {{"query": {json.dumps(ename)}}}}}</tool_call>'
                    )
                    messages.append({"role": "assistant", "content": search_tc})
                    messages.append({
                        "role": "user",
                        "content": f"Tool results:\n[memory_search] {search_result}",
                    })

                    # Find the contradiction's changed attr/value
                    contra = next(
                        (c for c in contradictions if c.entity_name == ename),
                        None)
                    if (contra and search_result
                            and "No results" not in search_result
                            and ename in search_result):
                        old_val_str = str(contra.old_val)
                        new_val_str = str(contra.new_val)
                        attr_name = contra.attr
                        # Find and edit via backend
                        target_entry = None
                        matched_val_str = old_val_str
                        old_val_variants = {old_val_str}
                        try:
                            fv = float(old_val_str)
                            old_val_variants.add(f"{fv:g}")
                            old_val_variants.add(str(int(fv)))
                            old_val_variants.add(f"{fv:,.2f}")
                            old_val_variants.add(f"{fv:,.0f}")
                            old_val_variants.add(f"{int(fv):,}")
                            # Currency/unit formats: $X,XXX.XM
                            old_val_variants.add(f"${fv:,.1f}M")
                            old_val_variants.add(f"${fv:,.2f}M")
                            old_val_variants.add(f"${fv:,.1f}")
                            old_val_variants.add(f"${fv:,.0f}")
                            old_val_variants.add(f"${int(fv):,}")
                            old_val_variants.add(f"{fv:.1f}")
                            old_val_variants.add(f"{fv:.2f}")
                        except (ValueError, OverflowError):
                            pass
                        def _normalize_attr(s):
                            return s.lower().replace("_", " ").replace("-", " ").strip()
                        attr_norm = _normalize_attr(attr_name) if attr_name else ""

                        for entry in backend.list():
                            if ename not in entry["content"]:
                                continue
                            content = entry["content"]
                            # Try exact match with all variants
                            for variant in old_val_variants:
                                if variant in content:
                                    target_entry = entry
                                    matched_val_str = variant
                                    break
                            if target_entry:
                                break
                            # Fuzzy: find field by attr name, replace its value
                            if attr_norm:
                                for segment in content.split("|"):
                                    seg = segment.strip()
                                    if ":" not in seg:
                                        continue
                                    label, val = seg.split(":", 1)
                                    if attr_norm in _normalize_attr(label):
                                        target_entry = entry
                                        matched_val_str = val.strip()
                                        break
                                if target_entry:
                                    break
                        if target_entry:
                            content = target_entry["content"]
                            idx = content.find(matched_val_str)
                            if idx >= 0:
                                pipe_pos = content.rfind("|", 0, idx)
                                start = pipe_pos + 1 if pipe_pos >= 0 else 0
                                next_pipe = content.find("|", idx + len(matched_val_str))
                                end = next_pipe if next_pipe >= 0 else len(content)
                                contextual_old = content[start:end].strip()
                                contextual_new = contextual_old.replace(
                                    matched_val_str, new_val_str, 1)
                                new_content = content.replace(
                                    matched_val_str, new_val_str, 1)
                                backend.forget(target_entry["id"])
                                backend.store(new_content)
                                reasoning = (
                                    f"This document has updated data for {ename}. "
                                    f"The value changed from {old_val_str} to {new_val_str}. "
                                    f"Updating my memory.")
                                edit_tc = (
                                    f'{reasoning}\n'
                                    f'<tool_call>{{"name": "Edit", '
                                    f'"arguments": {{"old_text": {json.dumps(contextual_old)}, '
                                    f'"new_text": {json.dumps(contextual_new)}}}}}</tool_call>'
                                )
                                messages.append({"role": "assistant", "content": edit_tc})
                                messages.append({
                                    "role": "user",
                                    "content": f"Tool results:\n[Edit] Edited. {budget.remaining()} writes left.",
                                })
                            else:
                                messages.append({
                                    "role": "assistant",
                                    "content": f"Data for {ename} appears similar to what I have. No update needed.",
                                })
                        else:
                            messages.append({
                                "role": "assistant",
                                "content": f"Data for {ename} appears similar to what I have. No update needed.",
                            })
                    else:
                        messages.append({
                            "role": "assistant",
                            "content": f"{ename} not found in memory or no change detected.",
                        })
            else:
                # --- Normal ingest: Write with triage reasoning ---
                tool_calls = []
                tool_results = []
                skipped_names = []
                for ename in event.get("entity_names", []):
                    if ename not in stored_names:
                        skipped_names.append(ename)
                        continue
                    entity = world.get_entity(ename)
                    if not entity:
                        continue
                    # Use original attrs if correction hasn't fired yet
                    if ename not in fired_corrections:
                        saved = {}
                        if ename in original_attrs:
                            for attr, val in entity.attrs.items():
                                if attr in original_attrs[ename] and val != original_attrs[ename][attr]:
                                    saved[attr] = val
                                    entity.attrs[attr] = original_attrs[ename][attr]
                        compact = tmpl._compact_document(entity, world.active_attrs)
                        for attr, val in saved.items():
                            entity.attrs[attr] = val
                    else:
                        compact = tmpl._compact_document(entity, world.active_attrs)

                    content = f"{ename} | {compact}"
                    tc = f'<tool_call>{{"name": "Write", "arguments": {{"content": {json.dumps(content)}}}}}</tool_call>'
                    tool_calls.append(tc)

                    # Real tool execution
                    result_text, _ = execute_tool(
                        "Write", {"content": content}, backend, budget)
                    tool_results.append(f"[Write] {result_text}")

                if tool_calls:
                    # Add triage reasoning when some entities skipped
                    prefix = ""
                    if skipped_names and remaining < len(event.get("entity_names", [])):
                        prefix = (
                            f"Budget is limited ({remaining} writes left). "
                            f"Skipping lower-priority entities: {', '.join(skipped_names[:3])}. "
                            f"Storing the most important ones.\n"
                        )
                    messages.append({
                        "role": "assistant",
                        "content": prefix + "\n".join(tool_calls),
                    })
                    messages.append({
                        "role": "user",
                        "content": "Tool results:\n" + "\n".join(tool_results),
                    })
                else:
                    remaining = budget.remaining()
                    messages.append({
                        "role": "assistant",
                        "content": (
                            f"Budget: {remaining} writes left. "
                            f"These entities are not high priority. "
                            f"Skipping to conserve budget for more important data."
                        ),
                    })

            # Redaction after ingest event
            summary = _build_memory_summary(
                backend, budget, event_idx + 1, total_events)
            messages.append({"role": "user", "content": summary})
            messages.append({"role": "assistant", "content": "OK."})

        elif event_type == "correction":
            ename = event["entity_name"]
            old_val_str = str(event.get("old_val", ""))
            new_val_str = str(event.get("new_val", ""))
            # Record for reasoning context in later questions
            correction_history[ename] = {
                "attr": event.get("attr", ""),
                "old": old_val_str,
                "new": new_val_str,
            }
            user_msg = (
                f"=== Event {event_idx+1}/{total_events} [CORRECTION] ===\n\n"
                f"**Correction Notice:**\n{event['notice']}\n\n"
                f"Entity: {ename}\n"
                f"Old value: {old_val_str}\n"
                f"New value: {new_val_str}\n\n"
                f"If you stored data about this entity, use memory_search "
                f"to find it and Edit to update. "
                f"Correction edits do not consume your write budget."
            )
            messages.append({"role": "user", "content": user_msg})

            if ename in stored_names and any(
                ename in e["content"] for e in backend.list()
            ):
                # Search → Edit chain with real results
                search_result, _ = execute_tool(
                    "memory_search", {"query": ename}, backend, budget)
                search_tc = (
                    f'<tool_call>{{"name": "memory_search", '
                    f'"arguments": {{"query": {json.dumps(ename)}}}}}</tool_call>'
                )
                messages.append({"role": "assistant", "content": search_tc})
                messages.append({
                    "role": "user",
                    "content": f"Tool results:\n[memory_search] {search_result}",
                })

                # Edit: find exact entry and edit directly on backend
                # Strategy: exact str match → attr-name field lookup → numeric prefix
                attr_name = event.get("attr", "")
                target_entry = None
                matched_val_str = old_val_str  # the string actually in content

                # Normalize attr for fuzzy field matching
                def _normalize(s):
                    return s.lower().replace("_", " ").replace("-", " ").strip()

                attr_norm = _normalize(attr_name)
                # Also try old_val variants: strip trailing zeros, commas
                old_val_variants = {old_val_str}
                try:
                    fv = float(old_val_str)
                    old_val_variants.add(f"{fv:g}")          # 31.10 → 31.1
                    old_val_variants.add(f"{fv:.1f}")        # 31.07 → 31.1
                    old_val_variants.add(f"{int(fv):,}")     # 1112 → 1,112
                    old_val_variants.add(str(int(fv)))       # 31.0 → 31
                except (ValueError, OverflowError):
                    pass

                for entry in backend.list():
                    if ename not in entry["content"]:
                        continue
                    content = entry["content"]
                    # Try exact match with all variants
                    for variant in old_val_variants:
                        if variant in content:
                            target_entry = entry
                            matched_val_str = variant
                            break
                    if target_entry:
                        break
                    # Fuzzy: find field by attr name, replace its value
                    if attr_norm:
                        for segment in content.split("|"):
                            seg = segment.strip()
                            if ":" not in seg:
                                continue
                            label, val = seg.split(":", 1)
                            if attr_norm in _normalize(label):
                                target_entry = entry
                                matched_val_str = val.strip()
                                break
                        if target_entry:
                            break

                if target_entry:
                    content = target_entry["content"]
                    idx = content.find(matched_val_str)
                    if idx >= 0:
                        # Extract contextual substring: "field_label: old_val"
                        pipe_pos = content.rfind("|", 0, idx)
                        start = pipe_pos + 1 if pipe_pos >= 0 else 0
                        next_pipe = content.find("|", idx + len(matched_val_str))
                        end = next_pipe if next_pipe >= 0 else len(content)
                        contextual_old = content[start:end].strip()
                        contextual_new = contextual_old.replace(
                            matched_val_str, new_val_str, 1)

                        # Direct backend edit (guaranteed success)
                        new_content = content.replace(
                            matched_val_str, new_val_str, 1)
                        backend.forget(target_entry["id"])
                        backend.store(new_content)
                        edit_result_text = (
                            f"Edited. {budget.remaining()} writes left.")
                    else:
                        contextual_old = old_val_str
                        contextual_new = new_val_str
                        edit_result_text = "Text not found in memory."
                else:
                    contextual_old = old_val_str
                    contextual_new = new_val_str
                    edit_result_text = "Text not found in memory."

                edit_tc = (
                    f'<tool_call>{{"name": "Edit", '
                    f'"arguments": {{"old_text": {json.dumps(contextual_old)}, '
                    f'"new_text": {json.dumps(contextual_new)}}}}}</tool_call>'
                )
                messages.append({"role": "assistant", "content": edit_tc})
                messages.append({
                    "role": "user",
                    "content": f"Tool results:\n[Edit] {edit_result_text}",
                })
            else:
                fired_corrections.setdefault(ename, []).append(event)
                messages.append({
                    "role": "assistant",
                    "content": "Entity not in my memory. No update needed.",
                })

            # Redaction after correction event
            summary = _build_memory_summary(
                backend, budget, event_idx + 1, total_events)
            messages.append({"role": "user", "content": summary})
            messages.append({"role": "assistant", "content": "OK."})

        elif event_type == "noise":
            user_msg = (
                f"=== Event {event_idx+1}/{total_events} [INFO] ===\n\n"
                f"{event['document']}\n\n"
                "This is supplementary information. "
                "Store only if relevant to your tasks."
            )
            messages.append({"role": "user", "content": user_msg})
            messages.append({
                "role": "assistant",
                "content": "This is noise/supplementary info. Skipping.",
            })

            # Redaction after noise event
            summary = _build_memory_summary(
                backend, budget, event_idx + 1, total_events)
            messages.append({"role": "user", "content": summary})
            messages.append({"role": "assistant", "content": "OK."})
            continue

        elif event_type == "question":
            total_questions += 1
            user_msg = (
                f"=== Event {event_idx+1}/{total_events} [QUESTION] ===\n\n"
                f"**Question:**\n{event['question']}\n\n"
                "Search your memory and call submit_answer(answer=\"...\")."
            )
            messages.append({"role": "user", "content": user_msg})

            gt = str(event["answer"])
            required = event.get("required_entities", [])
            competency = event["competency"]

            if competency == "abstention":
                # Check if this is a "trick question" — entity IS stored
                # Eval includes trick retrieval questions phrased like abstention
                # but with real GT. Model must answer, not abstain.
                is_trick = (
                    required
                    and all(n in stored_names for n in required)
                    and gt and gt != "I don't have enough information"
                    and any(n in e["content"] for n in required
                            for e in backend.list())
                )

                if is_trick:
                    # Trick question: search and answer correctly
                    all_search_text = ""
                    for req_entity in required:
                        search_result, _ = execute_tool(
                            "memory_search", {"query": req_entity},
                            backend, budget)
                        all_search_text += search_result + "\n"
                        search_tc = (
                            f'<tool_call>{{"name": "memory_search", '
                            f'"arguments": {{"query": {json.dumps(req_entity)}}}}}</tool_call>'
                        )
                        messages.append({"role": "assistant", "content": search_tc})
                        messages.append({
                            "role": "user",
                            "content": f"Tool results:\n[memory_search] {search_result}",
                        })
                    reasoning = (
                        f"Although the question seems uncertain, I found "
                        f"{required[0]} in my memory. The data is available."
                    )
                    answer_tc = (
                        f'{reasoning}\n'
                        f'<tool_call>{{"name": "submit_answer", '
                        f'"arguments": {{"answer": {json.dumps(gt)}}}}}</tool_call>'
                    )
                    messages.append({"role": "assistant", "content": answer_tc})
                    messages.append({
                        "role": "user",
                        "content": f"[submit_answer] ANSWER_SUBMITTED: {gt}",
                    })
                    correct_count += 1
                else:
                    # True abstention: entity not stored
                    answer = "I don't have enough information"
                    search_q = required[0] if required else ""
                    if search_q:
                        search_result, _ = execute_tool(
                            "memory_search", {"query": search_q}, backend, budget)
                        search_tc = (
                            f'<tool_call>{{"name": "memory_search", '
                            f'"arguments": {{"query": {json.dumps(search_q)}}}}}</tool_call>'
                        )
                        messages.append({"role": "assistant", "content": search_tc})
                        messages.append({
                            "role": "user",
                            "content": f"Tool results:\n[memory_search] {search_result}",
                        })

                    reasoning = "Entity not found in my memory. Cannot answer."
                    answer_tc = (
                        f'{reasoning}\n'
                        f'<tool_call>{{"name": "submit_answer", '
                        f'"arguments": {{"answer": {json.dumps(answer)}}}}}</tool_call>'
                    )
                    messages.append({"role": "assistant", "content": answer_tc})
                    messages.append({
                        "role": "user",
                        "content": f"[submit_answer] ANSWER_SUBMITTED: {answer}",
                    })
                    correct_count += 1

            elif all(n in stored_names for n in required):
                # Search ALL required entities (not just first)
                all_search_text = ""
                for req_entity in required:
                    search_result, _ = execute_tool(
                        "memory_search", {"query": req_entity},
                        backend, budget)
                    all_search_text += search_result + "\n"
                    search_tc = (
                        f'<tool_call>{{"name": "memory_search", '
                        f'"arguments": {{"query": {json.dumps(req_entity)}}}}}</tool_call>'
                    )
                    messages.append({"role": "assistant", "content": search_tc})
                    messages.append({
                        "role": "user",
                        "content": f"Tool results:\n[memory_search] {search_result}",
                    })

                # Build reasoning grounded in search results + correction context
                corr_ctx = correction_history.get(required[0]) if required else None
                reasoning = _build_reasoning(
                    event["question"], gt, competency,
                    all_search_text, required[0] if required else "",
                    correction_ctx=corr_ctx)
                answer_tc = (
                    f'{reasoning}\n'
                    f'<tool_call>{{"name": "submit_answer", '
                    f'"arguments": {{"answer": {json.dumps(gt)}}}}}</tool_call>'
                )
                messages.append({"role": "assistant", "content": answer_tc})
                messages.append({
                    "role": "user",
                    "content": f"[submit_answer] ANSWER_SUBMITTED: {gt}",
                })
                correct_count += 1
            else:
                answer = "I don't have enough information"
                answer_tc = (
                    f'<tool_call>{{"name": "submit_answer", '
                    f'"arguments": {{"answer": {json.dumps(answer)}}}}}</tool_call>'
                )
                messages.append({"role": "assistant", "content": answer_tc})
                messages.append({
                    "role": "user",
                    "content": f"[submit_answer] ANSWER_SUBMITTED: {answer}",
                })

            # Redaction after question event
            summary = _build_memory_summary(
                backend, budget, event_idx + 1, total_events)
            messages.append({"role": "user", "content": summary})
            messages.append({"role": "assistant", "content": "OK."})

    # Merge consecutive same-role messages
    merged: list[dict] = [messages[0]]
    for msg in messages[1:]:
        if merged and msg["role"] == merged[-1]["role"]:
            merged[-1]["content"] += "\n\n---\n\n" + msg["content"]
        else:
            merged.append(msg)

    # Clean up
    backend.close()

    score = correct_count / total_questions if total_questions else 0.0
    metadata = {
        "template": template_name,
        "seed": seed,
        "strategy": strategy,
        "tier_config": {
            "entities": n_entities,
            "questions": n_questions,
            "corrections": n_corrections,
            "write_budget": write_budget,
        },
        "correct": correct_count,
        "total": total_questions,
        "score": score,
    }
    return merged, metadata


def _generate_one(args_tuple):
    """Worker function for parallel generation."""
    tmpl_name, seed, strategy, tier, worker_id, total = args_tuple
    try:
        messages, meta = generate_hybrid_trajectory(
            tmpl_name, seed,
            strategy=strategy,
            n_entities=tier["entities"],
            n_questions=tier["questions"],
            n_corrections=tier["corrections"],
            write_budget=tier["write_budget"],
        )
        entry = {
            "messages": messages,
            "env": "MemoryGym",
            "source": f"hybrid_{strategy}",
            "score": meta["score"],
            "template": tmpl_name,
            "seed": seed,
            **meta,
        }
        print(f"  [{worker_id}/{total}] {tmpl_name} seed={seed} "
              f"{len(messages)} msgs {meta['correct']}/{meta['total']}",
              flush=True)
        return entry
    except Exception as e:
        print(f"  [{worker_id}/{total}] {tmpl_name} seed={seed} ERROR: {e}",
              flush=True)
        return None


def main():
    import multiprocessing as mp

    parser = argparse.ArgumentParser(
        description="Generate hybrid MemoryGym SFT data")
    parser.add_argument("-o", "--output", default="data/memorygym_hybrid.jsonl")
    parser.add_argument("--templates", nargs="+", default=None,
                        help="Templates (default: all 10)")
    parser.add_argument("--strategy", default="perfect",
                        choices=["perfect", "strategic"])
    parser.add_argument("--seeds", type=int, default=10)
    parser.add_argument("--seed-offset", type=int, default=0,
                        help="Starting seed (default: 0)")
    parser.add_argument("--tier", default="lite",
                        choices=list(TIERS.keys()))
    parser.add_argument("--tier-mix", action="store_true",
                        help="Generate mixed tiers: 40%% lite, 30%% standard, 30%% hard")
    parser.add_argument("--shuffle-seed", type=int, default=42)
    parser.add_argument("-j", "--workers", type=int, default=1,
                        help="Parallel workers (default: 1)")
    args = parser.parse_args()

    template_names = args.templates or list(TEMPLATES.keys())
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build work items with optional tier mixing
    work = []
    idx = 0
    if args.tier_mix:
        # Mixed tiers: 40% lite, 30% standard, 30% hard
        tier_schedule = []
        for tmpl_name in template_names:
            for seed in range(args.seed_offset, args.seed_offset + args.seeds):
                # Deterministic tier assignment based on seed
                r = seed % 10
                if r < 4:
                    tier_schedule.append((tmpl_name, seed, TIERS["lite"]))
                elif r < 7:
                    tier_schedule.append((tmpl_name, seed, TIERS["standard"]))
                else:
                    tier_schedule.append((tmpl_name, seed, TIERS["hard"]))
        total = len(tier_schedule)
        for tmpl_name, seed, tier in tier_schedule:
            idx += 1
            work.append((tmpl_name, seed, args.strategy, tier, idx, total))
        tier_counts = {"lite": sum(1 for _, _, t in tier_schedule if t["entities"] == 30),
                       "standard": sum(1 for _, _, t in tier_schedule if t["entities"] == 60),
                       "hard": sum(1 for _, _, t in tier_schedule if t["entities"] == 120)}
        print(f"Tier mix: {tier_counts}")
    else:
        tier = TIERS[args.tier]
        total = len(template_names) * args.seeds
        for tmpl_name in template_names:
            for seed in range(args.seed_offset, args.seed_offset + args.seeds):
                idx += 1
                work.append((tmpl_name, seed, args.strategy, tier, idx, total))

    # Generate (parallel or sequential)
    if args.workers > 1:
        print(f"Generating {total} trajectories with {args.workers} workers...")
        with mp.Pool(args.workers) as pool:
            results = pool.map(_generate_one, work)
        trajectories = [r for r in results if r is not None]
    else:
        trajectories = []
        for item in work:
            result = _generate_one(item)
            if result is not None:
                trajectories.append(result)

    # Shuffle
    rng = Random(args.shuffle_seed)
    rng.shuffle(trajectories)

    with open(output_path, "w") as f:
        for t in trajectories:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")

    total_msgs = sum(len(t["messages"]) for t in trajectories)
    avg_score = (sum(t["score"] for t in trajectories) / len(trajectories)
                 if trajectories else 0)
    print(f"\nGenerated {len(trajectories)} trajectories → {output_path}")
    print(f"  Avg messages: {total_msgs / len(trajectories):.0f}")
    print(f"  Avg score: {avg_score:.2f}")


if __name__ == "__main__":
    main()
