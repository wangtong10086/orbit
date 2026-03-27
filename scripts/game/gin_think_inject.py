#!/usr/bin/env python3
"""Inject rule-based think blocks into v11 gin_rummy data (no pyspiel needed).

Parses game state from user messages and generates strategic reasoning
for each action. Critical: teaches model WHEN to knock.

Usage:
    python3 gin_think_inject.py data/canonical/game.jsonl -o data/gin_rummy_with_think.jsonl
"""

import json
import re
import sys
import argparse


def parse_gin_state(user_msg):
    """Extract game state from user message."""
    state = {}

    # Knock card threshold
    m = re.search(r'Knock card:\s*(\d+)', user_msg)
    state['knock_card'] = int(m.group(1)) if m else 10

    # Deadwood
    m = re.search(r'Deadwood=(\d+)', user_msg)
    state['deadwood'] = int(m.group(1)) if m else None

    # Phase
    m = re.search(r'Phase:\s*(\w+)', user_msg)
    state['phase'] = m.group(1) if m else ''

    # Upcard
    m = re.search(r'Upcard:\s*(\S+)', user_msg)
    state['upcard'] = m.group(1) if m else 'XX'

    # Stock size
    m = re.search(r'Stock size:\s*(\d+)', user_msg)
    state['stock_size'] = int(m.group(1)) if m else 0

    # Parse hand from card grid (Player1 section)
    hand_cards = []
    card_pattern = re.compile(r'[AKQJT2-9][shdc]')
    # Find the player's hand section
    player_section = re.search(r'Player\d+: Deadwood=\d+\n([\s\S]*?)(?:\n\n|$)', user_msg)
    if player_section:
        hand_cards = card_pattern.findall(player_section.group(1))
    state['hand'] = hand_cards

    # Legal actions
    actions = {}
    for line in user_msg.split('\n'):
        m = re.match(r'(\d+)\s*->\s*(.*)', line.strip())
        if m:
            actions[int(m.group(1))] = m.group(2).strip()
    state['legal_actions'] = actions

    return state


def card_value(card):
    """Get deadwood value of a card."""
    rank = card[0]
    if rank in 'TJQK':
        return 10
    if rank == 'A':
        return 1
    return int(rank)


def generate_think(state, action):
    """Generate rule-based think block for a gin_rummy action."""
    dw = state.get('deadwood')
    kc = state['knock_card']
    phase = state['phase']
    upcard = state['upcard']
    hand = state['hand']
    legal = state['legal_actions']
    stock = state.get('stock_size', 0)

    can_knock = 55 in legal
    is_knock = (action == 55)
    is_draw_upcard = (action == 52)
    is_draw_stock = (action == 53)
    is_first_upcard = (action == 54)  # pass on first upcard
    is_discard = (action < 52)

    parts = []

    # Always report deadwood and threshold
    if dw is not None:
        parts.append(f"Deadwood: {dw}, knock threshold: {kc}.")

    if is_knock:
        parts.append(f"Deadwood {dw} ≤ {kc} → KNOCK NOW. Waiting risks opponent improving their hand.")
        return " ".join(parts)

    if can_knock and not is_knock:
        # Model chose NOT to knock when it could — explain why
        parts.append(f"Can knock (deadwood {dw} ≤ {kc}), but continuing to improve hand.")

    if phase == 'FirstUpcard':
        if action == 52:
            parts.append(f"First upcard {upcard}.")
            if hand:
                uv = card_value(upcard)
                parts.append(f"Taking upcard ({upcard}, value {uv}) — may form a meld.")
            else:
                parts.append("Taking upcard to start.")
        elif action == 54:
            parts.append(f"First upcard {upcard}. Passing — doesn't help my hand.")
        return " ".join(parts)

    if phase == 'Draw':
        if is_draw_upcard:
            parts.append(f"Upcard {upcard} visible.")
            if hand:
                # Check if upcard matches anything in hand
                upcard_rank = upcard[0] if upcard != 'XX' else ''
                upcard_suit = upcard[1] if len(upcard) > 1 and upcard != 'XX' else ''
                matching_ranks = [c for c in hand if c[0] == upcard_rank]
                if matching_ranks:
                    parts.append(f"Have {', '.join(matching_ranks)} — {upcard} forms a set → DRAW UPCARD.")
                else:
                    parts.append(f"Drawing upcard {upcard} to reduce deadwood or form a run.")
            else:
                parts.append(f"Drawing upcard {upcard}.")
        elif is_draw_stock:
            parts.append(f"Upcard {upcard} doesn't help. Drawing from stock ({stock} cards left).")
        return " ".join(parts)

    if phase == 'Discard':
        if is_discard:
            # Find what card is being discarded
            action_desc = legal.get(action, '')
            card_match = re.search(r'([AKQJT2-9][shdc])', action_desc)
            discard_card = card_match.group(1) if card_match else f"action {action}"
            dv = card_value(discard_card) if card_match else 0

            parts.append(f"Discarding {discard_card} (value {dv}).")
            if dv >= 10:
                parts.append("High deadwood card — removing to reduce deadwood.")
            elif hand:
                parts.append("Doesn't contribute to any meld.")
        return " ".join(parts)

    # Fallback
    if dw is not None and dw <= kc and can_knock:
        parts.append(f"Deadwood {dw} ≤ {kc} — should knock.")
    else:
        parts.append("Playing best available action.")

    return " ".join(parts)


def process_file(input_path, output_path):
    """Process gin_rummy entries: inject think blocks."""
    gin_count = 0
    think_added = 0
    knock_thinks = 0

    with open(input_path) as fin, open(output_path, 'w') as fout:
        for line in fin:
            entry = json.loads(line)
            msgs = entry.get('messages', [])
            is_gin = any('gin_rummy' in (m.get('content', '') or '').lower() for m in msgs)

            if not is_gin:
                fout.write(line)
                continue

            gin_count += 1
            new_msgs = []
            last_user_state = None

            for m in msgs:
                if m['role'] == 'user':
                    last_user_state = parse_gin_state(m.get('content', ''))
                    new_msgs.append(m)
                elif m['role'] == 'assistant':
                    content = (m.get('content', '') or '').strip()
                    if content.isdigit() and last_user_state:
                        action = int(content)
                        think = generate_think(last_user_state, action)
                        if think:
                            think_added += 1
                            if action == 55:
                                knock_thinks += 1
                            new_msgs.append({
                                'role': 'assistant',
                                'content': f'<think>{think}</think>\n{content}'
                            })
                        else:
                            new_msgs.append(m)
                    else:
                        new_msgs.append(m)
                else:
                    new_msgs.append(m)

            entry['messages'] = new_msgs
            entry['source'] = entry.get('source', '') + '_think_injected'
            fout.write(json.dumps(entry, ensure_ascii=False) + '\n')

    print(f"Processed {gin_count} gin_rummy entries")
    print(f"Think blocks added: {think_added}")
    print(f"Knock thinks: {knock_thinks}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('input', help='Input JSONL file')
    parser.add_argument('-o', '--output', required=True, help='Output JSONL file')
    args = parser.parse_args()
    process_file(args.input, args.output)
