"""Minimal OpenEnv-based SWE synthesis controller.

This stays above upstream `SWE-INFINITE` as a thin orchestration layer:
- uses upstream OpenEnv reset/state/checkpoint/restore/step/stop
- uses a single OpenAI-compatible model as the action generator
- records raw events and a small run manifest

The goal is to validate real synthesis with checkpoint/retry/rollback without
reintroducing ORBIT-side environment semantics.
"""

from __future__ import annotations

import copy
from functools import lru_cache
import json
import os
import re
import shlex
import time
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request
from pathlib import Path
from typing import Any

from openai import OpenAI
try:
    import yaml
except Exception:  # pragma: no cover - optional dependency in lightweight remote venvs
    yaml = None

try:
    from jinja2 import StrictUndefined, Template
except Exception:  # pragma: no cover - optional dependency in lightweight remote venvs
    StrictUndefined = None
    Template = None

try:
    from transformers import AutoTokenizer
except Exception:  # pragma: no cover - optional dependency in lightweight remote venvs
    AutoTokenizer = None

from .runner import (
    DEFAULT_AFFINETES_GIT_URL,
    DEFAULT_SWE_CACHE_DIR,
    openenv_checkpoint,
    openenv_reset,
    openenv_restore,
    openenv_state,
    openenv_step,
    openenv_stop,
)


TEACHER_CONTROLLER_SYSTEM_PROMPT = """You are the privileged controller-policy model for an ORBIT SWE synthesis run over an upstream SWE-INFINITE OpenEnv episode.

You are NOT allowed to output shell commands.
You are NOT allowed to rewrite the student prompt template.
You are ONLY allowed to influence the run in two ways:
1. choose whether to continue from CURRENT, restore to BASELINE, roll back to one of the recent edit checkpoints, or STOP the run
2. optionally provide hidden guidance text for the next student's THOUGHT

Return exactly one JSON object with this schema:
{
  "restore_target": "CURRENT" | "BASELINE" | "ROLLBACK_1" | "ROLLBACK_2" | "ROLLBACK_3" | "ROLLBACK_4" | "STOP",
  "inject_teacher_think": boolean,
  "teacher_think_text": string,
  "stall_class": "none" | "no_action" | "repeat_read_loop" | "repeat_search_loop" | "stuck_patch" | "bad_patch_loop" | "verify_loop",
  "reason": string
}

Rules:
- Use CURRENT when the student should continue from the current state.
- Use BASELINE only when the controller should restore the clean baseline checkpoint before the next student step.
- Use ROLLBACK_1 as the most recent edit checkpoint, ROLLBACK_2 as the second most recent, and so on.
- Use STOP only when the run should terminate because the student is stuck in a bad pattern and further retries are unlikely to help.
- When a plausible patch already exists, strongly prefer CURRENT over rollback. A single read or verification step after a fresh patch is normal and should not trigger rollback.
- Use rollback only when there is concrete evidence the current patch lineage is wrong or corrupted, or when the student has repeated the same unchanged-patch read/verify behavior multiple times.
- If the current patch looks plausible, prefer CURRENT plus short hidden guidance that pushes the student toward one focused verification step and then submission.
- Treat `latest_changed_files`, `last_patch_hash`, `patch_status`, and `last_state_payload.info.changed_files` as the source of truth for whether a patch really exists.
- If `latest_changed_files` is empty, do not claim that a file was created or that a patch was applied successfully.
- Do not request rollback or STOP solely because the student is locally rereading or verifying a fresh plausible patch once.
- If restore_target is not CURRENT, inject_teacher_think must be false and teacher_think_text must be empty.
- If inject_teacher_think is false, teacher_think_text must be empty.
- teacher_think_text must be short hidden guidance for the student's next THOUGHT only, not a command.
- Use all provided privileged controller state and history.
- Return JSON only. No markdown, no prose, no code fences.
"""

UPSTREAM_SUBMIT_COMMAND = "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && git add -A && git diff --cached"
BASELINE_CHECKPOINT_RETRIES = 3
BASELINE_CHECKPOINT_RETRY_DELAY_SECS = 2.0
BASELINE_CHECKPOINT_INITIAL_DELAY_SECS = 8.0
BASELINE_RESET_RESTART_RETRIES = 3
MAX_EDIT_CHECKPOINTS = 4
MAX_TOTAL_RESTORES_PER_RUN = 6
MAX_SAME_LINEAGE_RETRIES = 2
STUDENT_MAX_CONTEXT_TOKENS_DEFAULT = 65536
TRANSPORT_RETRY_PATTERNS = (
    "request timed out",
    "connection timed out",
    "connection error",
    "connection refused",
    "connection reset",
    "read timeout",
)


def _ensure_dir(path: str) -> Path:
    root = Path(path).resolve()
    (root / "raw").mkdir(parents=True, exist_ok=True)
    (root / "manifests").mkdir(parents=True, exist_ok=True)
    return root


def _read_api_key(*, api_key: str = "", api_key_file: str = "") -> str:
    if api_key:
        return api_key
    if api_key_file:
        return Path(api_key_file).read_text(encoding="utf-8").strip()
    return ""


def _is_retryable_checkpoint_failure(payload: dict[str, Any]) -> bool:
    info = payload.get("info")
    if not isinstance(info, dict):
        return False
    error = info.get("error")
    if not isinstance(error, dict):
        return False
    if bool(error.get("retryable")):
        return True
    message = str(error.get("message") or "")
    return "No such container" in message


def _extract_text(payload: dict[str, Any]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()
    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError("chat completion returned no choices")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
        text = "".join(parts).strip()
        if text:
            return text
    raise RuntimeError("chat completion returned no text content")


def _extract_text_or_none(payload: dict[str, Any]) -> str | None:
    try:
        text = _extract_text(payload)
    except RuntimeError:
        return None
    return text or None


def _payload_has_reasoning_content(payload: dict[str, Any]) -> bool:
    choices = payload.get("choices") or []
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message") or {}
        reasoning_content = message.get("reasoning_content")
        if isinstance(reasoning_content, str) and reasoning_content.strip():
            return True
        if isinstance(reasoning_content, list):
            parts: list[str] = []
            for item in reasoning_content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text") or ""))
            if "".join(parts).strip():
                return True
    meta_info = payload.get("meta_info") or {}
    finish_reason = meta_info.get("finish_reason") or {}
    # Some local Qwen-compatible endpoints omit assistant content while still
    # producing a successful completion payload. If we have a structured finish
    # reason but no text, treat this as a possible reasoning-only response.
    return bool(finish_reason)


def _reasoning_content_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    reasoning_content = message.get("reasoning_content")
    if isinstance(reasoning_content, str):
        return reasoning_content.strip()
    if isinstance(reasoning_content, list):
        parts: list[str] = []
        for item in reasoning_content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
        return "".join(parts).strip()
    return ""


def _promote_reasoning_content_to_content(payload: dict[str, Any], *, model: str) -> dict[str, Any]:
    lowered_model = (model or "").strip().lower()
    if not any(token in lowered_model for token in ("affine", "fakemoon")):
        return payload
    if _extract_text_or_none(payload) is not None:
        return payload
    reasoning_text = _reasoning_content_text(payload)
    if not reasoning_text:
        return payload
    normalized = copy.deepcopy(payload)
    choices = normalized.get("choices") or []
    if not choices:
        return payload
    message = choices[0].get("message") or {}
    message["content"] = reasoning_text
    choices[0]["message"] = message
    normalized["choices"] = choices
    return normalized


def _annotate_student_retry_metadata(
    payload: dict[str, Any],
    *,
    retry_without_think: bool,
    response_attempt: int,
) -> dict[str, Any]:
    annotated = dict(payload)
    annotated["student_retry_without_think"] = retry_without_think
    annotated["student_response_attempt"] = response_attempt
    return annotated


def _truncate_generated_action_text(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return raw
    if raw == "<SUBMIT>":
        return raw
    bash_match = re.search(r"```bash\s*.*?```", raw, re.DOTALL | re.IGNORECASE)
    if bash_match:
        return raw[: bash_match.end()].strip()
    thought_match = re.search(r"(^|\n)THOUGHT:\s*", raw, re.IGNORECASE)
    if thought_match:
        tail = raw[thought_match.start() :].strip()
        next_thought = re.search(r"\nTHOUGHT:\s*", tail[1:], re.IGNORECASE)
        if next_thought:
            return tail[: next_thought.start() + 1].strip()
        return tail
    return raw


def _transport_from_payload(payload: dict[str, Any] | None) -> str:
    if not payload:
        return ""
    return str(payload.get("transport") or "openai_chat")


def _finish_reason_type_from_payload(payload: dict[str, Any] | None) -> str:
    if not payload:
        return ""
    meta_info = payload.get("meta_info") or {}
    finish_reason = meta_info.get("finish_reason") or {}
    value = finish_reason.get("type") or ""
    return str(value)


def _finish_reason_length_from_payload(payload: dict[str, Any] | None) -> int | None:
    if not payload:
        return None
    meta_info = payload.get("meta_info") or {}
    finish_reason = meta_info.get("finish_reason") or {}
    value = finish_reason.get("length")
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clean_reasoning_text(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"```.*?```", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"</?think>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</?thinking>", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _merge_teacher_think_into_messages(
    messages: list[dict[str, str]],
    teacher_think_text: str,
) -> list[dict[str, str]]:
    if not teacher_think_text:
        return copy.deepcopy(messages)
    merged = copy.deepcopy(messages)
    guidance = (
        "\n\n<teacher_guidance>\n"
        "Use the following hidden guidance for your next THOUGHT only. "
        "Do not quote this block verbatim in your answer.\n"
        f"{teacher_think_text}\n"
        "</teacher_guidance>"
    )
    if merged and str(merged[-1].get("role", "")) == "user":
        merged[-1]["content"] = f"{merged[-1].get('content', '')}{guidance}"
        return merged
    merged.append({"role": "user", "content": guidance.lstrip()})
    return merged


def _trim_messages_to_context_limit(
    *,
    model: str,
    messages: list[dict[str, str]],
    enable_thinking: bool,
    max_context_tokens: int,
) -> tuple[list[dict[str, str]], int]:
    trimmed = copy.deepcopy(messages)
    removed_pairs = 0
    while len(trimmed) > 4:
        token_count = _count_rendered_prompt_tokens(
            model=model,
            messages=trimmed,
            enable_thinking=enable_thinking,
        )
        if token_count <= max_context_tokens:
            return trimmed, removed_pairs
        del trimmed[2:4]
        removed_pairs += 1
    return trimmed, removed_pairs


def _resolve_teacher_api_base(
    *,
    student_api_base: str,
    teacher_api_base: str,
    teacher_model: str,
    teacher_api_key: str,
    teacher_api_key_file: str,
) -> str:
    explicit = (teacher_api_base or "").strip()
    if explicit:
        return explicit
    if teacher_model and (teacher_api_key or teacher_api_key_file):
        env_base = str(os.environ.get("OPENAI_BASE_URL", "") or "").strip()
        if env_base:
            return env_base
    return student_api_base


def _checkpoint_ring_summary(checkpoints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for index, checkpoint in enumerate(checkpoints[:MAX_EDIT_CHECKPOINTS], start=1):
        summary.append(
            {
                "slot": index,
                "checkpoint_id": checkpoint.get("checkpoint_id", ""),
                "step_index": checkpoint.get("step_index", -1),
                "patch_hash": checkpoint.get("patch_hash", ""),
                "changed_files": checkpoint.get("changed_files", []),
            }
        )
    return summary


def _patch_status(*, latest_changed_files: list[str], last_patch_hash: str, same_patch_steps: int) -> str:
    if not latest_changed_files:
        return "clean"
    if not last_patch_hash:
        return "dirty_patch"
    if same_patch_steps <= 1:
        return "fresh_patch"
    if same_patch_steps >= 4:
        return "stuck_patch"
    return "stable_patch"


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    if not cleaned:
        raise ValueError("empty structured output")
    try:
        payload = json.loads(cleaned)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no json object found")
    payload = json.loads(cleaned[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("structured payload is not an object")
    return payload


def _is_edit_command(command: str) -> bool:
    normalized = re.sub(r"\s+", " ", command.strip()).lower()
    return any(
        token in normalized
        for token in (
            "apply_patch",
            "sed -i",
            "perl -0pi",
            "ruby -0pi",
            "python - <<",
            "python3 - <<",
            "ruby - <<",
            "python -c",
            "python3 -c",
            "ruby -e",
            "file.write(",
            "write_text(",
            "cat <<'eof' >",
            "cat <<'ruby' >",
        )
    )


def _is_verify_command(command: str) -> bool:
    normalized = re.sub(r"\s+", " ", command.strip()).lower()
    return any(
        token in normalized
        for token in (
            "bundle exec rspec",
            "bundle exec rake",
            "pytest",
            "python -m pytest",
            "python -m py_compile",
            "python3 -m pytest",
            "python3 -m py_compile",
            "go test",
            "ruby -ispec",
            "git diff",
            "git status",
        )
    )


def _normalize_action_text(
    text: str,
    *,
    prefer_edit: bool = False,
    prefer_verify: bool = False,
    prefer_view: bool = False,
) -> str:
    raw = (text or "").strip()
    if not raw:
        return raw
    if raw == "<SUBMIT>" and prefer_verify:
        return "<SUBMIT>"
    matches = re.findall(r"```bash\s*(.*?)```", raw, re.DOTALL | re.IGNORECASE)
    if not matches:
        return raw
    commands = [match.strip() for match in matches]

    def _score(command: str, index: int) -> tuple[int, int]:
        if prefer_verify:
            if _is_verify_command(command):
                base = 40
            elif _is_edit_command(command):
                base = 25
            elif _is_file_view_command(command) or _is_search_command(command):
                base = 10
            else:
                base = 0
        elif prefer_view:
            if _is_file_view_command(command):
                base = 45
            elif _is_search_command(command):
                base = 20
            elif _is_edit_command(command):
                base = 10
            elif _is_verify_command(command):
                base = 0
            else:
                base = 0
        elif prefer_edit:
            if _is_edit_command(command):
                base = 40
            elif _is_verify_command(command):
                base = 20
            elif _is_file_view_command(command):
                base = 15
            elif _is_search_command(command):
                base = 10
            else:
                base = 0
        else:
            if _is_file_view_command(command) or _is_search_command(command):
                base = 40
            elif _is_edit_command(command):
                base = 30
            elif _is_verify_command(command):
                base = 10
            else:
                base = 0
        return (base, index)

    command = max(enumerate(commands), key=lambda item: _score(item[1], item[0]))[1]
    prefix = raw.split("```bash", 1)[0].strip()
    if prefix and len(commands) == 1:
        return f"{prefix}\n\n```bash\n{command}\n```"
    return f"```bash\n{command}\n```"


def _extract_issue_context(observation: str) -> str:
    raw = observation or ""
    match = re.search(r"<pr_description>\s*(.*?)\s*</pr_description>", raw, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return raw.strip()


def _extract_problem_statement(observation: str) -> str:
    match = re.search(
        r"<pr_description>\s*Consider the following issue or PR description:\s*(.*?)\s*</pr_description>",
        observation or "",
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    return _extract_issue_context(observation)


def _extract_command(action_text: str) -> str:
    match = re.search(r"```bash\s*(.*?)```", action_text or "", re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return (action_text or "").strip()


def _materialize_action_text(action_text: str) -> str:
    command = _extract_command(action_text)
    if command == "<SUBMIT>":
        return f"```bash\n{UPSTREAM_SUBMIT_COMMAND}\n```"
    return action_text


def _load_upstream_agent_config(output_dir: str) -> dict[str, Any]:
    if yaml is None:
        return {}
    runtime_root = Path(output_dir).resolve() / ".runtime" / "affinetes" / "environments" / "SWE-INFINITE"
    for config_path in (runtime_root / "config.yaml", runtime_root / "agents" / "config.yaml"):
        if config_path.exists():
            payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            return payload.get("agent", {})
    return {}


def _render_upstream_student_messages(
    output_dir: str,
    problem_statement: str,
    reset_observation: str,
) -> list[dict[str, str]]:
    agent_config = _load_upstream_agent_config(output_dir)
    if not agent_config or Template is None or StrictUndefined is None:
        raw = (reset_observation or "").strip()
        marker = "<pr_description>"
        if marker in raw:
            index = raw.index(marker)
            system_msg = raw[:index].strip()
            instance_msg = raw[index:].strip()
            return [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": instance_msg},
            ]
        return [
            {"role": "system", "content": ""},
            {"role": "user", "content": raw},
        ]
    system_template = str(agent_config.get("system_template") or "")
    instance_template = str(agent_config.get("instance_template") or "")
    system_msg = Template(system_template, undefined=StrictUndefined).render()
    instance_msg = Template(instance_template, undefined=StrictUndefined).render(task=problem_statement)
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": instance_msg},
    ]


def _preferred_edit_runtime(current_observation: str) -> str:
    lowered = (current_observation or "").lower()
    if "python3: command not found" in lowered:
        if "python: command not found" in lowered:
            if "ruby: command not found" in lowered:
                return "sed"
            return "ruby"
        return "python"
    if "python: command not found" in lowered:
        return "python3"
    if "ruby: command not found" in lowered:
        return "python3"
    return "python3"


def _edit_runtime_guidance(runtime: str) -> str:
    if runtime == "python3":
        return (
            "Prefer a small `python3 - <<'PY'` script that reads the file, checks an exact needle with "
            "`if needle not in text: raise`, applies one `replace(..., 1)` or equivalent targeted rewrite, "
            "and writes the file back with plain `open(...).read()` / `open(..., \"w\")`. Avoid `pathlib`."
        )
    if runtime == "python":
        return (
            "Prefer a small `python - <<'PY'` script that reads the file, checks an exact needle with "
            "`if needle not in text: raise`, applies one `replace(..., 1)` or equivalent targeted rewrite, "
            "and writes the file back with plain `open(...).read()` / `open(..., \"w\")`. Avoid `pathlib`."
        )
    if runtime == "ruby":
        return (
            "Prefer a small `ruby - <<'RUBY'` script that reads the file, checks an exact needle with `include?`, "
            "applies one `sub`, raises if the needle is absent, and writes the file back."
        )
    if runtime == "perl":
        return (
            "Prefer a small `perl - <<'PL'` script that reads the file, checks an exact needle with `index(...)`, "
            "applies one targeted substitution, dies if the needle is absent, and writes the file back."
        )
    return (
        "Use a minimal non-interactive edit command with tools already present in the container, such as `awk` or `sed`, "
        "and avoid brittle multi-line regex one-liners."
    )


def _rewrite_command_for_runtime(command: str, runtime: str) -> str:
    if runtime == "python3":
        return re.sub(r"\bpython\b(?=(\s+-|\s+<<))", "python3", command)
    return command


def _command_uses_unavailable_runtime(command: str, runtime: str) -> tuple[bool, str]:
    normalized = re.sub(r"\s+", " ", command.strip()).lower()
    if runtime in {"python3", "python"} and re.search(r"(^|[;&|]\s*|&&\s*|cd /app &&\s*)ruby\b", normalized):
        return True, "ruby"
    if runtime == "perl" and re.search(r"(^|[;&|]\s*|&&\s*|cd /app &&\s*)(python3?|ruby)\b", normalized):
        match = re.search(r"(^|[;&|]\s*|&&\s*|cd /app &&\s*)(python3?|ruby)\b", normalized)
        return True, str(match.group(2)) if match else "python"
    if runtime == "python3" and re.search(r"(^|[;&|]\s*|&&\s*|cd /app &&\s*)python\b", normalized):
        return False, ""
    return False, ""


def _is_no_progress_command(command: str) -> bool:
    normalized = re.sub(r"\s+", " ", command.strip()).lower()
    if normalized in {
        "cd /app && ls",
        "cd /app && ls -la",
        "ls",
        "ls -la",
        "pwd",
        "cd /app && pwd",
        "git status",
        "cd /app && git status",
    }:
        return True
    return normalized.startswith("git log --oneline") or normalized.startswith("cd /app && git log --oneline")


def _returncode_from_observation(observation: str) -> int | None:
    match = re.search(r"<returncode>(-?\d+)</returncode>", observation or "", re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _extract_output(observation: str) -> str:
    match = re.search(r"<output>\s*(.*?)\s*</output>", observation or "", re.DOTALL | re.IGNORECASE)
    if not match:
        return ""
    return match.group(1).strip()


def _is_search_command(command: str) -> bool:
    normalized = re.sub(r"\s+", " ", command.strip()).lower()
    return any(token in normalized for token in ("git grep", " grep ", "grep -r", "grep -n", "rg ", "rg -n", "find "))


def _is_file_view_command(command: str) -> bool:
    normalized = re.sub(r"\s+", " ", command.strip()).lower()
    return any(token in normalized for token in ("sed -n", "cat ", "nl -ba", "head ", "tail "))


def _extract_viewed_file(command: str) -> str:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return ""
    for token in reversed(tokens):
        if token in {"&&", "||", ";"}:
            continue
        if token.startswith("-"):
            continue
        if "*" in token or "?" in token or "[" in token:
            continue
        if token in {"cd", "/app", "sed", "cat", "nl", "head", "tail"}:
            continue
        if "/" in token or "." in token:
            return token
    return ""


def _extract_first_candidate_file(output: str) -> str:
    for line in (output or "").splitlines():
        match = re.match(r"([A-Za-z0-9_./-]+\.[A-Za-z0-9_+-]+):\d+:", line.strip())
        if match:
            return match.group(1)
    return ""


@lru_cache(maxsize=8)
def _load_chat_template_tokenizer(model: str):
    if AutoTokenizer is None:
        raise RuntimeError("transformers is required for sglang /generate fallback")
    return AutoTokenizer.from_pretrained(model, trust_remote_code=True)


def _render_messages_as_prompt(
    *,
    model: str,
    messages: list[dict[str, str]],
    enable_thinking: bool,
) -> str:
    try:
        tokenizer = _load_chat_template_tokenizer(model)
        if hasattr(tokenizer, "apply_chat_template"):
            kwargs: dict[str, Any] = {
                "tokenize": False,
                "add_generation_prompt": True,
            }
            if enable_thinking:
                kwargs["enable_thinking"] = True
            try:
                rendered = tokenizer.apply_chat_template(messages, **kwargs)
                if isinstance(rendered, str) and rendered.strip():
                    return rendered
            except TypeError:
                kwargs.pop("enable_thinking", None)
                rendered = tokenizer.apply_chat_template(messages, **kwargs)
                if isinstance(rendered, str) and rendered.strip():
                    return rendered
            except Exception:
                pass
    except Exception:
        pass
    rendered_lines = []
    for message in messages:
        rendered_lines.append(f"{message.get('role', 'user')}: {message.get('content', '')}")
    rendered_lines.append("assistant:")
    return "\n".join(rendered_lines)


def _count_rendered_prompt_tokens(
    *,
    model: str,
    messages: list[dict[str, str]],
    enable_thinking: bool,
) -> int:
    try:
        tokenizer = _load_chat_template_tokenizer(model)
        if hasattr(tokenizer, "apply_chat_template"):
            kwargs: dict[str, Any] = {
                "tokenize": True,
                "add_generation_prompt": True,
            }
            if enable_thinking:
                kwargs["enable_thinking"] = True
            try:
                rendered = tokenizer.apply_chat_template(messages, **kwargs)
            except TypeError:
                kwargs.pop("enable_thinking", None)
                rendered = tokenizer.apply_chat_template(messages, **kwargs)
            if hasattr(rendered, "__len__"):
                return int(len(rendered))
    except Exception:
        pass
    prompt = _render_messages_as_prompt(model=model, messages=messages, enable_thinking=enable_thinking)
    return max(1, len(prompt) // 4)


def _api_base_root(api_base: str) -> str:
    parsed = urllib_parse.urlparse(api_base)
    scheme = parsed.scheme or "http"
    netloc = parsed.netloc or parsed.path
    return f"{scheme}://{netloc}"


def _prefer_chat_completions_first(api_base: str, model: str) -> bool:
    parsed = urllib_parse.urlparse(api_base)
    hostname = (parsed.hostname or "").strip().lower()
    lowered_model = (model or "").strip().lower()
    if hostname in {"127.0.0.1", "localhost"} and any(
        token in lowered_model for token in ("qwen", "affine", "fakemoon")
    ):
        return True
    return False


def _should_try_sglang_generate(api_base: str, error_message: str) -> bool:
    lowered = (error_message or "").lower()
    return "input_ids should be a list of lists" in lowered


def _sglang_generate_completion(
    *,
    api_base: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    timeout: int,
    enable_thinking: bool,
    max_new_tokens: int,
) -> dict[str, Any]:
    prompt = _render_messages_as_prompt(model=model, messages=messages, enable_thinking=enable_thinking)
    payload = {
        "text": prompt,
        "sampling_params": {
            "temperature": max(0.0, float(temperature)),
            "max_new_tokens": int(max_new_tokens),
        },
    }
    req = urllib_request.Request(
        _api_base_root(api_base).rstrip("/") + "/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"sglang /generate failed: HTTP {exc.code}: {body[:500]}") from exc
    except Exception as exc:  # pragma: no cover - real network fallback
        raise RuntimeError(f"sglang /generate failed: {exc}") from exc
    data = json.loads(body)
    text = _truncate_generated_action_text(str(data.get("text") or ""))
    return {
        "id": str((data.get("meta_info") or {}).get("id") or ""),
        "model": model,
        "output_text": text,
        "transport": "sglang_generate",
        "meta_info": data.get("meta_info") or {},
    }


def _chat_completion(
    *,
    api_base: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    reasoning_effort: str,
    timeout: int,
    enable_thinking: bool = False,
    student_max_new_tokens: int = 4096,
    retry_without_think_on_no_text: bool = False,
) -> dict[str, Any]:
    client = OpenAI(base_url=api_base, api_key=api_key, timeout=timeout)
    prefer_chat_first = _prefer_chat_completions_first(api_base, model)
    lower_model = (model or "").strip().lower()
    use_qwen_chat_template_kwargs = prefer_chat_first and "qwen" in lower_model
    extra_body = {"enable_thinking": True} if enable_thinking else None
    chat_extra_body = (
        {"chat_template_kwargs": {"enable_thinking": bool(enable_thinking)}}
        if use_qwen_chat_template_kwargs
        else extra_body
    )
    no_think_chat_extra_body = (
        {"chat_template_kwargs": {"enable_thinking": False}}
        if use_qwen_chat_template_kwargs
        else None
    )

    def _maybe_retry_local_prefer_chat_no_text(payload: dict[str, Any]) -> dict[str, Any]:
        if not (
            retry_without_think_on_no_text
            and enable_thinking
            and prefer_chat_first
            and _extract_text_or_none(payload) is None
            and _payload_has_reasoning_content(payload)
        ):
            return _annotate_student_retry_metadata(payload, retry_without_think=False, response_attempt=1)
        retry_payload = _chat_create(no_think_chat_extra_body)
        if _extract_text_or_none(retry_payload) is None:
            raise RuntimeError("chat completion returned no text content after no-think retry")
        return _annotate_student_retry_metadata(retry_payload, retry_without_think=True, response_attempt=2)

    def _responses_create(request_extra_body: dict[str, Any] | None) -> dict[str, Any]:
        response = client.responses.create(
            model=model,
            reasoning={"effort": reasoning_effort},
            input=messages,
            extra_body=request_extra_body,
        )
        return {
            "id": getattr(response, "id", ""),
            "model": getattr(response, "model", model),
            "output_text": getattr(response, "output_text", ""),
        }

    def _chat_create(request_extra_body: dict[str, Any] | None) -> dict[str, Any]:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            extra_body=request_extra_body,
        )
        payload = {
            "id": getattr(response, "id", ""),
            "model": getattr(response, "model", model),
            "choices": [choice.model_dump(mode="json") for choice in (getattr(response, "choices", None) or [])],
        }
        return _promote_reasoning_content_to_content(payload, model=model)

    def _rejects_enable_thinking(exc: Exception) -> bool:
        status_code = getattr(exc, "status_code", None)
        message = str(exc)
        return bool(status_code == 422 and "enable_thinking" in message)

    if prefer_chat_first:
        try:
            return _maybe_retry_local_prefer_chat_no_text(_chat_create(chat_extra_body))
        except Exception as chat_exc:  # pragma: no cover - exercised by real runs
            if chat_extra_body and _rejects_enable_thinking(chat_exc):
                try:
                    return _annotate_student_retry_metadata(_chat_create(None), retry_without_think=False, response_attempt=1)
                except Exception as retry_exc:
                    chat_exc = retry_exc
            message = str(chat_exc)
            if _should_try_sglang_generate(api_base, message):
                try:
                    return _sglang_generate_completion(
                        api_base=api_base,
                        api_key=api_key,
                        model=model,
                        messages=messages,
                        temperature=temperature,
                        timeout=timeout,
                        enable_thinking=enable_thinking,
                        max_new_tokens=student_max_new_tokens,
                    )
                except Exception as generate_exc:
                    raise RuntimeError(
                        f"chat.completions.create failed: {chat_exc}; "
                        f"sglang /generate fallback failed: {generate_exc}"
                    ) from generate_exc
            raise RuntimeError(f"chat.completions.create failed: {chat_exc}") from chat_exc

    try:
        return _annotate_student_retry_metadata(_responses_create(extra_body), retry_without_think=False, response_attempt=1)
    except Exception as exc:  # pragma: no cover - exercised by real runs
        if extra_body and _rejects_enable_thinking(exc):
            try:
                return _annotate_student_retry_metadata(_responses_create(None), retry_without_think=False, response_attempt=1)
            except Exception as retry_exc:
                exc = retry_exc
        status_code = getattr(exc, "status_code", None)
        message = str(exc)
        should_try_chat = (
            status_code == 404
            or (isinstance(status_code, int) and status_code >= 500)
            or "404" in message
            or "Not Found" in message
            or "Internal Server Error" in message
            or _should_try_sglang_generate(api_base, message)
        )
        if should_try_chat:
            try:
                return _maybe_retry_local_prefer_chat_no_text(_chat_create(chat_extra_body))
            except Exception as chat_exc:  # pragma: no cover - exercised by real runs
                if chat_extra_body and _rejects_enable_thinking(chat_exc):
                    try:
                        return _annotate_student_retry_metadata(_chat_create(None), retry_without_think=False, response_attempt=1)
                    except Exception as retry_chat_exc:
                        chat_exc = retry_chat_exc
                if _should_try_sglang_generate(api_base, str(chat_exc)):
                    try:
                        return _sglang_generate_completion(
                            api_base=api_base,
                            api_key=api_key,
                            model=model,
                            messages=messages,
                            temperature=temperature,
                            timeout=timeout,
                            enable_thinking=enable_thinking,
                            max_new_tokens=student_max_new_tokens,
                        )
                    except Exception as generate_exc:
                        raise RuntimeError(
                            f"responses.create failed: {exc}; chat.completions.create fallback failed: {chat_exc}; "
                            f"sglang /generate fallback failed: {generate_exc}"
                        ) from generate_exc
                raise RuntimeError(
                    f"responses.create failed: {exc}; chat.completions.create fallback failed: {chat_exc}"
                ) from chat_exc
        raise RuntimeError(f"responses.create failed: {exc}") from exc


def _chat_completion_with_transport_retry(
    *,
    transport_only_retries: int,
    **kwargs: Any,
) -> tuple[dict[str, Any], int]:
    attempts = 0
    while True:
        try:
            return _chat_completion(**kwargs), attempts
        except Exception as exc:
            if attempts >= max(0, int(transport_only_retries)) or not _is_retryable_transport_error(exc):
                raise
            attempts += 1


def _lineage_key(*, latest_changed_files: list[str], current_patch_hash: str) -> str:
    if latest_changed_files and current_patch_hash:
        return current_patch_hash
    return "no_patch"


def _normalize_command_signature(command: str) -> str:
    return re.sub(r"\s+", " ", (command or "").strip()).lower()


def _classify_stall(
    *,
    raw_action_text: str,
    action_text: str,
    command_signature: str,
    command_history: list[str],
    latest_changed_files: list[str],
    same_patch_steps: int,
    patch_repeat_command_kind: str,
) -> str:
    if _is_model_stop_response(action_text) or _is_model_stop_response(raw_action_text):
        return "no_action"
    if latest_changed_files:
        if same_patch_steps >= 4:
            return "stuck_patch"
        repeated_same_command_twice = bool(command_signature) and len(command_history) >= 2 and command_history[-2:] == [command_signature] * 2
        repeated_same_command_thrice = bool(command_signature) and len(command_history) >= 3 and command_history[-3:] == [command_signature] * 3
        if patch_repeat_command_kind == "verify" and (repeated_same_command_twice or same_patch_steps >= 3):
            return "verify_loop"
        if patch_repeat_command_kind == "read" and (repeated_same_command_twice or repeated_same_command_thrice or same_patch_steps >= 3):
            return "bad_patch_loop"
        return "none"
    if command_signature and len(command_history) >= 3 and command_history[-3:] == [command_signature] * 3:
        if _is_file_view_command(command_signature):
            return "repeat_read_loop"
        if _is_search_command(command_signature) or any(
            token in command_signature for token in ("git log", "curl ", "wget ")
        ):
            return "repeat_search_loop"
    return "none"


def _normalize_controller_decision(payload: dict[str, Any]) -> dict[str, Any]:
    restore_target = str(payload.get("restore_target") or payload.get("branch_decision") or "CURRENT").strip().upper()
    if restore_target == "EDIT":
        restore_target = "ROLLBACK_1"
    if restore_target not in {"CURRENT", "BASELINE", "ROLLBACK_1", "ROLLBACK_2", "ROLLBACK_3", "ROLLBACK_4", "STOP"}:
        restore_target = "CURRENT"
    inject_teacher_think = bool(payload.get("inject_teacher_think"))
    teacher_think_text = _clean_reasoning_text(str(payload.get("teacher_think_text") or ""))
    stall_class = str(payload.get("stall_class") or "none").strip().lower()
    if stall_class not in {
        "none",
        "no_action",
        "repeat_read_loop",
        "repeat_search_loop",
        "stuck_patch",
        "bad_patch_loop",
        "verify_loop",
    }:
        stall_class = "none"
    reason = str(payload.get("reason") or "").strip()
    if restore_target != "CURRENT":
        inject_teacher_think = False
        teacher_think_text = ""
    if not inject_teacher_think:
        teacher_think_text = ""
    branch_decision = "CURRENT"
    if restore_target == "BASELINE":
        branch_decision = "BASELINE"
    elif restore_target.startswith("ROLLBACK_"):
        branch_decision = "EDIT"
    elif restore_target == "STOP":
        branch_decision = "STOP"
    return {
        "restore_target": restore_target,
        "branch_decision": branch_decision,
        "inject_teacher_think": inject_teacher_think,
        "teacher_think_text": teacher_think_text,
        "stall_class": stall_class,
        "reason": reason,
    }


def _is_model_stop_response(action_text: str) -> bool:
    raw = (action_text or "").strip()
    if not raw:
        return True
    if raw == "<SUBMIT>":
        return False
    if re.search(r"```bash\s*.*?```", raw, re.DOTALL | re.IGNORECASE):
        return False
    return True


def _heuristic_controller_decision(
    *,
    no_progress_commands: list[str],
    current_observation: str,
    latest_changed_files: list[str],
    checkpoint_ring: list[dict[str, Any]],
    root_retries_used: int,
    max_root_retries: int,
    stall_class: str,
) -> dict[str, Any]:
    lowered_observation = (current_observation or "").lower()
    restore_target = "CURRENT"
    if stall_class in {"stuck_patch", "bad_patch_loop", "verify_loop"} and checkpoint_ring:
        restore_target = "ROLLBACK_1"
    elif no_progress_commands or "command not found" in lowered_observation or "no file changes were made" in lowered_observation or "syntax error" in lowered_observation:
        if checkpoint_ring:
            restore_target = "ROLLBACK_1"
        elif root_retries_used < max_root_retries:
            restore_target = "BASELINE"
    return {
        "restore_target": restore_target,
        "inject_teacher_think": False,
        "teacher_think_text": "",
        "stall_class": stall_class,
        "reason": "local heuristic fallback",
    }


def _resolve_restore_target(
    *,
    requested_target: str,
    checkpoint_ring: list[dict[str, Any]],
    baseline_available: bool,
    total_restores_used: int,
    lineage_retry_count: int,
    stall_class: str,
) -> tuple[str, str]:
    if total_restores_used >= MAX_TOTAL_RESTORES_PER_RUN:
        return "STOP", "restore_budget_exhausted"
    if stall_class in {"no_action", "repeat_read_loop", "repeat_search_loop", "stuck_patch", "bad_patch_loop", "verify_loop"}:
        if lineage_retry_count <= 0:
            requested_target = "ROLLBACK_1"
        elif lineage_retry_count == 1:
            requested_target = "ROLLBACK_2"
        elif lineage_retry_count == 2:
            requested_target = "BASELINE"
        else:
            return "STOP", "lineage_retry_budget_exhausted"
    if requested_target.startswith("ROLLBACK_"):
        try:
            index = int(requested_target.split("_", 1)[1]) - 1
        except (TypeError, ValueError):
            index = 0
        if checkpoint_ring:
            index = max(0, min(index, len(checkpoint_ring) - 1))
            return f"ROLLBACK_{index + 1}", "resolved"
        if baseline_available:
            return "BASELINE", "degraded_to_baseline"
        return "STOP", "rollback_unavailable"
    if requested_target == "BASELINE" and not baseline_available:
        if checkpoint_ring:
            return "ROLLBACK_1", "degraded_to_latest_rollback"
        return "STOP", "baseline_unavailable"
    return requested_target, "resolved"


def _teacher_controller_decision(
    *,
    api_base: str,
    api_key: str,
    model: str,
    controller_context: dict[str, Any],
    reasoning_effort: str,
    timeout: int,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    static_context = {
        "task_id": controller_context.get("task_id"),
        "max_steps": controller_context.get("max_steps"),
        "issue_context": controller_context.get("issue_context"),
        "problem_statement": controller_context.get("problem_statement"),
        "preferred_runtime": controller_context.get("preferred_runtime"),
        "runtime_availability": controller_context.get("runtime_availability"),
        "baseline_checkpoint_id": controller_context.get("baseline_checkpoint_id"),
        "max_total_restores_per_run": controller_context.get("max_total_restores_per_run"),
        "max_same_lineage_retries": controller_context.get("max_same_lineage_retries"),
    }
    dynamic_context = {
        "step_index": controller_context.get("step_index"),
        "current_observation": controller_context.get("current_observation"),
        "latest_changed_files": controller_context.get("latest_changed_files"),
        "last_patch_hash": controller_context.get("last_patch_hash"),
        "last_viewed_file": controller_context.get("last_viewed_file"),
        "last_candidate_file": controller_context.get("last_candidate_file"),
        "no_progress_commands": controller_context.get("no_progress_commands"),
        "stall_class": controller_context.get("stall_class"),
        "same_patch_steps": controller_context.get("same_patch_steps"),
        "recent_command_signatures": controller_context.get("recent_command_signatures"),
        "lineage_key": controller_context.get("lineage_key"),
        "lineage_retry_count": controller_context.get("lineage_retry_count"),
        "total_restores_used": controller_context.get("total_restores_used"),
        "restore_budget_remaining": controller_context.get("restore_budget_remaining"),
        "checkpoint_ring": controller_context.get("checkpoint_ring"),
        "baseline_available": controller_context.get("baseline_available"),
        "last_step_payload": controller_context.get("last_step_payload"),
        "last_state_payload": controller_context.get("last_state_payload"),
    }
    transcript_context = {
        "student_messages": controller_context.get("student_messages"),
    }
    payload = _chat_completion(
        api_base=api_base,
        api_key=api_key,
        model=model,
        messages=[
            {"role": "system", "content": TEACHER_CONTROLLER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Static privileged run context follows as JSON. This content should be treated as stable background for the run.\n\n"
                    + json.dumps(static_context, ensure_ascii=False, sort_keys=True, indent=2)
                ),
            },
            {
                "role": "user",
                "content": (
                    "Full student-visible transcript/history follows as JSON.\n\n"
                    + json.dumps(transcript_context, ensure_ascii=False, sort_keys=True, indent=2)
                ),
            },
            {
                "role": "user",
                "content": (
                    "Dynamic controller state for the current step follows as JSON.\n"
                    "Use it to decide whether to continue, restore BASELINE/EDIT, and whether to inject hidden think guidance.\n\n"
                    + json.dumps(dynamic_context, ensure_ascii=False, sort_keys=True, indent=2)
                ),
            },
        ],
        temperature=0.0,
        reasoning_effort=reasoning_effort,
        timeout=timeout,
        enable_thinking=False,
    )
    raw_text = _extract_text(payload)
    try:
        normalized = _normalize_controller_decision(_extract_json_object(raw_text))
    except Exception as exc:
        normalized = {
            "restore_target": "CURRENT",
            "branch_decision": "CURRENT",
            "inject_teacher_think": False,
            "teacher_think_text": "",
            "stall_class": "none",
            "reason": f"structured_parse_fallback: {exc}",
        }
    return normalized, payload, raw_text


def _append_event(events_path: Path, payload: dict[str, Any]) -> None:
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _changed_files_from_state(payload: dict[str, Any]) -> list[str]:
    info = payload.get("info") or {}
    changed = info.get("changed_files") or []
    if isinstance(changed, list):
        return [str(item) for item in changed]
    return []


def _patch_hash_from_state(payload: dict[str, Any]) -> str:
    info = payload.get("info") or {}
    value = info.get("last_patch_hash") or ""
    return str(value)


def _reward_from_step_payload(payload: dict[str, Any] | None) -> float | None:
    if not payload:
        return None
    reward = payload.get("reward")
    if reward is None:
        return None
    try:
        return float(reward)
    except (TypeError, ValueError):
        return None


def _test_stats_from_step_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {}
    info = payload.get("info") or {}
    test_stats = info.get("test_stats") or {}
    return dict(test_stats) if isinstance(test_stats, dict) else {}


def _is_retryable_transport_error(exc: Exception) -> bool:
    lowered = str(exc).strip().lower()
    return any(pattern in lowered for pattern in TRANSPORT_RETRY_PATTERNS)


def _terminal_status_for_failure(*, failure_stage: str, exc: Exception) -> str:
    lowered = str(exc).lower()
    if "no module named pip" in lowered or "failed to install upstream swe requirements" in lowered or "failed to create upstream venv" in lowered:
        return "runtime_bootstrap_failed"
    if failure_stage == "student_transport" or _is_retryable_transport_error(exc):
        return "student_transport_failed"
    if failure_stage.startswith("openenv") or failure_stage.startswith("baseline_"):
        return "openenv_failed"
    return "launch_aborted"


def _build_synthesis_summary(
    *,
    task_id: str,
    episode_id: str,
    model: str,
    teacher_model: str,
    reasoning_effort: str,
    teacher_reasoning_effort: str,
    api_base: str,
    resolved_teacher_api_base: str,
    upstream_repo_path: str,
    upstream_git_url: str,
    upstream_ref: str,
    baseline_checkpoint_id: str,
    edit_checkpoint_id: str,
    root_retries_used: int,
    edit_retries_used: int,
    student_calls: int,
    teacher_calls: int,
    teacher_branch_calls: int,
    teacher_think_calls: int,
    probe_runtime: bool,
    inject_teacher_think: bool,
    student_enable_thinking: bool,
    student_max_new_tokens: int,
    student_max_context_tokens: int,
    final_model_payload: dict[str, Any] | None,
    eval_mode: bool,
    eval_max_context_tokens: int,
    last_context_tokens: int,
    runtime_availability: dict[str, bool],
    preferred_runtime: str,
    latest_changed_files: list[str],
    final_step: dict[str, Any] | None,
    model_stop_reason: str,
    stall_class: str,
    last_restore_target_applied: str,
    total_restores_used: int,
    edit_checkpoints: list[dict[str, Any]],
    terminal_status: str,
    events_path: Path,
    transport_retries_used: int,
    failure_stage: str,
    failure_reason: str,
    exception_type: str,
    exception_message: str,
) -> dict[str, Any]:
    return {
        "schema_version": "affinetes_openenv_synthesis.v1",
        "task_id": task_id,
        "episode_id": episode_id,
        "model": model,
        "teacher_model": teacher_model,
        "reasoning_effort": reasoning_effort,
        "teacher_reasoning_effort": teacher_reasoning_effort,
        "api_base": api_base,
        "teacher_api_base": resolved_teacher_api_base if teacher_model else "",
        "upstream_repo_path": upstream_repo_path,
        "upstream_git_url": upstream_git_url,
        "upstream_ref": upstream_ref,
        "baseline_checkpoint_id": baseline_checkpoint_id,
        "edit_checkpoint_id": edit_checkpoint_id,
        "root_retries_used": root_retries_used,
        "edit_retries_used": edit_retries_used,
        "student_calls": student_calls,
        "teacher_calls": teacher_calls,
        "teacher_branch_calls": teacher_branch_calls,
        "teacher_think_calls": teacher_think_calls,
        "probe_runtime": probe_runtime,
        "inject_teacher_think": inject_teacher_think,
        "student_enable_thinking": student_enable_thinking,
        "student_max_new_tokens": student_max_new_tokens,
        "student_max_context_tokens": student_max_context_tokens,
        "student_retry_without_think": bool((final_model_payload or {}).get("student_retry_without_think")),
        "student_response_attempt": int((final_model_payload or {}).get("student_response_attempt") or 0),
        "eval_mode": eval_mode,
        "clean_eval": eval_mode,
        "eval_max_context_tokens": eval_max_context_tokens,
        "final_context_tokens": last_context_tokens,
        "runtime_availability": runtime_availability,
        "preferred_runtime": preferred_runtime,
        "latest_changed_files": latest_changed_files,
        "final_reward": _reward_from_step_payload(final_step),
        "verified_success": bool((_reward_from_step_payload(final_step) or 0.0) > 0.0),
        "final_test_stats": _test_stats_from_step_payload(final_step),
        "model_stop_reason": model_stop_reason,
        "student_transport": _transport_from_payload(final_model_payload),
        "student_finish_reason_type": _finish_reason_type_from_payload(final_model_payload),
        "student_finish_reason_length": _finish_reason_length_from_payload(final_model_payload),
        "stall_class": stall_class if not eval_mode else "none",
        "restore_target_applied": last_restore_target_applied,
        "restore_budget_used": total_restores_used,
        "checkpoint_ring_depth": 0 if eval_mode else len(edit_checkpoints),
        "final_observation": str(final_step.get("observation") if final_step else ""),
        "final_done": bool(final_step.get("done")) if final_step else False,
        "final_truncated": bool(final_step.get("truncated")) if final_step else False,
        "terminal_status": terminal_status,
        "transport_retries_used": transport_retries_used,
        "failure_stage": failure_stage,
        "failure_reason": failure_reason,
        "exception_type": exception_type,
        "exception_message": exception_message,
        "events_path": str(events_path),
    }


def _probe_runtime_availability(*, output_dir: str, episode_id: str) -> dict[str, bool]:
    probe_command = (
        "cd /app && "
        "printf 'python3=' && command -v python3 || true && "
        "printf '\\npython=' && command -v python || true && "
        "printf '\\nruby=' && command -v ruby || true && "
        "printf '\\nperl=' && command -v perl || true"
    )
    step_payload = openenv_step(
        output_dir=output_dir,
        episode_id=episode_id,
        action_text=f"```bash\n{probe_command}\n```",
    )
    output_text = _extract_output(str(step_payload.get("observation") or ""))
    availability = {"python3": False, "python": False, "ruby": False, "perl": False}
    for line in output_text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key in availability:
            availability[key] = bool(value)
    return availability


def _preferred_runtime_from_availability(availability: dict[str, bool]) -> str:
    if availability.get("python3"):
        return "python3"
    if availability.get("perl"):
        return "perl"
    if availability.get("python"):
        return "python"
    if availability.get("ruby"):
        return "ruby"
    return "sed"


def _run_openenv_synthesis_impl(
    *,
    output_dir: str,
    upstream_repo_path: str = "",
    upstream_git_url: str = DEFAULT_AFFINETES_GIT_URL,
    upstream_ref: str,
    upstream_python: str = "python3",
    cache_dir: str = DEFAULT_SWE_CACHE_DIR,
    task_id: str,
    api_base: str,
    model: str,
    api_key: str = "",
    api_key_file: str = "",
    teacher_model: str = "",
    teacher_api_base: str = "",
    teacher_api_key: str = "",
    teacher_api_key_file: str = "",
    temperature: float = 0.2,
    teacher_temperature: float = 0.0,
    reasoning_effort: str = "low",
    teacher_reasoning_effort: str = "low",
    step_limit: int = 20,
    command_timeout: int = 60,
    model_timeout: int = 180,
    transport_only_retries: int = 0,
    max_steps: int = 4,
    max_root_retries: int = 1,
    max_edit_retries: int = 1,
    probe_runtime: bool = False,
    inject_teacher_think: bool = False,
    student_enable_thinking: bool = False,
    student_max_new_tokens: int = 4096,
    student_max_context_tokens: int = STUDENT_MAX_CONTEXT_TOKENS_DEFAULT,
    eval_mode: bool = False,
    eval_max_context_tokens: int = 32768,
) -> dict[str, Any]:
    root = _ensure_dir(output_dir)
    events_path = root / "raw" / "synthesis_events.jsonl"
    manifest_path = root / "manifests" / "synthesis_run.json"
    events_path.write_text("", encoding="utf-8")

    resolved_api_key = _read_api_key(api_key=api_key, api_key_file=api_key_file)
    if not resolved_api_key:
        raise RuntimeError("api_key or api_key_file is required for synthesis")
    if eval_mode:
        teacher_model = ""
        teacher_api_base = ""
        teacher_api_key = ""
        teacher_api_key_file = ""
        max_root_retries = 0
        max_edit_retries = 0
        probe_runtime = False
        inject_teacher_think = False
    resolved_teacher_api_key = _read_api_key(api_key=teacher_api_key, api_key_file=teacher_api_key_file) or resolved_api_key
    resolved_teacher_api_base = _resolve_teacher_api_base(
        student_api_base=api_base,
        teacher_api_base=teacher_api_base,
        teacher_model=teacher_model,
        teacher_api_key=teacher_api_key,
        teacher_api_key_file=teacher_api_key_file,
    )

    reset: dict[str, Any] = {}
    baseline: dict[str, Any] = {}
    baseline_checkpoint_id = ""
    episode_id = ""
    baseline_ready = False
    for reset_attempt in range(1, BASELINE_RESET_RESTART_RETRIES + 2):
        reset = openenv_reset(
            output_dir=output_dir,
            upstream_repo_path=upstream_repo_path,
            upstream_git_url=upstream_git_url,
            upstream_ref=upstream_ref,
            upstream_python=upstream_python,
            cache_dir=cache_dir,
            api_key=resolved_api_key,
            task_id=task_id,
            step_limit=step_limit,
            command_timeout=command_timeout,
        )
        _append_event(events_path, {"kind": "reset", "attempt": reset_attempt, "payload": reset})
        episode_id = str(reset.get("episode_id") or "")
        if not episode_id:
            raise RuntimeError(f"reset did not return episode_id: {reset}")

        if BASELINE_CHECKPOINT_INITIAL_DELAY_SECS > 0:
            time.sleep(BASELINE_CHECKPOINT_INITIAL_DELAY_SECS)

        baseline = {}
        baseline_checkpoint_id = ""
        for attempt in range(1, BASELINE_CHECKPOINT_RETRIES + 1):
            baseline = openenv_checkpoint(output_dir=output_dir, episode_id=episode_id, label="baseline")
            _append_event(
                events_path,
                {
                    "kind": "checkpoint",
                    "label": "baseline",
                    "reset_attempt": reset_attempt,
                    "attempt": attempt,
                    "payload": baseline,
                },
            )
            baseline_checkpoint_id = str(baseline.get("checkpoint_id") or "")
            if baseline_checkpoint_id:
                baseline_ready = True
                break
            if attempt >= BASELINE_CHECKPOINT_RETRIES or not _is_retryable_checkpoint_failure(baseline):
                break
            time.sleep(BASELINE_CHECKPOINT_RETRY_DELAY_SECS)

        if baseline_ready:
            break
        if not _is_retryable_checkpoint_failure(baseline) or reset_attempt > BASELINE_RESET_RESTART_RETRIES:
            raise RuntimeError(f"baseline checkpoint failed: {baseline}")
        try:
            stop_payload = openenv_stop(output_dir=output_dir, episode_id=episode_id)
            _append_event(
                events_path,
                {
                    "kind": "stop",
                    "scope": "baseline_retry_cleanup",
                    "reset_attempt": reset_attempt,
                    "payload": stop_payload,
                },
            )
        except Exception as exc:
            _append_event(
                events_path,
                {
                    "kind": "stop_error",
                    "scope": "baseline_retry_cleanup",
                    "reset_attempt": reset_attempt,
                    "error": str(exc),
                },
            )

    if not baseline_ready:
        raise RuntimeError(f"baseline checkpoint failed: {baseline}")

    if probe_runtime:
        runtime_availability = _probe_runtime_availability(output_dir=output_dir, episode_id=episode_id)
        _append_event(events_path, {"kind": "runtime_probe", "availability": runtime_availability})
        restored_after_probe = openenv_restore(
            output_dir=output_dir,
            episode_id=episode_id,
            checkpoint_id=baseline_checkpoint_id,
        )
        _append_event(events_path, {"kind": "restore", "scope": "post-probe", "payload": restored_after_probe})
    else:
        runtime_availability = {"python3": True, "python": False, "ruby": False, "perl": False}

    current_observation = str(reset.get("observation") or "")
    problem_statement = _extract_problem_statement(current_observation)
    issue_context = problem_statement
    student_messages = _render_upstream_student_messages(output_dir, problem_statement, current_observation)
    checkpoint_student_messages: dict[str, list[dict[str, str]]] = {
        baseline_checkpoint_id: copy.deepcopy(student_messages)
    }
    root_retries_used = 0
    edit_retries_used = 0
    edit_checkpoints: list[dict[str, Any]] = []
    edit_checkpoint_id = ""
    latest_changed_files: list[str] = []
    final_step: dict[str, Any] | None = None
    no_progress_commands: list[str] = []
    last_viewed_file = ""
    last_candidate_file = ""
    student_calls = 0
    teacher_calls = 0
    teacher_branch_calls = 0
    teacher_think_calls = 0
    last_patch_hash = ""
    preferred_runtime = _preferred_runtime_from_availability(runtime_availability)
    teacher_think_text = ""
    last_step_payload: dict[str, Any] | None = None
    last_state_payload: dict[str, Any] | None = None
    terminal_status = "max_steps"
    model_stop_reason = ""
    last_context_tokens = 0
    final_model_payload: dict[str, Any] | None = None
    last_restore_target_applied = "CURRENT"
    same_patch_steps = 0
    recent_command_signatures: list[str] = []
    stall_class = "none"
    total_restores_used = 0
    lineage_retry_counts: dict[str, int] = {}
    current_lineage_key = "no_patch"
    transport_retries_used = 0

    step_index = 0
    while step_index < max_steps:
        messages = _merge_teacher_think_into_messages(student_messages, teacher_think_text)
        messages, trimmed_pairs = _trim_messages_to_context_limit(
            model=model,
            messages=messages,
            enable_thinking=student_enable_thinking,
            max_context_tokens=student_max_context_tokens,
        )
        if trimmed_pairs:
            _append_event(
                events_path,
                {
                    "kind": "context_trim",
                    "step_index": step_index,
                    "removed_pairs": trimmed_pairs,
                    "limit": student_max_context_tokens,
                },
            )
        last_context_tokens = _count_rendered_prompt_tokens(model=model, messages=messages, enable_thinking=student_enable_thinking)
        if eval_mode and last_context_tokens >= eval_max_context_tokens:
            terminal_status = "context_limit"
            _append_event(
                events_path,
                {
                    "kind": "eval_stop",
                    "step_index": step_index,
                    "reason": "context_limit",
                    "context_tokens": last_context_tokens,
                    "limit": eval_max_context_tokens,
                },
            )
            break
        lowered_observation = current_observation.lower()
        checkpoint_ring = _checkpoint_ring_summary(edit_checkpoints)
        lineage_retry_count = lineage_retry_counts.get(current_lineage_key, 0)
        if eval_mode:
            decision = {
                "restore_target": "CURRENT",
                "branch_decision": "CURRENT",
                "inject_teacher_think": False,
                "teacher_think_text": "",
                "stall_class": "none",
                "reason": "clean eval mode",
            }
        elif teacher_model:
            controller_context = {
                "task_id": task_id,
                "step_index": step_index,
                "max_steps": max_steps,
                "issue_context": issue_context,
                "problem_statement": problem_statement,
                "current_observation": current_observation,
                "lowered_observation": lowered_observation,
                "latest_changed_files": latest_changed_files,
                "last_patch_hash": last_patch_hash,
                "patch_status": _patch_status(
                    latest_changed_files=latest_changed_files,
                    last_patch_hash=last_patch_hash,
                    same_patch_steps=same_patch_steps,
                ),
                "last_viewed_file": last_viewed_file,
                "last_candidate_file": last_candidate_file,
                "no_progress_commands": no_progress_commands,
                "preferred_runtime": preferred_runtime,
                "runtime_availability": runtime_availability,
                "baseline_checkpoint_id": baseline_checkpoint_id,
                "max_total_restores_per_run": MAX_TOTAL_RESTORES_PER_RUN,
                "max_same_lineage_retries": MAX_SAME_LINEAGE_RETRIES,
                "stall_class": stall_class,
                "same_patch_steps": same_patch_steps,
                "recent_command_signatures": recent_command_signatures[-8:],
                "lineage_key": current_lineage_key,
                "lineage_retry_count": lineage_retry_count,
                "total_restores_used": total_restores_used,
                "restore_budget_remaining": max(0, MAX_TOTAL_RESTORES_PER_RUN - total_restores_used),
                "checkpoint_ring": checkpoint_ring,
                "baseline_available": bool(baseline_checkpoint_id and root_retries_used < max_root_retries),
                "student_messages": messages,
                "last_step_payload": last_step_payload,
                "last_state_payload": last_state_payload,
            }
            decision, decision_payload, decision_raw = _teacher_controller_decision(
                api_base=resolved_teacher_api_base,
                api_key=resolved_teacher_api_key,
                model=teacher_model,
                controller_context=controller_context,
                reasoning_effort=teacher_reasoning_effort,
                timeout=model_timeout,
            )
            teacher_calls += 1
            _append_event(
                events_path,
                {
                    "kind": "teacher_decision",
                    "step_index": step_index,
                    "decision": decision,
                    "response": decision_payload,
                    "raw_text": decision_raw,
                },
            )
        else:
            decision = _heuristic_controller_decision(
                no_progress_commands=no_progress_commands,
                current_observation=current_observation,
                latest_changed_files=latest_changed_files,
                checkpoint_ring=checkpoint_ring,
                root_retries_used=root_retries_used,
                max_root_retries=max_root_retries,
                stall_class=stall_class,
            )

        if not eval_mode:
            requested_target = str(decision.get("restore_target") or "CURRENT").upper()
            decision_stall_class = str(decision.get("stall_class") or stall_class or "none").strip().lower()
            if decision_stall_class not in {
                "none",
                "no_action",
                "repeat_read_loop",
                "repeat_search_loop",
                "stuck_patch",
                "bad_patch_loop",
                "verify_loop",
            }:
                decision_stall_class = stall_class
            if latest_changed_files and requested_target != "CURRENT" and decision_stall_class in {"none", "repeat_read_loop", "repeat_search_loop"}:
                requested_target = "CURRENT"
            restore_target, target_resolution = _resolve_restore_target(
                requested_target=requested_target,
                checkpoint_ring=edit_checkpoints,
                baseline_available=bool(baseline_checkpoint_id and root_retries_used < max_root_retries),
                total_restores_used=total_restores_used,
                lineage_retry_count=lineage_retry_count,
                stall_class=decision_stall_class,
            )
            if restore_target != "CURRENT":
                if teacher_model:
                    teacher_branch_calls += 1
                    _append_event(
                        events_path,
                        {
                            "kind": "teacher_branch",
                            "step_index": step_index,
                            "requested_target": requested_target,
                            "effective_target": restore_target,
                            "target_resolution": target_resolution,
                            "stall_class": decision_stall_class,
                            "reason": decision.get("reason", ""),
                        },
                    )
                if restore_target == "STOP":
                    last_restore_target_applied = "STOP"
                    terminal_status = "failed_loop_budget" if target_resolution in {
                        "restore_budget_exhausted",
                        "lineage_retry_budget_exhausted",
                        "rollback_unavailable",
                        "baseline_unavailable",
                    } else "teacher_stop"
                    _append_event(
                        events_path,
                        {
                            "kind": "control_stop",
                            "step_index": step_index,
                            "requested_target": requested_target,
                            "effective_target": restore_target,
                            "target_resolution": target_resolution,
                            "stall_class": decision_stall_class,
                            "reason": decision.get("reason", ""),
                        },
                    )
                    break

                checkpoint_id = baseline_checkpoint_id
                scope = "baseline"
                if restore_target.startswith("ROLLBACK_"):
                    rollback_index = int(restore_target.split("_", 1)[1]) - 1
                    checkpoint_entry = edit_checkpoints[rollback_index]
                    checkpoint_id = str(checkpoint_entry.get("checkpoint_id") or "")
                    scope = restore_target.lower()
                restored = openenv_restore(output_dir=output_dir, episode_id=episode_id, checkpoint_id=checkpoint_id)
                total_restores_used += 1
                lineage_retry_counts[current_lineage_key] = lineage_retry_count + 1
                last_restore_target_applied = restore_target
                if restore_target == "BASELINE":
                    root_retries_used += 1
                    student_messages = copy.deepcopy(checkpoint_student_messages.get(baseline_checkpoint_id, student_messages))
                    latest_changed_files = []
                    current_lineage_key = "no_patch"
                    last_viewed_file = ""
                    last_candidate_file = ""
                    last_patch_hash = ""
                else:
                    edit_retries_used += 1
                    checkpoint_entry = edit_checkpoints[int(restore_target.split("_", 1)[1]) - 1]
                    student_messages = copy.deepcopy(checkpoint_student_messages.get(checkpoint_id, student_messages))
                    latest_changed_files = [str(item) for item in (checkpoint_entry.get("changed_files") or [])]
                    last_patch_hash = str(checkpoint_entry.get("patch_hash") or "")
                    current_lineage_key = _lineage_key(
                        latest_changed_files=latest_changed_files,
                        current_patch_hash=last_patch_hash,
                    )
                same_patch_steps = 0
                stall_class = "none"
                teacher_think_text = ""
                current_observation = str(restored.get("observation") or current_observation)
                _append_event(
                    events_path,
                    {
                        "kind": "restore",
                        "scope": scope,
                        "requested_target": requested_target,
                        "effective_target": restore_target,
                        "target_resolution": target_resolution,
                        "payload": restored,
                    },
                )
                if total_restores_used >= MAX_TOTAL_RESTORES_PER_RUN:
                    terminal_status = "failed_loop_budget"
                    continue
                continue

        if decision.get("inject_teacher_think") and decision.get("teacher_think_text") and not eval_mode:
            teacher_think_text = _clean_reasoning_text(str(decision.get("teacher_think_text") or ""))
            teacher_think_calls += 1
            _append_event(
                events_path,
                {
                    "kind": "teacher_think",
                    "step_index": step_index,
                    "preferred_runtime": preferred_runtime,
                    "text": teacher_think_text,
                    "think_text": teacher_think_text,
                    "reason": decision.get("reason", ""),
                },
            )
        else:
            teacher_think_text = ""
        messages = _merge_teacher_think_into_messages(student_messages, teacher_think_text)
        messages, trimmed_pairs = _trim_messages_to_context_limit(
            model=model,
            messages=messages,
            enable_thinking=student_enable_thinking,
            max_context_tokens=student_max_context_tokens,
        )
        if trimmed_pairs:
            _append_event(
                events_path,
                {
                    "kind": "context_trim",
                    "step_index": step_index,
                    "removed_pairs": trimmed_pairs,
                    "limit": student_max_context_tokens,
                },
            )
        model_payload, used_transport_retries = _chat_completion_with_transport_retry(
            transport_only_retries=transport_only_retries if eval_mode else 0,
            api_base=api_base,
            api_key=resolved_api_key,
            model=model,
            messages=messages,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            timeout=model_timeout,
            enable_thinking=student_enable_thinking,
            student_max_new_tokens=student_max_new_tokens,
            retry_without_think_on_no_text=True,
        )
        transport_retries_used += used_transport_retries
        final_model_payload = model_payload
        student_calls += 1
        raw_action_text = _extract_text(model_payload)
        action_text = _normalize_action_text(
            raw_action_text,
            prefer_edit=bool(last_viewed_file or "no file changes were made" in lowered_observation),
            prefer_verify=bool(latest_changed_files),
            prefer_view=bool(last_candidate_file and not last_viewed_file and not latest_changed_files),
        )
        if eval_mode and _is_model_stop_response(action_text):
            terminal_status = "model_stop"
            finish_reason_type = _finish_reason_type_from_payload(model_payload)
            model_stop_reason = "generation_truncated" if finish_reason_type == "length" else "no_executable_action"
            _append_event(
                events_path,
                {
                    "kind": "eval_stop",
                    "step_index": step_index,
                    "reason": "model_stop",
                    "model_stop_reason": model_stop_reason,
                    "raw_action_text": raw_action_text,
                    "action_text": action_text,
                    "messages": messages,
                    "response": model_payload,
                },
            )
            break
        action_text = _materialize_action_text(action_text)
        command_text = _extract_command(action_text)
        command_signature = _normalize_command_signature(command_text)
        if not eval_mode:
            rewritten_command = _rewrite_command_for_runtime(command_text, preferred_runtime)
            if rewritten_command != command_text:
                action_text = f"```bash\n{rewritten_command}\n```"
                _append_event(
                    events_path,
                    {
                        "kind": "command_rewritten",
                        "step_index": step_index,
                        "from_command": command_text,
                        "to_command": rewritten_command,
                        "preferred_runtime": preferred_runtime,
                    },
                )
                command_text = rewritten_command
                command_signature = _normalize_command_signature(command_text)
            uses_unavailable, unavailable_runtime = _command_uses_unavailable_runtime(command_text, preferred_runtime)
            if uses_unavailable:
                current_observation = (
                    f"The previous proposed action used `{unavailable_runtime}`, which is not the preferred edit runtime in this environment. "
                    f"Use `{preferred_runtime}` instead. {_edit_runtime_guidance(preferred_runtime)}"
                )
                _append_event(
                    events_path,
                    {
                        "kind": "command_rejected",
                        "step_index": step_index,
                        "action_text": action_text,
                        "preferred_runtime": preferred_runtime,
                        "unavailable_runtime": unavailable_runtime,
                    },
                )
                stall_class = "no_action"
                step_index += 1
                continue
        _append_event(
            events_path,
            {
                "kind": "model_action",
                "step_index": step_index,
                "messages": messages,
                "actor": "student",
                "requested_model": model,
                "response": model_payload,
                "raw_action_text": raw_action_text,
                "action_text": action_text,
            },
        )
        if _is_model_stop_response(action_text):
            stall_class = "no_action"
            step_index += 1
            continue

        step_payload = openenv_step(output_dir=output_dir, episode_id=episode_id, action_text=action_text)
        last_step_payload = step_payload
        final_step = step_payload
        _append_event(events_path, {"kind": "step", "step_index": step_index, "payload": step_payload})
        student_messages.append({"role": "assistant", "content": action_text})
        student_messages.append({"role": "user", "content": str(step_payload.get("observation") or "")})

        state_payload = openenv_state(output_dir=output_dir, episode_id=episode_id)
        last_state_payload = state_payload
        _append_event(events_path, {"kind": "state", "step_index": step_index, "payload": state_payload})
        latest_changed_files = _changed_files_from_state(state_payload)
        current_patch_hash = _patch_hash_from_state(state_payload)
        executed_command = command_text
        returncode = _returncode_from_observation(str(step_payload.get("observation") or ""))
        step_observation_text = str(step_payload.get("observation") or "")
        output_text = _extract_output(step_observation_text)
        lowered_step_observation = step_observation_text.lower()
        if "python3: command not found" in lowered_step_observation and runtime_availability.get("python3"):
            runtime_availability["python3"] = False
        elif "python: command not found" in lowered_step_observation and runtime_availability.get("python"):
            runtime_availability["python"] = False
        elif "ruby: command not found" in lowered_step_observation and runtime_availability.get("ruby"):
            runtime_availability["ruby"] = False
        preferred_runtime = _preferred_runtime_from_availability(runtime_availability)

        if returncode == 0 and _is_file_view_command(executed_command) and output_text:
            last_viewed_file = _extract_viewed_file(executed_command) or last_candidate_file
            last_candidate_file = ""
        elif output_text and _is_search_command(executed_command):
            last_candidate_file = _extract_first_candidate_file(output_text) or last_candidate_file

        if (not eval_mode) and latest_changed_files and current_patch_hash and current_patch_hash != last_patch_hash:
            edit_checkpoint = openenv_checkpoint(
                output_dir=output_dir,
                episode_id=episode_id,
                label=f"post-edit-{step_index + 1}",
            )
            _append_event(
                events_path,
                {"kind": "checkpoint", "label": f"post-edit-{step_index + 1}", "payload": edit_checkpoint},
            )
            edit_checkpoint_id = str(edit_checkpoint.get("checkpoint_id") or "")
            if edit_checkpoint_id:
                checkpoint_student_messages[edit_checkpoint_id] = copy.deepcopy(student_messages)
                edit_checkpoints.insert(
                    0,
                    {
                        "checkpoint_id": edit_checkpoint_id,
                        "step_index": step_index,
                        "patch_hash": current_patch_hash,
                        "changed_files": list(latest_changed_files),
                    },
                )
                edit_checkpoints = edit_checkpoints[:MAX_EDIT_CHECKPOINTS]

        recent_command_signatures.append(command_signature)
        recent_command_signatures = recent_command_signatures[-8:]
        patch_repeat_command_kind = ""
        if latest_changed_files and current_patch_hash and current_patch_hash == last_patch_hash:
            same_patch_steps += 1
            if _is_verify_command(executed_command):
                patch_repeat_command_kind = "verify"
            elif _is_file_view_command(executed_command) or _is_search_command(executed_command):
                patch_repeat_command_kind = "read"
        else:
            same_patch_steps = 0

        stall_class = _classify_stall(
            raw_action_text=raw_action_text,
            action_text=action_text,
            command_signature=command_signature,
            command_history=recent_command_signatures,
            latest_changed_files=latest_changed_files,
            same_patch_steps=same_patch_steps,
            patch_repeat_command_kind=patch_repeat_command_kind,
        )
        current_lineage_key = _lineage_key(
            latest_changed_files=latest_changed_files,
            current_patch_hash=current_patch_hash,
        )
        if current_patch_hash:
            last_patch_hash = current_patch_hash

        if bool(step_payload.get("done")) or bool(step_payload.get("truncated")):
            current_observation = str(step_payload.get("observation") or "")
            terminal_status = "done" if bool(step_payload.get("done")) else "truncated"
            break

        useful_search = bool(output_text and _is_search_command(executed_command) and not _is_no_progress_command(executed_command))
        if _is_no_progress_command(executed_command):
            no_progress_commands.append(executed_command)
        elif returncode not in (None, 0) and not useful_search:
            no_progress_commands.append(f"{executed_command}  # rc={returncode}")

        current_observation = str(step_payload.get("observation") or "")
        if stall_class == "none":
            lineage_retry_counts[current_lineage_key] = 0
        step_index += 1
        continue

    stop_payload = openenv_stop(output_dir=output_dir, episode_id=episode_id)
    _append_event(events_path, {"kind": "stop", "payload": stop_payload})

    summary = _build_synthesis_summary(
        task_id=task_id,
        episode_id=episode_id,
        model=model,
        teacher_model=teacher_model,
        reasoning_effort=reasoning_effort,
        teacher_reasoning_effort=teacher_reasoning_effort,
        api_base=api_base,
        resolved_teacher_api_base=resolved_teacher_api_base,
        upstream_repo_path=upstream_repo_path,
        upstream_git_url=upstream_git_url,
        upstream_ref=upstream_ref,
        baseline_checkpoint_id=baseline_checkpoint_id,
        edit_checkpoint_id=edit_checkpoint_id,
        root_retries_used=root_retries_used,
        edit_retries_used=edit_retries_used,
        student_calls=student_calls,
        teacher_calls=teacher_calls,
        teacher_branch_calls=teacher_branch_calls,
        teacher_think_calls=teacher_think_calls,
        probe_runtime=probe_runtime,
        inject_teacher_think=inject_teacher_think,
        student_enable_thinking=student_enable_thinking,
        student_max_new_tokens=student_max_new_tokens,
        student_max_context_tokens=student_max_context_tokens,
        final_model_payload=final_model_payload,
        eval_mode=eval_mode,
        eval_max_context_tokens=eval_max_context_tokens,
        last_context_tokens=last_context_tokens,
        runtime_availability=runtime_availability,
        preferred_runtime=preferred_runtime,
        latest_changed_files=latest_changed_files,
        final_step=final_step,
        model_stop_reason=model_stop_reason,
        stall_class=stall_class,
        last_restore_target_applied=last_restore_target_applied,
        total_restores_used=total_restores_used,
        edit_checkpoints=edit_checkpoints,
        terminal_status=terminal_status,
        events_path=events_path,
        transport_retries_used=transport_retries_used,
        failure_stage="",
        failure_reason="",
        exception_type="",
        exception_message="",
    )
    manifest_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


def run_openenv_synthesis(
    *,
    output_dir: str,
    upstream_repo_path: str = "",
    upstream_git_url: str = DEFAULT_AFFINETES_GIT_URL,
    upstream_ref: str,
    upstream_python: str = "python3",
    cache_dir: str = DEFAULT_SWE_CACHE_DIR,
    task_id: str,
    api_base: str,
    model: str,
    api_key: str = "",
    api_key_file: str = "",
    teacher_model: str = "",
    teacher_api_base: str = "",
    teacher_api_key: str = "",
    teacher_api_key_file: str = "",
    temperature: float = 0.2,
    teacher_temperature: float = 0.0,
    reasoning_effort: str = "low",
    teacher_reasoning_effort: str = "low",
    step_limit: int = 20,
    command_timeout: int = 60,
    model_timeout: int = 180,
    transport_only_retries: int = 0,
    max_steps: int = 4,
    max_root_retries: int = 1,
    max_edit_retries: int = 1,
    probe_runtime: bool = False,
    inject_teacher_think: bool = False,
    student_enable_thinking: bool = False,
    student_max_new_tokens: int = 4096,
    student_max_context_tokens: int = STUDENT_MAX_CONTEXT_TOKENS_DEFAULT,
    eval_mode: bool = False,
    eval_max_context_tokens: int = 32768,
) -> dict[str, Any]:
    try:
        return _run_openenv_synthesis_impl(
            output_dir=output_dir,
            upstream_repo_path=upstream_repo_path,
            upstream_git_url=upstream_git_url,
            upstream_ref=upstream_ref,
            upstream_python=upstream_python,
            cache_dir=cache_dir,
            task_id=task_id,
            api_base=api_base,
            model=model,
            api_key=api_key,
            api_key_file=api_key_file,
            teacher_model=teacher_model,
            teacher_api_base=teacher_api_base,
            teacher_api_key=teacher_api_key,
            teacher_api_key_file=teacher_api_key_file,
            temperature=temperature,
            teacher_temperature=teacher_temperature,
            reasoning_effort=reasoning_effort,
            teacher_reasoning_effort=teacher_reasoning_effort,
            step_limit=step_limit,
            command_timeout=command_timeout,
            model_timeout=model_timeout,
            transport_only_retries=transport_only_retries,
            max_steps=max_steps,
            max_root_retries=max_root_retries,
            max_edit_retries=max_edit_retries,
            probe_runtime=probe_runtime,
            inject_teacher_think=inject_teacher_think,
            student_enable_thinking=student_enable_thinking,
            student_max_new_tokens=student_max_new_tokens,
            student_max_context_tokens=student_max_context_tokens,
            eval_mode=eval_mode,
            eval_max_context_tokens=eval_max_context_tokens,
        )
    except Exception as exc:
        root = _ensure_dir(output_dir)
        events_path = root / "raw" / "synthesis_events.jsonl"
        manifest_path = root / "manifests" / "synthesis_run.json"
        if not events_path.exists():
            events_path.write_text("", encoding="utf-8")

        resolved_api_key = _read_api_key(api_key=api_key, api_key_file=api_key_file)
        if eval_mode:
            teacher_model = ""
            teacher_api_base = ""
            teacher_api_key = ""
            teacher_api_key_file = ""
            max_root_retries = 0
            max_edit_retries = 0
            probe_runtime = False
            inject_teacher_think = False
        resolved_teacher_api_key = _read_api_key(api_key=teacher_api_key, api_key_file=teacher_api_key_file) or resolved_api_key
        resolved_teacher_api_base = _resolve_teacher_api_base(
            student_api_base=api_base,
            teacher_api_base=teacher_api_base,
            teacher_model=teacher_model,
            teacher_api_key=teacher_api_key,
            teacher_api_key_file=teacher_api_key_file,
        )
        failure_stage = "student_transport" if _is_retryable_transport_error(exc) else "launch"
        terminal_status = _terminal_status_for_failure(failure_stage=failure_stage, exc=exc)

        episode_id = ""
        session_path = root / "raw" / "openenv_session.json"
        if session_path.exists():
            try:
                session_payload = json.loads(session_path.read_text(encoding="utf-8"))
                episode_id = str(session_payload.get("last_episode_id") or episode_id)
            except Exception:
                pass
        try:
            if episode_id and (root / ".runtime" / "openenv_server.json").exists():
                stop_payload = openenv_stop(output_dir=output_dir, episode_id=episode_id)
                _append_event(events_path, {"kind": "stop", "scope": "exception_cleanup", "payload": stop_payload})
        except Exception as stop_exc:
            _append_event(events_path, {"kind": "stop_error", "scope": "exception_cleanup", "error": str(stop_exc)})
        _append_event(
            events_path,
            {
                "kind": "fatal_error",
                "failure_stage": failure_stage,
                "terminal_status": terminal_status,
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
        )
        summary = _build_synthesis_summary(
            task_id=task_id,
            episode_id=episode_id,
            model=model,
            teacher_model=teacher_model,
            reasoning_effort=reasoning_effort,
            teacher_reasoning_effort=teacher_reasoning_effort,
            api_base=api_base,
            resolved_teacher_api_base=resolved_teacher_api_base,
            upstream_repo_path=upstream_repo_path,
            upstream_git_url=upstream_git_url,
            upstream_ref=upstream_ref,
            baseline_checkpoint_id="",
            edit_checkpoint_id="",
            root_retries_used=0,
            edit_retries_used=0,
            student_calls=0,
            teacher_calls=0,
            teacher_branch_calls=0,
            teacher_think_calls=0,
            probe_runtime=probe_runtime,
            inject_teacher_think=inject_teacher_think,
            student_enable_thinking=student_enable_thinking,
            student_max_new_tokens=student_max_new_tokens,
            student_max_context_tokens=student_max_context_tokens,
            final_model_payload=None,
            eval_mode=eval_mode,
            eval_max_context_tokens=eval_max_context_tokens,
            last_context_tokens=0,
            runtime_availability={"python3": False, "python": False, "ruby": False, "perl": False},
            preferred_runtime="",
            latest_changed_files=[],
            final_step=None,
            model_stop_reason="",
            stall_class="none",
            last_restore_target_applied="CURRENT",
            total_restores_used=0,
            edit_checkpoints=[],
            terminal_status=terminal_status,
            events_path=events_path,
            transport_retries_used=0,
            failure_stage=failure_stage,
            failure_reason=terminal_status,
            exception_type=type(exc).__name__,
            exception_message=str(exc),
        )
        manifest_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        return summary
