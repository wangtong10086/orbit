"""ms-swift gym plugin bindings for the MemoryGym environment pack."""

from __future__ import annotations

import re
from typing import Any

from .codec import parse_memorygym_action
from .telemetry import build_memorygym_telemetry

# Strip <think>...</think> blocks that Qwen3 thinking models generate.
# These blocks consume max_completion_length budget and must be removed
# before parsing tool calls.
_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)

# Detect event boundary observations (new stream events).
_EVENT_BOUNDARY_RE = re.compile(r"^=== Event \d+/\d+")

try:
    from swift.rollout import ContextManager, Env, context_managers, envs
    from swift.infer_engine.protocol import RolloutInferRequest
    from swift.template import Messages
except ImportError:  # pragma: no cover
    RolloutInferRequest = Any  # type: ignore[assignment]
    Messages = list  # type: ignore[assignment]

    class ContextManager:  # type: ignore[no-redef]
        def __init__(self, ctx_config):
            self.ctx_config = ctx_config

        def manage_context(self, history, trajectory_id):
            return history

    class Env:  # type: ignore[no-redef]
        def __init__(self, env_config):
            self.env_config = env_config

    context_managers: dict[str, Any] = {}
    envs: dict[str, Any] = {}


def _env_defaults(env_config: dict[str, Any]) -> dict[str, Any]:
    return {
        "template_name": env_config.get("template_name", env_config.get("template", "company")),
        "tier": env_config.get("tier", "standard"),
        "seed": int(env_config.get("seed", 0)),
        "reward_mode": env_config.get("reward_mode", "binary"),
        "backend_type": env_config.get("backend_type", "chromadb"),
    }


class MemoryGymRedactContext(ContextManager):
    """Context manager with event-boundary redaction.

    Aligned with online evaluation's nuclear redaction: at each event
    boundary only system prompt + current event observation are kept.
    Within the same event, recent messages (tool results, assistant
    actions) are preserved so the model can do multi-step tool use.
    """

    def manage_context(self, history: Messages, trajectory_id: str) -> Messages:  # type: ignore[override]
        if len(history) <= 2:
            return history

        last_msg = history[-1]
        content = ""
        if isinstance(last_msg, dict):
            content = str(last_msg.get("content", ""))

        # At event boundaries (new event observation), redact everything
        # between system prompt and the current event.
        if _EVENT_BOUNDARY_RE.match(content) or content == "Episode complete.":
            return [history[0], last_msg]

        # Within the same event: keep system + messages since last event
        # boundary so the model sees its tool results.
        start_idx = 1
        for i in range(len(history) - 2, 0, -1):
            msg = history[i]
            if isinstance(msg, dict):
                msg_content = str(msg.get("content", ""))
                if _EVENT_BOUNDARY_RE.match(msg_content):
                    start_idx = i
                    break

        return [history[0]] + history[start_idx:]


class MemoryGymPassthroughContext(ContextManager):
    """Legacy passthrough context manager (no redaction)."""

    def manage_context(self, history: Messages, trajectory_id: str) -> Messages:  # type: ignore[override]
        return history


class MemoryGymEnv(Env):
    def __init__(self, env_config):
        super().__init__(env_config)
        self._env = None
        self._defaults = _env_defaults(env_config or {})
        self._merged_env_config = dict(self._defaults)
        # Allow launch config to force tier regardless of per-row env_config
        self._tier_override = (env_config or {}).get("tier_override")

    async def reset(self, config: RolloutInferRequest):  # type: ignore[override]
        from memorygym.adapters._common import get_system_prompt
        from memorygym.training import MemoryEnv

        row_config = dict((getattr(config, "data_dict", {}) or {}).get("env_config") or {})
        merged = {**self._defaults, **row_config}
        if self._tier_override:
            merged["tier"] = self._tier_override
        self._merged_env_config = dict(merged)
        self._env = MemoryEnv(
            template_name=merged["template_name"],
            tier=merged["tier"],
            seed=int(merged["seed"]),
            reward_mode=merged["reward_mode"],
            backend_type=merged["backend_type"],
        )
        observation = self._env.reset(seed=int(merged["seed"]))
        info = {
            "template": merged["template_name"],
            "tier": merged["tier"],
            "seed": int(merged["seed"]),
            "terminated": False,
        }
        system_message = get_system_prompt(self._env.write_budget)
        return str(observation), info, system_message

    def _memory_summary(self) -> str:
        """Generate memory state summary aligned with eval's redaction."""
        stored = sorted(self._env._stored_entity_names) if self._env._stored_entity_names else []
        remaining = self._env.write_budget - self._env._writes_used
        names_str = ", ".join(stored) if stored else "(none)"
        return f"Current stored entities: {names_str}\nBudget: {remaining} writes remaining"

    async def step(self, action: Messages):  # type: ignore[override]
        if self._env is None:
            raise RuntimeError("MemoryGymEnv.step() called before reset()")

        assistant_text = ""
        if action:
            last_message = action[-1]
            if isinstance(last_message, dict):
                assistant_text = str(last_message.get("content", "") or "")

        # Strip <think>...</think> blocks so tool-call parsing sees
        # only the action portion.  Without this, Qwen3 thinking
        # output consumes the entire completion and the parser falls
        # back to {"tool": "next"}, producing reward = 0.
        assistant_text = _THINK_RE.sub("", assistant_text)

        parsed_action = parse_memorygym_action(assistant_text)
        next_obs, _step_reward, done, info = self._env.step(parsed_action)
        reward = float(self._env.get_verifiable_reward()) if done else 0.0

        tool = parsed_action.get("tool", "next")
        if done:
            observation = "Episode complete."
        elif tool in ("next", "submit_answer"):
            # Event boundary: prepend memory summary (aligned with eval
            # redaction which injects stored-entity list between events).
            summary = self._memory_summary()
            observation = f"{summary}\n\n{str(next_obs)}"
        else:
            # Tool execution: show formatted tool result so the model
            # sees feedback (aligned with eval's tool-result messages).
            from memorygym.adapters._common import format_tool_result
            observation = format_tool_result(parsed_action, info)

        telemetry = build_memorygym_telemetry(
            info=dict(info or {}),
            parsed_action=parsed_action,
            done=bool(done),
            template_name=self._merged_env_config.get("template_name", ""),
            tier=self._merged_env_config.get("tier", ""),
            seed=int(self._merged_env_config.get("seed", 0)),
        )
        if done:
            return observation, reward, True, telemetry
        return observation, reward, False, telemetry

    async def close(self):  # type: ignore[override]
        if self._env is not None:
            close = getattr(self._env, "close", None)
            if callable(close):
                close()
            self._env = None


def register_ms_swift_plugin() -> None:
    context_managers["memorygym_passthrough"] = MemoryGymPassthroughContext
    context_managers["memorygym_redact"] = MemoryGymRedactContext
    envs["memorygym_env"] = MemoryGymEnv
    # Keep the ORBIT data label stable while exposing the backend-facing gym env id.
    envs["MEMORYGYM"] = MemoryGymEnv


__all__ = [
    "MemoryGymEnv",
    "MemoryGymPassthroughContext",
    "register_ms_swift_plugin",
]
