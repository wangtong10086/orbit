#!/usr/bin/env python3
"""
GAME strategy injector — injects game-specific <think> reasoning into high-score DDB samples

No LLM calls; generates strategy reasoning directly from game rules.
Each game has a dedicated strategy function that generates reasoning based on game state and correct action.

Usage:
    python3 scripts/game_strategy_inject.py -o data/game_strategy_cot.jsonl
"""

import json
import re
import argparse
from pathlib import Path


GAMES_LIST = ['goofspiel','liars_dice','leduc_poker','gin_rummy','othello',
              'backgammon','hex','clobber','hearts','euchre','dots_and_boxes',
              'go','chess','checkers','quoridor','blackjack','phantom_ttt',
              '2048','solitaire','bridge','amazons','oware']

# 7 active games
ACTIVE_GAMES = {'goofspiel','liars_dice','leduc_poker','gin_rummy','othello','hex','clobber'}


def think_leduc_poker(user_msg: str, action: str) -> str:
    """Leduc Poker: 6 cards (JQK x2), simple strategy table"""
    card = ""
    public = ""
    if m := re.search(r"Your card: (\w)♥|Your card: (\w)♠", user_msg):
        card = m.group(1) or m.group(2)
    if m := re.search(r"Public card: (\w)", user_msg):
        public = m.group(1)

    rank = {"K": 3, "Q": 2, "J": 1}.get(card, 0)
    has_pair = card == public

    if has_pair:
        return f"<think>I have {card}, public card is also {card}, forming a pair. Pairs are very strong in Leduc, should raise.</think>\n{action}"
    elif card == "K":
        if "Raise" in action or action == "2":
            return f"<think>I have K, the strongest single card. High win rate even without a pair, raise to pressure opponent.</think>\n{action}"
        else:
            return f"<think>I have K, strongest card, call and observe opponent's reaction.</think>\n{action}"
    elif card == "Q":
        if public:
            if public == "K":
                return f"<think>I have Q, public card K no pair. Q is medium strength, opponent may have K, call cautiously.</think>\n{action}"
            else:
                return f"<think>I have Q, public card {public}, Q beats J. Medium hand strength, call based on pot odds.</think>\n{action}"
        return f"<think>Round 1, I have Q, medium strength. Small bet or call to probe.</think>\n{action}"
    elif card == "J":
        if "Fold" in action or action == "0":
            return f"<think>I have J, weakest card. Opponent raised, odds insufficient, fold to cut losses.</think>\n{action}"
        else:
            return f"<think>I have J, weakest card but pot odds are barely sufficient, reluctantly call.</think>\n{action}"
    return f"<think>Analyze the situation and choose the optimal action.</think>\n{action}"


def think_liars_dice(user_msg: str, action: str) -> str:
    """Liar's Dice: probability estimation + call liar threshold"""
    dice = []
    if m := re.search(r"Your dice: \[([^\]]+)\]", user_msg):
        dice = [int(x.strip()) for x in m.group(1).split(",")]

    total_dice = 10
    if m := re.search(r"Total dice in game: (\d+)", user_msg):
        total_dice = int(m.group(1))

    bid_match = re.search(r'"(\d+)-(\d+)".*claiming at least (\d+) dice showing (\d+)', user_msg)
    if bid_match:
        bid_qty = int(bid_match.group(3))
        bid_face = int(bid_match.group(4))
        my_count = dice.count(bid_face)
        # Expected count in opponent's dice: (total-my_dice) * 1/6
        opponent_dice = total_dice - len(dice)
        expected = my_count + opponent_dice / 6.0
        prob_true = min(expected / bid_qty, 1.0) if bid_qty > 0 else 1.0

        if "Call" in user_msg and ("0" in action or "Liar" in action.lower() or int(action) >= 50):
            return f"<think>Opponent claims {bid_qty} dice showing {bid_face}. I have {my_count}, expected total {expected:.1f}. {bid_qty} is unlikely (probability {prob_true:.0%}), call Liar.</think>\n{action}"
        else:
            return f"<think>Opponent claims {bid_qty} dice showing {bid_face}. I have {my_count}, seems reasonable. I raise with a higher bid.</think>\n{action}"

    return f"<think>Based on my dice {dice} and total dice count {total_dice}, estimate probabilities and make the optimal decision.</think>\n{action}"


def think_goofspiel(user_msg: str, action: str) -> str:
    """Goofspiel: bid proportionally to prize value"""
    prize = 0
    if m := re.search(r"Prize card: (\d+)", user_msg):
        prize = int(m.group(1))

    bid = action.strip()
    if prize >= 8:
        return f"<think>Prize card worth {prize} points, high value. Bid {bid} aggressively, worth the investment.</think>\n{action}"
    elif prize >= 5:
        return f"<think>Prize card worth {prize} points, medium value. Bid {bid} moderately, avoid overcommitting.</think>\n{action}"
    else:
        return f"<think>Prize card worth {prize} points, low value. Bid low with {bid}, save high cards for later.</think>\n{action}"


def think_othello(user_msg: str, action: str) -> str:
    """Othello: corners best > edges > center, avoid giving opponent corners"""
    action_id = int(action.strip())
    row, col = action_id // 8, action_id % 8
    corners = {(0,0), (0,7), (7,0), (7,7)}
    edges = {(r,c) for r in [0,7] for c in range(8)} | {(r,c) for c in [0,7] for r in range(8)}
    # X-squares (adjacent to corners, very bad to play)
    x_squares = {(1,1), (1,6), (6,1), (6,6)}

    if (row, col) in corners:
        return f"<think>Corner position ({row},{col})! Corners can never be flipped, strongest position. Must take it.</think>\n{action}"
    elif (row, col) in edges:
        return f"<think>Edge position ({row},{col}), stable and hard to flip. Good choice.</think>\n{action}"
    elif (row, col) in x_squares:
        return f"<think>Position ({row},{col}) near corner, usually risky but may be the best capture currently.</think>\n{action}"
    else:
        return f"<think>Center area ({row},{col}), choose position that flips the most opponent pieces.</think>\n{action}"


def think_hex(user_msg: str, action: str) -> str:
    """Hex: occupy center + bridge pattern + connection strategy"""
    action_id = int(action.strip())
    # Hex board size varies, assume extracted from context
    board_size = 5
    if m := re.search(r"(\d+)x(\d+)", user_msg):
        board_size = int(m.group(1))

    center = board_size // 2
    row, col = action_id // board_size, action_id % board_size
    dist_center = abs(row - center) + abs(col - center)

    if dist_center <= 1:
        return f"<think>Center position ({row},{col}), controlling the center is crucial in Hex, enables the most connection paths.</think>\n{action}"
    elif dist_center <= 2:
        return f"<think>Near center ({row},{col}), extend connections while blocking opponent's paths.</think>\n{action}"
    else:
        return f"<think>Position ({row},{col}), extend my connection chain toward the target edge.</think>\n{action}"


def think_clobber(user_msg: str, action: str) -> str:
    """Clobber: maintain connectivity + capture isolated pieces"""
    return f"<think>Choose to capture opponent's piece while keeping our pieces connected. Prioritize capturing isolated opponent pieces.</think>\n{action}"


def think_gin_rummy(user_msg: str, action: str) -> str:
    """Gin Rummy: meld recognition + deadwood minimization"""
    if "knock" in user_msg.lower() or "Knock" in user_msg:
        return f"<think>Hand deadwood is <=10, can knock. Check meld combinations (runs/sets), confirm knocking is favorable.</think>\n{action}"
    elif "draw" in user_msg.lower() or "Draw" in user_msg or "pick" in user_msg.lower():
        return f"<think>Choose draw source: can the discard pile card form a meld? If so take from discard pile, otherwise draw from stock.</think>\n{action}"
    else:
        return f"<think>Discard the highest deadwood card, keep cards that can form melds. Prioritize keeping potential runs and sets.</think>\n{action}"


STRATEGY_FUNCS = {
    "leduc_poker": think_leduc_poker,
    "liars_dice": think_liars_dice,
    "goofspiel": think_goofspiel,
    "othello": think_othello,
    "hex": think_hex,
    "clobber": think_clobber,
    "gin_rummy": think_gin_rummy,
}


def inject_strategy(record: dict, game_name: str) -> dict:
    """Inject game-specific <think> tags into assistant messages."""
    func = STRATEGY_FUNCS.get(game_name)
    if not func:
        return record

    messages = record["messages"]
    new_msgs = []
    for i, msg in enumerate(messages):
        if msg["role"] == "assistant":
            action = msg["content"].strip()
            # Find preceding user message for context
            user_msg = ""
            for j in range(i - 1, -1, -1):
                if messages[j]["role"] == "user":
                    user_msg = messages[j]["content"]
                    break
            think_action = func(user_msg, action)
            new_msgs.append({"role": "assistant", "content": think_action})
        else:
            new_msgs.append(msg)

    record["messages"] = new_msgs
    return record


def main():
    parser = argparse.ArgumentParser(description="GAME strategy injector")
    parser.add_argument("-o", "--output", default="data/game_strategy_cot.jsonl")
    parser.add_argument("--input", default="data/game_sft.jsonl")
    args = parser.parse_args()

    with open(args.input) as f:
        records = [json.loads(l) for l in f]

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    stats = {}
    with open(output_path, "w") as out:
        for r in records:
            tid = r.get("task_id", 0)
            idx = tid // 100_000_000
            if idx >= len(GAMES_LIST):
                continue
            game_name = GAMES_LIST[idx]

            if game_name not in ACTIVE_GAMES:
                continue

            r["game"] = game_name
            r = inject_strategy(r, game_name)
            r["source"] = "ddb_strategy_cot"
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
            stats[game_name] = stats.get(game_name, 0) + 1

    total = sum(stats.values())
    print(f"Generated {total} strategy-annotated samples:")
    for g, c in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {g}: {c}")


if __name__ == "__main__":
    main()
