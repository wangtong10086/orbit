"""Minimal OpenEnv-based SWE synthesis controller.

This stays above upstream `SWE-INFINITE` as a thin orchestration layer:
- uses upstream OpenEnv reset/state/checkpoint/restore/step/stop
- uses a single OpenAI-compatible model as the action generator
- records raw events and a small run manifest

The goal is to validate real synthesis with checkpoint/retry/rollback without
reintroducing ORBIT-side environment semantics.
"""

from __future__ import annotations

import json
import re
import shlex
import time
from pathlib import Path
from typing import Any

from openai import OpenAI

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


SYSTEM_PROMPT = """You are controlling an upstream SWE-INFINITE OpenEnv episode.
Return exactly one of:
1. A single ```bash ... ``` block
2. The literal token <SUBMIT>

Rules:
- Never output prose outside the action.
- Keep commands short and local to /app.
- Prefer minimal edits and concrete verification steps.
- If you already have a good patch staged, you may return <SUBMIT>.
- Never return more than one bash block.
- Do not repeat an earlier no-progress command such as plain `ls`, `ls -la`,
  or other generic repository listings.
- If the issue names a class, cop, method, or option, prefer targeted
  `git grep -n` or `grep -R -n` search over generic listing commands.
"""


TEACHER_SYSTEM_PROMPT = """You are the teacher model guiding an upstream SWE-INFINITE OpenEnv episode.
Return exactly one of:
1. A single ```bash ... ``` block
2. The literal token <SUBMIT>

Rules:
- Never output prose outside the action.
- Give exactly one next action, not a plan.
- When the target file has already been inspected, do not search again unless the latest feedback explicitly proves the file is wrong.
- Prefer minimal, deterministic edit commands over compact regex one-liners for multi-line edits.
- Prefer a small `ruby - <<'RUBY'` script that reads the file, checks an exact needle with `include?`, applies one `sub`, raises if the needle is absent, and writes the file back.
- If the current patch is ready, you may return <SUBMIT>.
"""

UPSTREAM_SUBMIT_COMMAND = "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && git add -A && git diff --cached"


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
            "ruby - <<",
            "python -c",
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


def _is_no_progress_command(command: str) -> bool:
    normalized = re.sub(r"\s+", " ", command.strip()).lower()
    return normalized in {
        "cd /app && ls",
        "cd /app && ls -la",
        "ls",
        "ls -la",
        "pwd",
        "cd /app && pwd",
        "git status",
        "cd /app && git status",
    }


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


def _chat_completion(
    *,
    api_base: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    reasoning_effort: str,
    timeout: int,
) -> dict[str, Any]:
    try:
        client = OpenAI(base_url=api_base, api_key=api_key, timeout=timeout)
        response = client.responses.create(
            model=model,
            reasoning={"effort": reasoning_effort},
            input=messages,
        )
        return {
            "id": getattr(response, "id", ""),
            "model": getattr(response, "model", model),
            "output_text": getattr(response, "output_text", ""),
        }
    except Exception as exc:  # pragma: no cover - exercised by real runs
        raise RuntimeError(f"responses.create failed: {exc}") from exc


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
    max_steps: int = 4,
    max_root_retries: int = 1,
    max_edit_retries: int = 1,
) -> dict[str, Any]:
    root = _ensure_dir(output_dir)
    events_path = root / "raw" / "synthesis_events.jsonl"
    manifest_path = root / "manifests" / "synthesis_run.json"
    events_path.write_text("", encoding="utf-8")

    resolved_api_key = _read_api_key(api_key=api_key, api_key_file=api_key_file)
    if not resolved_api_key:
        raise RuntimeError("api_key or api_key_file is required for synthesis")
    resolved_teacher_api_key = _read_api_key(api_key=teacher_api_key, api_key_file=teacher_api_key_file) or resolved_api_key
    resolved_teacher_api_base = teacher_api_base or api_base

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
    _append_event(events_path, {"kind": "reset", "payload": reset})
    episode_id = str(reset.get("episode_id") or "")
    if not episode_id:
        raise RuntimeError(f"reset did not return episode_id: {reset}")

    baseline = openenv_checkpoint(output_dir=output_dir, episode_id=episode_id, label="baseline")
    _append_event(events_path, {"kind": "checkpoint", "label": "baseline", "payload": baseline})
    baseline_checkpoint_id = str(baseline.get("checkpoint_id") or "")
    if not baseline_checkpoint_id:
        raise RuntimeError(f"baseline checkpoint failed: {baseline}")

    current_observation = str(reset.get("observation") or "")
    issue_context = _extract_issue_context(current_observation)
    root_retries_used = 0
    edit_retries_used = 0
    edit_checkpoint_id = ""
    latest_changed_files: list[str] = []
    final_step: dict[str, Any] | None = None
    no_progress_commands: list[str] = []
    last_viewed_file = ""
    last_candidate_file = ""
    student_calls = 0
    teacher_calls = 0
    last_patch_hash = ""
    edited_stall_count = 0
    last_followup_signature = ""
    post_edit_stall_steps = 0

    for step_index in range(max_steps):
        prompt_parts = []
        if issue_context:
            prompt_parts.append(f"Issue or PR description:\n{issue_context}")
        if latest_changed_files:
            prompt_parts.append(
                "The working tree already contains edits in:\n- "
                + "\n- ".join(latest_changed_files)
                + "\nDo not search again. Your next command must either verify the current patch or make one small revision to it."
            )
        elif last_viewed_file:
            prompt_parts.append(
                f"You already inspected `{last_viewed_file}`. Do not search again. "
                "Your next command must make one minimal non-interactive edit to that file. "
                "Prefer a small `ruby - <<'RUBY'` script that reads the file, checks an exact needle with `include?`, "
                "uses `sub` for one targeted replacement, raises if the needle is absent, and writes the file back. "
                "Avoid compact `ruby -0pi -e` or `perl -0pi -e` regex one-liners for multi-line edits."
            )
        elif last_candidate_file:
            prompt_parts.append(
                f"The previous targeted search identified `{last_candidate_file}` as the next candidate. "
                "Do not search or run tests yet. Your next command must inspect that file directly with `sed -n` or `nl -ba`."
            )
        if current_observation and current_observation != reset.get("observation", ""):
            prompt_parts.append(f"Latest environment feedback:\n{current_observation}")
        if no_progress_commands:
            prompt_parts.append(
                "Avoid repeating these no-progress commands:\n- "
                + "\n- ".join(no_progress_commands[-4:])
            )
            prompt_parts.append(
                "Your next command must be more targeted than a generic directory listing. "
                "Prefer git grep/grep -R/nl/sed on the most relevant symbol, class, cop, or option named in the issue."
            )
        lowered_observation = current_observation.lower()
        if "command not found" in lowered_observation and "rg" in lowered_observation:
            prompt_parts.append("The previous attempt failed because `rg` is unavailable in this environment. Use `git grep -n` or `grep -R -n` instead.")
        if "python: command not found" in lowered_observation:
            prompt_parts.append(
                "The previous edit failed because `python` is unavailable in this environment. "
                "Use a `ruby - <<'RUBY'` edit script instead."
            )
        if "ruby: command not found" in lowered_observation:
            prompt_parts.append(
                "The previous edit failed because `ruby` is unavailable in this environment. "
                "Use `python - <<'PY'` without `pathlib`, or use `awk`/`sed` for a minimal edit."
            )
        if "importerror: no module named pathlib" in lowered_observation:
            prompt_parts.append(
                "The previous edit failed because this environment does not provide `pathlib`. "
                "Use plain `open(...).read()` / `open(..., \"w\")` in `python - <<'PY'`, or use `awk`/`sed`."
            )
        if "syntax error" in lowered_observation and ("ruby -0pi -e" in lowered_observation or "perl -0pi -e" in lowered_observation):
            prompt_parts.append(
                "The previous regex one-liner edit was malformed. Do not use another `-pi -e` one-liner. "
                "Use a small `ruby - <<'RUBY'` script with `include?`, `sub`, and `File.write`."
            )
        use_teacher = bool(
            teacher_model
            and (
                latest_changed_files
                or last_viewed_file
                or "no file changes were made" in lowered_observation
                or "python: command not found" in lowered_observation
                or "syntax error" in lowered_observation
            )
        )
        call_model = teacher_model if use_teacher else model
        call_api_base = resolved_teacher_api_base if use_teacher else api_base
        call_api_key = resolved_teacher_api_key if use_teacher else resolved_api_key
        call_temperature = teacher_temperature if use_teacher else temperature
        call_reasoning_effort = teacher_reasoning_effort if use_teacher else reasoning_effort
        messages = [
            {"role": "system", "content": TEACHER_SYSTEM_PROMPT if use_teacher else SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "\n\n".join(part for part in prompt_parts if part).strip() + "\n\nReturn exactly one action.",
            },
        ]
        model_payload = _chat_completion(
            api_base=call_api_base,
            api_key=call_api_key,
            model=call_model,
            messages=messages,
            temperature=call_temperature,
            reasoning_effort=call_reasoning_effort,
            timeout=model_timeout,
        )
        if use_teacher:
            teacher_calls += 1
        else:
            student_calls += 1
        raw_action_text = _extract_text(model_payload)
        action_text = _normalize_action_text(
            raw_action_text,
            prefer_edit=bool(last_viewed_file or "no file changes were made" in lowered_observation),
            prefer_verify=bool(latest_changed_files),
            prefer_view=bool(last_candidate_file and not last_viewed_file and not latest_changed_files),
        )
        action_text = _materialize_action_text(action_text)
        _append_event(
            events_path,
            {
                "kind": "model_action",
                "step_index": step_index,
                "messages": messages,
                "actor": "teacher" if use_teacher else "student",
                "requested_model": call_model,
                "response": model_payload,
                "raw_action_text": raw_action_text,
                "action_text": action_text,
            },
        )

        step_payload = openenv_step(output_dir=output_dir, episode_id=episode_id, action_text=action_text)
        final_step = step_payload
        _append_event(events_path, {"kind": "step", "step_index": step_index, "payload": step_payload})

        state_payload = openenv_state(output_dir=output_dir, episode_id=episode_id)
        _append_event(events_path, {"kind": "state", "step_index": step_index, "payload": state_payload})
        latest_changed_files = _changed_files_from_state(state_payload)
        current_patch_hash = _patch_hash_from_state(state_payload)
        executed_command = _extract_command(action_text)
        returncode = _returncode_from_observation(str(step_payload.get("observation") or ""))
        output_text = _extract_output(str(step_payload.get("observation") or ""))

        if returncode == 0 and _is_file_view_command(executed_command) and output_text:
            last_viewed_file = _extract_viewed_file(executed_command) or last_candidate_file
            last_candidate_file = ""
        elif output_text and _is_search_command(executed_command):
            last_candidate_file = _extract_first_candidate_file(output_text) or last_candidate_file

        if latest_changed_files and not edit_checkpoint_id:
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

        if latest_changed_files:
            repeated_followup = _is_verify_command(executed_command) or _is_file_view_command(executed_command)
            followup_signature = f"{executed_command}|{returncode}|{output_text[:200]}"
            if current_patch_hash and current_patch_hash != last_patch_hash:
                edited_stall_count = 0
                last_followup_signature = ""
                post_edit_stall_steps = 0
            elif repeated_followup and current_patch_hash:
                if followup_signature == last_followup_signature or _is_verify_command(executed_command) or not output_text.strip():
                    edited_stall_count += 1
                else:
                    edited_stall_count = 0
                last_followup_signature = followup_signature
                post_edit_stall_steps += 1
            else:
                edited_stall_count = 0
                last_followup_signature = ""
                if current_patch_hash == last_patch_hash and not _is_edit_command(executed_command):
                    post_edit_stall_steps += 1
                else:
                    post_edit_stall_steps = 0
            if current_patch_hash:
                last_patch_hash = current_patch_hash

            if edit_checkpoint_id and (edited_stall_count > 0 or post_edit_stall_steps >= 2) and edit_retries_used < max_edit_retries:
                restored = openenv_restore(output_dir=output_dir, episode_id=episode_id, checkpoint_id=edit_checkpoint_id)
                edit_retries_used += 1
                edited_stall_count = 0
                last_followup_signature = ""
                post_edit_stall_steps = 0
                current_observation = (
                    "Restored the last edited checkpoint. The previous follow-up action did not change the patch or advance verification. "
                    "Try a different next step from the same edited state. Do not repeat verify-only or file-view commands. "
                    "If the patch is already ready, return <SUBMIT>."
                )
                _append_event(events_path, {"kind": "restore", "scope": "edit", "payload": restored})
                continue

        if bool(step_payload.get("done")) or bool(step_payload.get("truncated")):
            current_observation = str(step_payload.get("observation") or "")
            break

        if latest_changed_files:
            if "verified" in output_text.lower():
                current_observation = (
                    str(step_payload.get("observation") or "")
                    + "\nThe current patch passed the latest verification check. If it is ready, return <SUBMIT>."
                )
            else:
                current_observation = str(step_payload.get("observation") or "")
            continue

        if output_text and _is_search_command(executed_command) and not _is_no_progress_command(executed_command):
            current_observation = str(step_payload.get("observation") or "")
            continue

        if returncode == 0 and not _is_no_progress_command(executed_command):
            current_observation = str(step_payload.get("observation") or "")
            continue

        if _is_no_progress_command(executed_command):
            no_progress_commands.append(executed_command)
        elif returncode not in (None, 0):
            no_progress_commands.append(f"{executed_command}  # rc={returncode}")

        if edit_checkpoint_id and edit_retries_used < max_edit_retries:
            restored = openenv_restore(output_dir=output_dir, episode_id=episode_id, checkpoint_id=edit_checkpoint_id)
            edit_retries_used += 1
            current_observation = "Restored the last edited checkpoint. The previous follow-up action was not useful. Try a different next step from the same edited state."
            _append_event(events_path, {"kind": "restore", "scope": "edit", "payload": restored})
            continue

        if last_viewed_file and step_index + 1 < max_steps:
            current_observation = (
                str(step_payload.get("observation") or "")
                + f"\nNo file changes were made. Stay on `{last_viewed_file}` and try a different direct edit command. Do not search again."
            )
            continue

        if root_retries_used < max_root_retries:
            restored = openenv_restore(output_dir=output_dir, episode_id=episode_id, checkpoint_id=baseline_checkpoint_id)
            root_retries_used += 1
            edit_retries_used = 0
            edit_checkpoint_id = ""
            last_viewed_file = ""
            current_observation = "Restored the baseline checkpoint. The previous first action was not useful. Try a different first action."
            _append_event(events_path, {"kind": "restore", "scope": "baseline", "payload": restored})
            continue

        current_observation = str(step_payload.get("observation") or "")
        break

    stop_payload = openenv_stop(output_dir=output_dir, episode_id=episode_id)
    _append_event(events_path, {"kind": "stop", "payload": stop_payload})

    summary = {
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
        "latest_changed_files": latest_changed_files,
        "final_observation": str(final_step.get("observation") if final_step else ""),
        "final_done": bool(final_step.get("done")) if final_step else False,
        "final_truncated": bool(final_step.get("truncated")) if final_step else False,
        "events_path": str(events_path),
    }
    manifest_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary
