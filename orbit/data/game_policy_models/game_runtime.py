"""Explicit adapter for GAME script/runtime symbols used by self-play."""

from __future__ import annotations

from functools import lru_cache

from orbit.data.game_generators.base import ensure_game_scripts_path


@lru_cache(maxsize=1)
def load_game_runtime_symbols() -> dict[str, object]:
    ensure_game_scripts_path()
    from generate_v11 import GAME_IDX, GAME_RULES, SYSTEM_PROMPT_TEMPLATE, make_mcts_bot, make_user_prompt  # type: ignore

    return {
        "GAME_IDX": GAME_IDX,
        "GAME_RULES": GAME_RULES,
        "SYSTEM_PROMPT_TEMPLATE": SYSTEM_PROMPT_TEMPLATE,
        "make_mcts_bot": make_mcts_bot,
        "make_user_prompt": make_user_prompt,
    }
