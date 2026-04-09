from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np


SYSTEM_PROMPTS = {
    "othello": """You are playing othello.

OTHELLO (REVERSI) RULES:
Board: 8×8 grid. 2 players (Black and White). Start with 4 discs in center (2 black, 2 white diagonal).
Goal: Have more discs of your color when board is full or no moves available.

Turn: Place disc to sandwich opponent's discs between your new disc and existing disc (horizontally, vertically, or diagonally). All sandwiched opponent discs flip to your color.
Must flip at least 1 disc; if no valid move, pass turn.

Winning: Player with most discs when game ends wins.

# Output Format
You must respond with ONLY the action ID (a single number).
Do NOT include descriptions or explanations.

Examples:
- For action "0 -> roll": respond "0"
- For action "89 -> a3": respond "89"
""",
    "clobber": """You are playing clobber.

CLOBBER RULES:
Board: Rectangular grid (5×5, 6×6, or 7×7) filled with alternating black and white pieces.
Goal: Be the last player able to move.

Movement: On your turn, move one of your pieces orthogonally (horizontally or vertically) to capture an adjacent opponent piece. The captured piece is removed and replaced by your piece.
Must capture: Every move must capture an opponent piece. No non-capturing moves allowed.

Important: You can ONLY move to a position occupied by an opponent piece that is directly adjacent (up/down/left/right) to one of your pieces.

Losing: If you have no legal moves (no adjacent opponent pieces to capture), you lose.

# Output Format
You must respond with ONLY the action ID (a single number).
Do NOT include descriptions or explanations.

Examples:
- For action "0 -> roll": respond "0"
- For action "89 -> a3": respond "89"
""",
}

GAME_IDX = {
    "othello": 4,
    "clobber": 7,
}


def _stable_seed(sample_key: str) -> int:
    digest = hashlib.blake2b(sample_key.encode("utf-8"), digest_size=8).hexdigest()
    return int(digest, 16) % (2**31 - 1)


def _othello_coord(action_id: int) -> str:
    if int(action_id) == 64:
        return "pass"
    row, col = divmod(int(action_id), 8)
    return f"{chr(ord('a') + col)}{row + 1}"


def _clobber_coord(row: int, col: int, board_h: int) -> str:
    return f"{chr(ord('a') + col)}{board_h - row}"


def _clobber_action_str(action_id: int, board_h: int, board_w: int) -> str:
    square_index, direction = divmod(int(action_id), 4)
    row, col = divmod(square_index, board_w)
    deltas = {0: (-1, 0), 1: (0, 1), 2: (1, 0), 3: (0, -1)}
    dst_row = row + deltas[direction][0]
    dst_col = col + deltas[direction][1]
    return f"{_clobber_coord(row, col, board_h)}{_clobber_coord(dst_row, dst_col, board_h)}"


def _othello_board(obs: np.ndarray, player: int) -> str:
    own = obs[0, :8, :8]
    opp = obs[1, :8, :8]
    own_symbol = "x" if int(player) == 0 else "o"
    opp_symbol = "o" if own_symbol == "x" else "x"
    rows = []
    for row in range(8):
        cells = []
        for col in range(8):
            if own[row, col] > 0.5:
                cells.append(own_symbol)
            elif opp[row, col] > 0.5:
                cells.append(opp_symbol)
            else:
                cells.append("-")
        rows.append(f"{row + 1} " + " ".join(cells) + f" {row + 1}")
    header = "  a b c d e f g h  "
    player_label = "Black (x)" if int(player) == 0 else "White (o)"
    return f"{player_label} to play:\n{header}\n" + "\n".join(rows) + f"\n{header}"


def _clobber_board(obs: np.ndarray, player: int) -> tuple[str, int, int]:
    valid = obs[3]
    coords = np.argwhere(valid > 0.5)
    board_h = int(coords[:, 0].max()) + 1
    board_w = int(coords[:, 1].max()) + 1
    own = obs[0, :board_h, :board_w]
    opp = obs[1, :board_h, :board_w]
    own_symbol = "x" if int(player) == 0 else "o"
    opp_symbol = "o" if own_symbol == "x" else "x"
    lines = []
    for row in range(board_h):
        cells = []
        for col in range(board_w):
            if own[row, col] > 0.5:
                cells.append(own_symbol)
            elif opp[row, col] > 0.5:
                cells.append(opp_symbol)
            else:
                cells.append(".")
        lines.append(f"{board_h - row}{''.join(cells)}")
    lines.append(" " + "".join(chr(ord("a") + col) for col in range(board_w)))
    return "\n".join(lines) + "\n", board_h, board_w


def _sample_to_turn(*, game: str, sample: dict[str, object]) -> tuple[str, str]:
    player = int(sample["agent_player"])
    obs = np.asarray(sample["obs"])
    legal_mask = np.asarray(sample["legal_mask"])
    action = int(sample["action"])

    if game == "othello":
        board_str = _othello_board(obs, player)
        legal_actions = [idx for idx, value in enumerate(legal_mask.tolist()) if value > 0.5]
        legal_desc = "\n".join(f"{idx} -> {_othello_coord(idx)}" for idx in legal_actions)
    elif game == "clobber":
        board_str, board_h, board_w = _clobber_board(obs, player)
        legal_actions = [idx for idx, value in enumerate(legal_mask.tolist()) if value > 0.5]
        legal_desc = "\n".join(f"{idx} -> {_clobber_action_str(idx, board_h, board_w)}" for idx in legal_actions)
    else:
        raise KeyError(game)

    user = f"Current State:\n{board_str}\n\nYou are Player {player}.\nLegal Actions:\n{legal_desc}\n\nYour choice (ID only):"
    assistant = str(action)
    return user, assistant


def _load_game_index(root: Path) -> dict[str, dict[int, dict[str, object]]]:
    game_index: dict[str, dict[int, dict[str, object]]] = defaultdict(dict)
    for path in sorted(root.rglob("winning_games.jsonl")):
        rel_parent = str(path.parent.relative_to(root))
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                game_index[rel_parent][int(row["game_index"])] = row
    return game_index


def _load_sample_groups(root: Path) -> dict[str, dict[int, list[dict[str, object]]]]:
    grouped: dict[str, dict[int, list[dict[str, object]]]] = defaultdict(lambda: defaultdict(list))
    for npz_path in sorted(root.rglob("winning_agent_samples_*.npz")):
        rel_parent = str(npz_path.parent.parent.relative_to(root)) if npz_path.parent.name == "winning_agent_samples" else str(npz_path.parent.relative_to(root))
        payload = dict(np.load(npz_path))
        rows = int(payload["action"].shape[0])
        for index in range(rows):
            game_index = int(payload["game_index"][index])
            grouped[rel_parent][game_index].append(
                {
                    "obs": payload["obs"][index],
                    "legal_mask": payload["legal_mask"][index],
                    "action": int(payload["action"][index]),
                    "agent_player": int(payload["agent_player"][index]),
                    "variant_id": int(payload["variant_id"][index]),
                    "move_index": int(payload["move_index"][index]),
                }
            )
    for parent_groups in grouped.values():
        for rows in parent_groups.values():
            rows.sort(key=lambda item: int(item["move_index"]))
    return grouped


def _convert_root(root: Path, *, game: str, output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    game_index = _load_game_index(root)
    sample_groups = _load_sample_groups(root)
    total = 0
    with output_path.open("w", encoding="utf-8") as handle:
        for rel_parent in sorted(sample_groups):
            for game_id in sorted(sample_groups[rel_parent]):
                samples = sample_groups[rel_parent][game_id]
                if not samples:
                    continue
                meta = game_index.get(rel_parent, {}).get(game_id, {})
                first = samples[0]
                messages = [{"role": "system", "content": SYSTEM_PROMPTS[game]}]
                for sample in samples:
                    user, assistant = _sample_to_turn(game=game, sample=sample)
                    messages.append({"role": "user", "content": user})
                    messages.append({"role": "assistant", "content": assistant})
                record_key = f"{game}:{rel_parent}:{game_id}:{int(first['agent_player'])}"
                seed = _stable_seed(record_key)
                record = {
                    "messages": messages,
                    "env": "GAME",
                    "source": "v11_no_think",
                    "game": game,
                    "score": 1,
                    "task_id": GAME_IDX[game] * 100_000_000 + (seed % 100_000_000),
                    "seed": seed,
                }
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                total += 1
    return total


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert MuZero MCTS-win trajectories to GAME JSONL")
    parser.add_argument("--othello-root", required=True)
    parser.add_argument("--clobber-root", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    output = Path(args.output)
    out_othello = output.with_name(output.stem + "_othello.jsonl")
    out_clobber = output.with_name(output.stem + "_clobber.jsonl")
    othello_records = _convert_root(Path(args.othello_root), game="othello", output_path=out_othello)
    clobber_records = _convert_root(Path(args.clobber_root), game="clobber", output_path=out_clobber)
    with output.open("w", encoding="utf-8") as merged:
        for part in (out_othello, out_clobber):
            with part.open("r", encoding="utf-8") as source:
                for line in source:
                    merged.write(line)
    print(json.dumps({"output": str(output), "othello_records": othello_records, "clobber_records": clobber_records}, ensure_ascii=False))


if __name__ == "__main__":
    main()
