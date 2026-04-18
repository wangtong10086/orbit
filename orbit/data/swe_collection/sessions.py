"""Student sampling and teacher critique sessions for SWE collection."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from orbit.prompt.tools import load_tools


ACTION_RE = re.compile(r"```bash\s*\n(.*?)(?:\n```|\Z)", re.DOTALL)
LINE_NUMBER_PREFIX_RE = re.compile(r"^\s*\d{4}:\s?")
SUBMIT_MARKER = "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"
REALIZATION_MAX_TOKENS = 1600
RETRYABLE_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}
OPENAI_COMPAT_TIMEOUT_SECONDS = max(int(os.getenv("ORBIT_SWE_HTTP_TIMEOUT_SECONDS", "45") or "45"), 1)
OPENAI_COMPAT_MAX_RETRIES = max(int(os.getenv("ORBIT_SWE_HTTP_MAX_RETRIES", "2") or "2"), 1)


@dataclass
class StudentTurn:
    assistant_message: dict
    command: str = ""
    submit: bool = False
    action_state: str = "ok"
    tool_name: str = "shell"
    action: dict | None = None


@dataclass
class CritiqueTurn:
    critique: str
    revised_action: str
    raw_response: str


@dataclass
class LocalizationProposal:
    candidate_files: tuple[str, ...]
    candidate_symbols: tuple[str, ...]
    hypothesis: str
    edit_type: str
    raw_response: str


@dataclass
class PatchPlanProposal:
    target_files: tuple[str, ...]
    target_symbols: tuple[str, ...]
    diff_sketch: str
    plan_steps: tuple[str, ...]
    edit_type: str
    raw_response: str


@dataclass
class PatchActionProposal:
    file_id: str
    span_id: str
    target_file: str
    start_line: int
    end_line: int
    edit_type: str
    replacement: str
    submit: bool
    rationale: str
    raw_response: str


@dataclass
class IssueRubricTurn:
    likely_modules: tuple[str, ...]
    required_constraints: tuple[str, ...]
    common_pseudo_solutions: tuple[str, ...]
    forbidden_patterns: tuple[str, ...]
    raw_response: str


@dataclass
class TeacherJudgeDecisionTurn:
    score: float
    decision: str
    stop_reason: str
    failure_risk: float
    branch_proposals: list[dict]
    raw_response: str


@dataclass
class TeacherStateSummaryTurn:
    root_cause_guess: str
    target_file_ids: tuple[str, ...]
    target_span_ids: tuple[str, ...]
    minimal_edit_direction: str
    prior_score: float
    value_score: float
    submit_likelihood: float
    dead_end_risk: float
    branch_proposals: list[dict]
    raw_response: str


class SweStudentSession(Protocol):
    format: str
    endpoint: str
    model: str

    def initial_messages(self, task: dict) -> list[dict]: ...

    def next_turn(self, *, task: dict, messages: list[dict], temperature: float) -> StudentTurn: ...

    def observation_message(self, *, turn: StudentTurn, output: str, returncode: int) -> dict: ...

    def verification_feedback(self, *, output: str) -> dict: ...

    def propose_localization(self, *, task: dict, temperature: float) -> LocalizationProposal: ...

    def propose_patch_plan(self, *, task: dict, localization: dict, temperature: float) -> PatchPlanProposal: ...

    def realize_patch_action(self, *, task: dict, context: dict, temperature: float) -> StudentTurn: ...


class _OpenAICompatSession:
    def __init__(
        self,
        *,
        endpoint: str,
        model: str,
        api_key: str = "",
        tools: list[dict] | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.tools = tools or []
        self.max_tokens = max_tokens
        self.json_mode = json_mode

    def complete(self, *, messages: list[dict], temperature: float) -> dict:
        body: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if self.max_tokens is not None:
            body["max_tokens"] = self.max_tokens
        if self.json_mode:
            body["response_format"] = {"type": "json_object"}
        if self.tools:
            body["tools"] = self.tools
            body["tool_choice"] = "auto"
        req = Request(
            f"{self.endpoint}/chat/completions",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}),
            },
            method="POST",
        )
        for attempt in range(OPENAI_COMPAT_MAX_RETRIES):
            try:
                with urlopen(req, timeout=OPENAI_COMPAT_TIMEOUT_SECONDS) as resp:
                    payload = json.loads(resp.read())
                return payload["choices"][0]["message"]
            except HTTPError as exc:
                if exc.code not in RETRYABLE_STATUS_CODES or attempt == OPENAI_COMPAT_MAX_RETRIES - 1:
                    raise
            except (TimeoutError, URLError):
                if attempt == OPENAI_COMPAT_MAX_RETRIES - 1:
                    raise
            time.sleep(min(2**attempt, 8))
        raise RuntimeError("unreachable")


def _json_payload(raw_content: str) -> dict:
    try:
        parsed = json.loads(raw_content)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_content, re.DOTALL)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}


def _extract_tool_call_json(raw_content: str) -> str:
    marker = raw_content.find("<tool_call>")
    if marker == -1:
        return ""
    payload = raw_content[marker + len("<tool_call>") :].strip()
    start = payload.find("{")
    if start == -1:
        return ""
    payload = payload[start:]
    depth = 0
    in_string = False
    escaped = False
    for index, ch in enumerate(payload):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                return payload[: index + 1]
    return ""


def _extract_shell_command_from_tool_call_content(raw_content: str) -> tuple[str, list[dict]]:
    json_payload = _extract_tool_call_json(raw_content)
    if not json_payload:
        return "", []
    try:
        parsed = json.loads(json_payload)
    except json.JSONDecodeError:
        return "", []
    if not isinstance(parsed, dict) or parsed.get("name") != "shell":
        return "", []
    arguments = parsed.get("arguments", {})
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            arguments = {"command": arguments}
    raw_command = arguments.get("command", "")
    if isinstance(raw_command, list):
        if len(raw_command) >= 3 and raw_command[0] == "bash" and raw_command[1] == "-lc":
            command = raw_command[2]
        else:
            command = " ".join(str(part) for part in raw_command)
    else:
        command = str(raw_command)
    if not command.strip():
        return "", []
    tool_call = {
        "id": "content_tool_call_1",
        "function": {
            "name": "shell",
            "arguments": arguments,
        },
    }
    return command, [tool_call]


def _probe_content(client: _OpenAICompatSession, *, prompt: str, expect_json: bool = False) -> tuple[bool, str]:
    try:
        content = client.complete(messages=[{"role": "user", "content": prompt}], temperature=0.0).get("content", "") or ""
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    if expect_json:
        payload = _json_payload(content)
        if not payload:
            return False, "empty or invalid JSON probe response"
        return True, "ok"
    if not content.strip():
        return False, "empty probe response"
    return True, "ok"


def _normalize_patch_action_payload(payload: dict, raw: str) -> PatchActionProposal:
    def _infer_edit_type(value: str, *, position: str = "") -> str:
        op = str(value or "").strip().lower()
        if op in {"replace", "edit", "modify", "add"}:
            return "replace"
        if op == "insert":
            pos = str(position or "").strip().lower()
            if pos == "before":
                return "insert_before"
            if pos == "after":
                return "insert_after"
            return "replace"
        if op in {"insert_before", "insert_after", "delete"}:
            return op
        return "replace"

    def _coerce_text(value) -> str:
        if isinstance(value, list):
            return "\n".join(str(item) for item in value)
        return str(value or "")

    def _flatten_nested_patch(value) -> dict:
        if isinstance(value, str):
            target_file = ""
            start_line = 0
            for line in value.splitlines():
                if line.startswith("*** Update File: "):
                    target_file = line.removeprefix("*** Update File: ").strip()
                    continue
                if line.startswith("@@"):
                    match = re.search(r"\+(\d+)", line)
                    if match:
                        start_line = int(match.group(1))
                        break
            added_lines = [line[1:] for line in value.splitlines() if line.startswith("+") and not line.startswith("+++")]
            removed_lines = [line[1:] for line in value.splitlines() if line.startswith("-") and not line.startswith("---")]
            if target_file and (added_lines or removed_lines):
                replacement = "\n".join(added_lines)
                return {
                    "file_id": "",
                    "span_id": "",
                    "target_file": target_file,
                    "start_line": start_line,
                    "end_line": start_line,
                    "edit_type": "replace",
                    "replacement": replacement,
                    "submit": False,
                }
            return {}
        if isinstance(value, list):
            first = next((item for item in value if isinstance(item, dict)), {})
            op = str(first.get("op", first.get("action", "")) or "")
            return {
                "file_id": first.get("file_id", ""),
                "span_id": first.get("span_id", ""),
                "target_file": first.get("target_file", first.get("file", first.get("path", ""))),
                "start_line": first.get("start_line", first.get("insert_after_line", 0)),
                "end_line": first.get("end_line", first.get("insert_after_line", 0)),
                "edit_type": _infer_edit_type(op, position=str(first.get("position", "") or "")),
                "replacement": _coerce_text(first.get("replacement", first.get("content", first.get("insert_lines", first.get("to", ""))))),
                "submit": first.get("submit", False),
            }
        if not isinstance(value, dict):
            return {}
        if isinstance(value.get("actions"), list) and value["actions"]:
            first = next((item for item in value["actions"] if isinstance(item, dict)), {})
            op = str(first.get("action", first.get("op", "")) or "")
            return {
                "file_id": first.get("file_id", value.get("file_id", "")),
                "span_id": first.get("span_id", value.get("span_id", "")),
                "target_file": first.get("target_file", first.get("path", value.get("file", value.get("path", "")))),
                "start_line": first.get("start_line", 0),
                "end_line": first.get("end_line", 0),
                "edit_type": _infer_edit_type(op, position=str(first.get("position", "") or "")),
                "replacement": _coerce_text(first.get("replacement", first.get("content", first.get("after", first.get("to", ""))))),
                "submit": first.get("submit", value.get("submit", False)),
            }
        if isinstance(value.get("edits"), list) and value["edits"]:
            first = next((item for item in value["edits"] if isinstance(item, dict)), {})
            op = str(first.get("op", first.get("action", "")) or "")
            return {
                "file_id": first.get("file_id", value.get("file_id", "")),
                "span_id": first.get("span_id", value.get("span_id", "")),
                "target_file": first.get("target_file", first.get("file", first.get("path", value.get("file", value.get("path", ""))))),
                "start_line": first.get("start_line", 0),
                "end_line": first.get("end_line", 0),
                "edit_type": _infer_edit_type(op, position=str(first.get("position", "") or "")),
                "replacement": _coerce_text(first.get("replacement", first.get("content", first.get("after", first.get("to", ""))))),
                "submit": first.get("submit", value.get("submit", False)),
            }
        if isinstance(value.get("hunks"), list) and value["hunks"]:
            first = next((item for item in value["hunks"] if isinstance(item, dict)), {})
            start_line = first.get("start_line", 0)
            return {
                "file_id": value.get("file_id", ""),
                "span_id": value.get("span_id", ""),
                "target_file": value.get("target_file", value.get("file", value.get("path", ""))),
                "start_line": start_line,
                "end_line": first.get("end_line", start_line),
                "edit_type": "replace",
                "replacement": _coerce_text(first.get("replacement", first.get("content", first.get("lines", "")))),
                "submit": value.get("submit", False),
            }
        op = str(value.get("op", value.get("action", "")) or "")
        return {
            "file_id": value.get("file_id", ""),
            "span_id": value.get("span_id", ""),
            "target_file": value.get("target_file", value.get("file", value.get("path", ""))),
            "start_line": value.get("start_line", 0),
            "end_line": value.get("end_line", 0),
            "edit_type": _infer_edit_type(op, position=str(value.get("position", "") or "")),
            "replacement": _coerce_text(value.get("replacement", value.get("content", value.get("after", value.get("to", ""))))),
            "submit": value.get("submit", False),
        }

    nested_patch = payload.get("patch")
    normalized_nested = _flatten_nested_patch(nested_patch)
    if normalized_nested:
        payload = {
            **normalized_nested,
            **payload,
            "file_id": payload.get("file_id", normalized_nested.get("file_id", "")),
            "span_id": payload.get("span_id", normalized_nested.get("span_id", "")),
            "target_file": payload.get("target_file", normalized_nested.get("target_file", "")),
            "start_line": payload.get("start_line", normalized_nested.get("start_line", 0)),
            "end_line": payload.get("end_line", normalized_nested.get("end_line", 0)),
            "replacement": payload.get("replacement", normalized_nested.get("replacement", "")),
            "edit_type": payload.get("edit_type", normalized_nested.get("edit_type", "replace")),
            "submit": payload.get("submit", normalized_nested.get("submit", False)),
        }
    patch_type = str(payload.get("patch_type", "") or "").strip()
    if not payload.get("edit_type") and patch_type in {"edit_lines", "edit"}:
        payload = {
            **payload,
            "edit_type": "replace",
            "target_file": payload.get("target_file", payload.get("file", payload.get("path", ""))),
            "replacement": payload.get(
                "replacement",
                _coerce_text(payload.get("insert_lines", payload.get("after", payload.get("to", payload.get("content", ""))))),
            ),
        }
    file_id = str(payload.get("file_id", "") or "").strip()
    span_id = str(payload.get("span_id", "") or "").strip()
    target_file = str(payload.get("target_file", "") or "").strip()
    edit_type = str(payload.get("edit_type", "no_action") or "no_action").strip()
    replacement = _normalize_replacement_text(_decode_common_replacement_escapes(str(payload.get("replacement", "") or "")))
    rationale = str(payload.get("rationale", "") or raw).strip()
    submit = bool(payload.get("submit", False))
    try:
        start_line = int(payload.get("start_line", 0) or 0)
    except (TypeError, ValueError):
        start_line = 0
    try:
        end_line = int(payload.get("end_line", 0) or 0)
    except (TypeError, ValueError):
        end_line = 0
    return PatchActionProposal(
        file_id=file_id,
        span_id=span_id,
        target_file=target_file,
        start_line=start_line,
        end_line=end_line,
        edit_type=edit_type,
        replacement=replacement,
        submit=submit,
        rationale=rationale,
        raw_response=raw,
    )


def normalize_patch_action_dict(payload: dict, raw: str = "") -> dict:
    action = _normalize_patch_action_payload(dict(payload), raw)
    return {
        "file_id": action.file_id,
        "span_id": action.span_id,
        "target_file": action.target_file,
        "start_line": action.start_line,
        "end_line": action.end_line,
        "edit_type": action.edit_type,
        "replacement": action.replacement,
        "submit": action.submit,
        "rationale": action.rationale,
    }


def _normalize_replacement_text(text: str) -> str:
    if not text:
        return ""
    lines = text.splitlines()
    nonempty = [line for line in lines if line.strip()]
    prefixed = sum(1 for line in nonempty if LINE_NUMBER_PREFIX_RE.match(line))
    if not nonempty or prefixed < max(1, len(nonempty) // 2):
        return text
    stripped = [LINE_NUMBER_PREFIX_RE.sub("", line, count=1) for line in lines]
    normalized = "\n".join(stripped)
    if text.endswith("\n"):
        normalized += "\n"
    return normalized


def _decode_common_replacement_escapes(text: str) -> str:
    if not text or "\n" in text:
        return text
    if not any(token in text for token in ("\\n", "\\t", "\\r")):
        return text
    try:
        return bytes(text, "utf-8").decode("unicode_escape")
    except UnicodeDecodeError:
        return text


def _patch_action_candidates_from_context(context: dict) -> tuple[str, ...]:
    candidates: list[str] = []
    for section in (
        context.get("selected_patch_plan", {}).get("target_files", []),
        context.get("selected_localization", {}).get("candidate_files", []),
        list((context.get("file_contexts") or {}).keys()),
        context.get("changed_files", []),
    ):
        for path in section:
            candidate = str(path or "").strip()
            if candidate and candidate not in candidates:
                candidates.append(candidate)
    return tuple(candidates)


def _target_file_from_span_catalog(context: dict, file_id: str) -> str:
    target = str(file_id or "").strip()
    if not target:
        return ""
    for entry in context.get("span_catalog", []) or []:
        if str(entry.get("file_id", "") or "").strip() == target:
            return str(entry.get("path", "") or "").strip()
    return ""


def _coerce_branch_proposals(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    proposals: list[dict] = []
    for item in value:
        if isinstance(item, dict):
            proposals.append(dict(item))
    return proposals[:2]


def _judge_decision_from_payload(payload: dict, raw: str) -> TeacherJudgeDecisionTurn:
    try:
        score = float(payload.get("score", 0.0) or 0.0)
    except (TypeError, ValueError):
        score = 0.0
    try:
        failure_risk = float(payload.get("failure_risk", 0.0) or 0.0)
    except (TypeError, ValueError):
        failure_risk = 0.0
    return TeacherJudgeDecisionTurn(
        score=max(0.0, min(1.0, score)),
        decision=str(payload.get("decision", "") or "").strip(),
        stop_reason=str(payload.get("stop_reason", "") or "").strip(),
        failure_risk=max(0.0, min(1.0, failure_risk)),
        branch_proposals=_coerce_branch_proposals(payload.get("branch_proposals")),
        raw_response=raw,
    )


def _teacher_state_summary_from_payload(payload: dict, raw: str) -> TeacherStateSummaryTurn:
    def _float_value(key: str) -> float:
        try:
            return max(0.0, min(1.0, float(payload.get(key, 0.0) or 0.0)))
        except (TypeError, ValueError):
            return 0.0

    return TeacherStateSummaryTurn(
        root_cause_guess=str(payload.get("root_cause_guess", "") or "").strip(),
        target_file_ids=_ensure_tuple(payload.get("target_file_ids")),
        target_span_ids=_ensure_tuple(payload.get("target_span_ids")),
        minimal_edit_direction=str(payload.get("minimal_edit_direction", "") or "").strip(),
        prior_score=_float_value("prior_score"),
        value_score=_float_value("value_score"),
        submit_likelihood=_float_value("submit_likelihood"),
        dead_end_risk=_float_value("dead_end_risk"),
        branch_proposals=_coerce_branch_proposals(payload.get("branch_proposals")),
        raw_response=raw,
    )


def _single_span_from_context(context: dict) -> dict | None:
    catalog = context.get("span_catalog", []) or []
    if len(catalog) != 1:
        return None
    spans = catalog[0].get("spans", []) or []
    if len(spans) != 1:
        return None
    return {
        "file_id": str(catalog[0].get("file_id", "") or ""),
        "span_id": str(spans[0].get("span_id", "") or ""),
        "target_file": str(catalog[0].get("path", "") or ""),
        "start_line": int(spans[0].get("start_line", 0) or 0),
        "end_line": int(spans[0].get("end_line", 0) or 0),
    }


def _classify_miniswe_action(content: str, command: str) -> str:
    if command.strip():
        return "ok"
    if "```bash" in content:
        return "truncated_action" if content.count("```") == 1 else "parse_fail"
    return "no_action"


def _classify_codex_action(content: str, command: str, tool_calls: list[dict]) -> str:
    if command.strip():
        return "ok"
    if tool_calls:
        return "parse_fail"
    if "<tool_call>" in content:
        return "truncated_action" if _extract_tool_call_json(content) == "" else "parse_fail"
    return "no_action"


def _ensure_tuple(value) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(item.strip() for item in value.split(",") if item.strip())
    if isinstance(value, list):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _student_env_key(fmt: str, suffix: str) -> str:
    return f"ORBIT_SWE_{fmt.upper()}_STUDENT_{suffix}"


def resolve_student_endpoint(fmt: str, endpoint: str = "") -> str:
    return endpoint or os.environ.get(_student_env_key(fmt, "ENDPOINT"), "") or os.environ.get("OPENAI_BASE_URL", "")


def resolve_student_model(fmt: str, model: str = "") -> str:
    return (
        model
        or os.environ.get(_student_env_key(fmt, "MODEL"), "")
        or os.environ.get("ORBIT_SWE_STUDENT_MODEL", "")
        or os.environ.get("ORBIT_SWE_TEACHER_MODEL", "")
        or "gpt-4o-mini"
    )


def resolve_student_api_key(fmt: str, api_key: str = "") -> str:
    return (
        api_key
        or os.environ.get(_student_env_key(fmt, "API_KEY"), "")
        or os.environ.get("CHUTES_API_KEY", "")
        or os.environ.get("OPENAI_API_KEY", "")
    )


def resolve_teacher_endpoint(endpoint: str = "") -> str:
    return endpoint or os.environ.get("ORBIT_SWE_TEACHER_ENDPOINT", "") or os.environ.get("OPENAI_BASE_URL", "")


def resolve_teacher_model(model: str = "") -> str:
    return model or os.environ.get("ORBIT_SWE_TEACHER_MODEL", "") or "gpt-4o-mini"


def resolve_teacher_api_key(api_key: str = "") -> str:
    return api_key or os.environ.get("ORBIT_SWE_TEACHER_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")


class MiniSweStudentSession:
    format = "miniswe"

    def __init__(self, *, endpoint: str = "", model: str = "", api_key: str = "", client: _OpenAICompatSession | None = None):
        self.endpoint = resolve_student_endpoint(self.format, endpoint)
        self.model = resolve_student_model(self.format, model)
        self.api_key = resolve_student_api_key(self.format, api_key)
        self.client = client or _OpenAICompatSession(
            endpoint=self.endpoint,
            model=self.model,
            api_key=self.api_key,
            max_tokens=REALIZATION_MAX_TOKENS,
        )
        self.analysis_client = _OpenAICompatSession(
            endpoint=self.endpoint,
            model=self.model,
            api_key=self.api_key,
            max_tokens=220,
            json_mode=True,
        )
        self.realization_client = _OpenAICompatSession(
            endpoint=self.endpoint,
            model=self.model,
            api_key=self.api_key,
            max_tokens=900,
            json_mode=True,
        )

    def initial_messages(self, task: dict) -> list[dict]:
        return [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant that can interact with a shell to solve a programming task. "
                    "Respond with THOUGHT followed by exactly one bash code block. "
                    "Keep THOUGHT under 20 words, do not emit <think> tags, and use COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT only when you want the environment to run tests. "
                    "Prefer short, local shell edits. Avoid rewriting whole files with here-docs unless the file is tiny. "
                    "The interaction budget is small, so do not spend all turns only inspecting."
                ),
            },
            {
                "role": "user",
                "content": task.get("problem_statement", ""),
            },
        ]

    def next_turn(self, *, task: dict, messages: list[dict], temperature: float) -> StudentTurn:
        message = self.client.complete(messages=messages, temperature=temperature)
        content = message.get("content", "") or ""
        match = ACTION_RE.search(content)
        command = match.group(1).strip() if match else ""
        return StudentTurn(
            assistant_message={"role": "assistant", "content": content},
            command=command,
            submit=SUBMIT_MARKER in content,
            action_state=_classify_miniswe_action(content, command),
        )

    def probe(self) -> tuple[bool, str]:
        return _probe_content(self.analysis_client, prompt='Return raw JSON only: {"ok": true}', expect_json=True)

    def observation_message(self, *, turn: StudentTurn, output: str, returncode: int) -> dict:
        return {
            "role": "user",
            "content": f"<returncode>{returncode}</returncode><output>{output}</output>",
        }

    def verification_feedback(self, *, output: str) -> dict:
        return {
            "role": "user",
            "content": f"Tests still failing.\n{output}",
        }

    def propose_localization(self, *, task: dict, temperature: float) -> LocalizationProposal:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are doing the localization stage for a SWE task. "
                    "Do not write or run a patch. Return raw JSON only with keys candidate_files, candidate_symbols, hypothesis, edit_type."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "problem_statement": task.get("problem_statement", ""),
                        "repo": task.get("repo", ""),
                        "language": task.get("repo_language", ""),
                        "test_command": task.get("test_command", ""),
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        raw = self.analysis_client.complete(messages=messages, temperature=temperature).get("content", "") or ""
        payload = _json_payload(raw)
        return LocalizationProposal(
            candidate_files=_ensure_tuple(payload.get("candidate_files")),
            candidate_symbols=_ensure_tuple(payload.get("candidate_symbols")),
            hypothesis=str(payload.get("hypothesis", raw)).strip(),
            edit_type=str(payload.get("edit_type", "unknown")).strip() or "unknown",
            raw_response=raw,
        )

    def propose_patch_plan(self, *, task: dict, localization: dict, temperature: float) -> PatchPlanProposal:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are doing the patch-planning stage for a SWE task. "
                    "Do not write the final patch yet. Return raw JSON only with keys target_files, target_symbols, diff_sketch, plan_steps, edit_type."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "problem_statement": task.get("problem_statement", ""),
                        "repo": task.get("repo", ""),
                        "language": task.get("repo_language", ""),
                        "localization": localization,
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        raw = self.analysis_client.complete(messages=messages, temperature=temperature).get("content", "") or ""
        payload = _json_payload(raw)
        plan_steps = payload.get("plan_steps")
        if isinstance(plan_steps, str):
            plan_steps = [line.strip("-* ").strip() for line in plan_steps.splitlines() if line.strip()]
        target_files = _ensure_tuple(payload.get("target_files")) or _ensure_tuple(localization.get("candidate_files"))
        target_symbols = _ensure_tuple(payload.get("target_symbols")) or _ensure_tuple(localization.get("candidate_symbols"))
        edit_type = str(payload.get("edit_type", localization.get("edit_type", "unknown"))).strip() or str(localization.get("edit_type", "unknown")).strip() or "unknown"
        return PatchPlanProposal(
            target_files=target_files,
            target_symbols=target_symbols,
            diff_sketch=str(payload.get("diff_sketch", raw)).strip(),
            plan_steps=_ensure_tuple(plan_steps),
            edit_type=edit_type,
            raw_response=raw,
        )

    def realize_patch_action(self, *, task: dict, context: dict, temperature: float) -> StudentTurn:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are in patch realization mode for a SWE task. "
                    "Do not inspect the repository with shell commands. Use the provided code context only. "
                    "Return raw JSON only with keys file_id, span_id, edit_type, replacement, submit, rationale. "
                    "Allowed edit_type values: replace, insert_before, insert_after, delete, no_action. "
                    "Prefer a minimal local edit. Do not rewrite a whole file unless the file is tiny. "
                    "Line prefixes like 0042: in the context are metadata only; never copy them into replacement. "
                    "You must select file_id/span_id from the provided span catalog instead of inventing file paths or line numbers. "
                    "If there is already a diff, revise it rather than restarting. "
                    "If the remaining step budget is small, emit an edit now instead of more analysis."
                ),
            },
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ]
        raw = self.realization_client.complete(messages=messages, temperature=temperature).get("content", "") or ""
        payload = _json_payload(raw)
        action = _normalize_patch_action_payload(payload, raw)
        fallback_span = _single_span_from_context(context)
        if fallback_span and not action.file_id and not action.span_id and not action.target_file:
            action = PatchActionProposal(
                file_id=fallback_span["file_id"],
                span_id=fallback_span["span_id"],
                target_file=fallback_span["target_file"],
                start_line=fallback_span["start_line"],
                end_line=fallback_span["end_line"],
                edit_type=action.edit_type,
                replacement=action.replacement,
                submit=action.submit,
                rationale=action.rationale,
                raw_response=action.raw_response,
            )
        if action.file_id and not action.target_file:
            mapped_target = _target_file_from_span_catalog(context, action.file_id)
            if mapped_target:
                action = PatchActionProposal(
                    file_id=action.file_id,
                    span_id=action.span_id,
                    target_file=mapped_target,
                    start_line=action.start_line,
                    end_line=action.end_line,
                    edit_type=action.edit_type,
                    replacement=action.replacement,
                    submit=action.submit,
                    rationale=action.rationale,
                    raw_response=action.raw_response,
                )
        if not action.target_file:
            candidates = _patch_action_candidates_from_context(context)
            if len(candidates) == 1:
                action = PatchActionProposal(
                    file_id=action.file_id,
                    span_id=action.span_id,
                    target_file=candidates[0],
                    start_line=action.start_line,
                    end_line=action.end_line,
                    edit_type=action.edit_type,
                    replacement=action.replacement,
                    submit=action.submit,
                    rationale=action.rationale,
                    raw_response=action.raw_response,
                )
        action_dict = {
            "file_id": action.file_id,
            "span_id": action.span_id,
            "target_file": action.target_file,
            "start_line": action.start_line,
            "end_line": action.end_line,
            "edit_type": action.edit_type,
            "replacement": action.replacement,
            "submit": action.submit,
            "rationale": action.rationale,
        }
        content = "PATCH_ACTION\n```json\n" + json.dumps(action_dict, ensure_ascii=False, indent=2) + "\n```"
        action_state = "ok"
        if action.edit_type == "no_action":
            action_state = "no_action"
        elif not (action.file_id and action.span_id) and not action.target_file:
            action_state = "parse_fail"
        elif action.start_line < 0 or action.end_line < 0:
            action_state = "parse_fail"
        return StudentTurn(
            assistant_message={"role": "assistant", "content": content},
            submit=action.submit,
            action_state=action_state,
            tool_name="apply_patch_action",
            action=action_dict,
        )


class CodexStudentSession:
    format = "codex"

    def __init__(self, *, endpoint: str = "", model: str = "", api_key: str = "", client: _OpenAICompatSession | None = None):
        self.endpoint = resolve_student_endpoint(self.format, endpoint)
        self.model = resolve_student_model(self.format, model)
        self.api_key = resolve_student_api_key(self.format, api_key)
        self.tools = load_tools("swe")
        self.client = client or _OpenAICompatSession(
            endpoint=self.endpoint,
            model=self.model,
            api_key=self.api_key,
            tools=self.tools,
            max_tokens=REALIZATION_MAX_TOKENS,
        )
        self.analysis_client = _OpenAICompatSession(
            endpoint=self.endpoint,
            model=self.model,
            api_key=self.api_key,
            max_tokens=220,
            json_mode=True,
        )
        self.realization_client = _OpenAICompatSession(
            endpoint=self.endpoint,
            model=self.model,
            api_key=self.api_key,
            max_tokens=900,
            json_mode=True,
        )

    def initial_messages(self, task: dict) -> list[dict]:
        return [
            {
                "role": "system",
                "content": (
                    "You are a coding agent operating in an isolated repository workspace. "
                    "Use the shell tool to inspect and modify /app until the bug is fixed. "
                    "Use COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT in assistant text only when you want tests to run. "
                    "Prefer short, local shell commands and incremental edits; avoid whole-file rewrites unless the file is tiny. "
                    "The interaction budget is small, so do not spend all turns only inspecting."
                ),
            },
            {
                "role": "user",
                "content": task.get("problem_statement", ""),
            },
        ]

    def next_turn(self, *, task: dict, messages: list[dict], temperature: float) -> StudentTurn:
        message = self.client.complete(messages=messages, temperature=temperature)
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            reminder_messages = [
                *messages,
                {"role": "assistant", "content": message.get("content", "") or ""},
                {"role": "user", "content": "You must respond with exactly one shell tool call now. Do not answer in plain text."},
            ]
            retried = self.client.complete(messages=reminder_messages, temperature=temperature)
            if retried.get("tool_calls"):
                message = retried
                tool_calls = message.get("tool_calls") or []
        command = ""
        for tool_call in tool_calls:
            fn = tool_call.get("function", {})
            if fn.get("name") != "shell":
                continue
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"command": args}
            raw_command = args.get("command", "")
            if isinstance(raw_command, list):
                if len(raw_command) >= 3 and raw_command[0] == "bash" and raw_command[1] == "-lc":
                    command = raw_command[2]
                else:
                    command = " ".join(str(part) for part in raw_command)
            else:
                command = str(raw_command)
            break
        content = message.get("content", "") or ""
        if not command.strip():
            command, content_tool_calls = _extract_shell_command_from_tool_call_content(content)
            if content_tool_calls:
                tool_calls = content_tool_calls
        return StudentTurn(
            assistant_message={"role": "assistant", "content": content, "tool_calls": tool_calls},
            command=command,
            submit=SUBMIT_MARKER in content,
            action_state=_classify_codex_action(content, command, tool_calls),
        )

    def probe(self) -> tuple[bool, str]:
        return _probe_content(self.analysis_client, prompt='Return raw JSON only: {"ok": true}', expect_json=True)

    def observation_message(self, *, turn: StudentTurn, output: str, returncode: int) -> dict:
        tool_call_id = ""
        tool_calls = turn.assistant_message.get("tool_calls") or []
        if tool_calls:
            tool_call_id = tool_calls[0].get("id", "")
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": json.dumps(
                {
                    "output": output,
                    "metadata": {
                        "exit_code": returncode,
                        "duration_seconds": 0.0,
                    },
                },
                ensure_ascii=False,
            ),
        }

    def verification_feedback(self, *, output: str) -> dict:
        return {"role": "user", "content": f"Tests still failing.\n{output}"}

    def propose_localization(self, *, task: dict, temperature: float) -> LocalizationProposal:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are doing the localization stage for a SWE task. "
                    "Return JSON with keys candidate_files, candidate_symbols, hypothesis, edit_type. "
                    "Return raw JSON only and do not emit tool calls."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "problem_statement": task.get("problem_statement", ""),
                        "repo": task.get("repo", ""),
                        "language": task.get("repo_language", ""),
                        "test_command": task.get("test_command", ""),
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        raw = self.analysis_client.complete(messages=messages, temperature=temperature).get("content", "") or ""
        payload = _json_payload(raw)
        return LocalizationProposal(
            candidate_files=_ensure_tuple(payload.get("candidate_files")),
            candidate_symbols=_ensure_tuple(payload.get("candidate_symbols")),
            hypothesis=str(payload.get("hypothesis", raw)).strip(),
            edit_type=str(payload.get("edit_type", "unknown")).strip() or "unknown",
            raw_response=raw,
        )

    def propose_patch_plan(self, *, task: dict, localization: dict, temperature: float) -> PatchPlanProposal:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are doing the patch-planning stage for a SWE task. "
                    "Return JSON with keys target_files, target_symbols, diff_sketch, plan_steps, edit_type. "
                    "Return raw JSON only and do not emit tool calls."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "problem_statement": task.get("problem_statement", ""),
                        "repo": task.get("repo", ""),
                        "language": task.get("repo_language", ""),
                        "localization": localization,
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        raw = self.analysis_client.complete(messages=messages, temperature=temperature).get("content", "") or ""
        payload = _json_payload(raw)
        plan_steps = payload.get("plan_steps")
        if isinstance(plan_steps, str):
            plan_steps = [line.strip("-* ").strip() for line in plan_steps.splitlines() if line.strip()]
        target_files = _ensure_tuple(payload.get("target_files")) or _ensure_tuple(localization.get("candidate_files"))
        target_symbols = _ensure_tuple(payload.get("target_symbols")) or _ensure_tuple(localization.get("candidate_symbols"))
        edit_type = str(payload.get("edit_type", localization.get("edit_type", "unknown"))).strip() or str(localization.get("edit_type", "unknown")).strip() or "unknown"
        return PatchPlanProposal(
            target_files=target_files,
            target_symbols=target_symbols,
            diff_sketch=str(payload.get("diff_sketch", raw)).strip(),
            plan_steps=_ensure_tuple(plan_steps),
            edit_type=edit_type,
            raw_response=raw,
        )

    def realize_patch_action(self, *, task: dict, context: dict, temperature: float) -> StudentTurn:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are in patch realization mode for a SWE task. "
                    "Do not inspect the repository with shell commands. Use the provided code context only. "
                    "Return raw JSON only with keys file_id, span_id, edit_type, replacement, submit, rationale. "
                    "Allowed edit_type values: replace, insert_before, insert_after, delete, no_action. "
                    "Prefer a minimal local edit. Do not rewrite a whole file unless the file is tiny. "
                    "Line prefixes like 0042: in the context are metadata only; never copy them into replacement. "
                    "You must select file_id/span_id from the provided span catalog instead of inventing file paths or line numbers. "
                    "If there is already a diff, revise it rather than restarting. "
                    "If the remaining step budget is small, emit an edit now instead of more analysis."
                ),
            },
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ]
        raw = self.realization_client.complete(messages=messages, temperature=temperature).get("content", "") or ""
        payload = _json_payload(raw)
        action = _normalize_patch_action_payload(payload, raw)
        fallback_span = _single_span_from_context(context)
        if fallback_span and not action.file_id and not action.span_id and not action.target_file:
            action = PatchActionProposal(
                file_id=fallback_span["file_id"],
                span_id=fallback_span["span_id"],
                target_file=fallback_span["target_file"],
                start_line=fallback_span["start_line"],
                end_line=fallback_span["end_line"],
                edit_type=action.edit_type,
                replacement=action.replacement,
                submit=action.submit,
                rationale=action.rationale,
                raw_response=action.raw_response,
            )
        if action.file_id and not action.target_file:
            mapped_target = _target_file_from_span_catalog(context, action.file_id)
            if mapped_target:
                action = PatchActionProposal(
                    file_id=action.file_id,
                    span_id=action.span_id,
                    target_file=mapped_target,
                    start_line=action.start_line,
                    end_line=action.end_line,
                    edit_type=action.edit_type,
                    replacement=action.replacement,
                    submit=action.submit,
                    rationale=action.rationale,
                    raw_response=action.raw_response,
                )
        if not action.target_file:
            candidates = _patch_action_candidates_from_context(context)
            if len(candidates) == 1:
                action = PatchActionProposal(
                    file_id=action.file_id,
                    span_id=action.span_id,
                    target_file=candidates[0],
                    start_line=action.start_line,
                    end_line=action.end_line,
                    edit_type=action.edit_type,
                    replacement=action.replacement,
                    submit=action.submit,
                    rationale=action.rationale,
                    raw_response=action.raw_response,
                )
        action_dict = {
            "file_id": action.file_id,
            "span_id": action.span_id,
            "target_file": action.target_file,
            "start_line": action.start_line,
            "end_line": action.end_line,
            "edit_type": action.edit_type,
            "replacement": action.replacement,
            "submit": action.submit,
            "rationale": action.rationale,
        }
        action_state = "ok"
        if action.edit_type == "no_action":
            action_state = "no_action"
        elif not (action.file_id and action.span_id) and not action.target_file:
            action_state = "parse_fail"
        elif action.start_line < 0 or action.end_line < 0:
            action_state = "parse_fail"
        return StudentTurn(
            assistant_message={
                "role": "assistant",
                "content": "Applying structured patch action",
                "tool_calls": [
                    {
                        "id": "patch_action_1",
                        "function": {
                            "name": "apply_patch_action",
                            "arguments": action_dict,
                        },
                    }
                ],
            },
            submit=action.submit,
            action_state=action_state,
            tool_name="apply_patch_action",
            action=action_dict,
        )


class TeacherJudgeSession:
    """Online teacher judge that can score, prune, and propose branch candidates."""

    def __init__(self, *, endpoint: str = "", model: str = "", api_key: str = "", client: _OpenAICompatSession | None = None):
        self.endpoint = resolve_teacher_endpoint(endpoint)
        self.model = resolve_teacher_model(model)
        self.api_key = resolve_teacher_api_key(api_key)
        self.client = client or _OpenAICompatSession(
            endpoint=self.endpoint,
            model=self.model,
            api_key=self.api_key,
            max_tokens=420,
            json_mode=True,
        )

    def probe(self) -> tuple[bool, str]:
        return _probe_content(self.client, prompt='Return raw JSON only: {"ok": true}', expect_json=True)

    def build_issue_rubric(self, *, task: dict, oracle: dict, temperature: float = 0.2) -> IssueRubricTurn:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are building a scoring rubric for a SWE issue. "
                    "Do not solve the task and do not write a patch. "
                    "Return raw JSON only with keys likely_modules, required_constraints, common_pseudo_solutions, forbidden_patterns."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "problem_statement": task.get("problem_statement", ""),
                        "repo": task.get("repo", ""),
                        "language": task.get("repo_language", ""),
                        "test_command": task.get("test_command", ""),
                        "hidden_oracle": oracle,
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        raw = self.client.complete(messages=messages, temperature=temperature).get("content", "") or ""
        payload = _json_payload(raw)
        likely_modules = _ensure_tuple(payload.get("likely_modules"))
        if not likely_modules:
            likely_modules = tuple(path for path in oracle.get("touched_files", []) if path and path in raw)
        return IssueRubricTurn(
            likely_modules=likely_modules,
            required_constraints=_ensure_tuple(payload.get("required_constraints")),
            common_pseudo_solutions=_ensure_tuple(payload.get("common_pseudo_solutions")),
            forbidden_patterns=_ensure_tuple(payload.get("forbidden_patterns")),
            raw_response=raw,
        )

    def judge_localization(self, *, task: dict, oracle: dict, rubric: dict | None, candidate: dict, frontier_summary: dict, temperature: float = 0.2) -> TeacherJudgeDecisionTurn:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an online SWE localization judge. "
                    "Score the candidate and decide accept or drop. "
                    "You may propose up to 2 alternative localization candidates. "
                    "Return raw JSON only with keys score, decision, failure_risk, stop_reason, branch_proposals."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": {
                            "problem_statement": task.get("problem_statement", ""),
                            "repo": task.get("repo", ""),
                            "language": task.get("repo_language", ""),
                        },
                        "oracle": oracle,
                        "rubric": rubric or {},
                        "candidate": candidate,
                        "frontier_summary": frontier_summary,
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        raw = self.client.complete(messages=messages, temperature=temperature).get("content", "") or ""
        return _judge_decision_from_payload(_json_payload(raw), raw)

    def judge_plan(self, *, task: dict, oracle: dict, rubric: dict | None, localization: dict, plan: dict, frontier_summary: dict, temperature: float = 0.2) -> TeacherJudgeDecisionTurn:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an online SWE patch-plan judge. "
                    "Score the plan and decide accept or drop. "
                    "You may propose up to 2 alternative patch plans. "
                    "Return raw JSON only with keys score, decision, failure_risk, stop_reason, branch_proposals."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": {
                            "problem_statement": task.get("problem_statement", ""),
                            "repo": task.get("repo", ""),
                            "language": task.get("repo_language", ""),
                        },
                        "oracle": oracle,
                        "rubric": rubric or {},
                        "localization": localization,
                        "plan": plan,
                        "frontier_summary": frontier_summary,
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        raw = self.client.complete(messages=messages, temperature=temperature).get("content", "") or ""
        return _judge_decision_from_payload(_json_payload(raw), raw)

    def judge_realization_step(
        self,
        *,
        task: dict,
        oracle: dict,
        rubric: dict | None,
        branch_state: dict,
        last_action: dict,
        runtime_feedback: dict,
        temperature: float = 0.2,
    ) -> TeacherJudgeDecisionTurn:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an online SWE realization judge. "
                    "Decide whether to continue_current, submit_now, or stop_current. "
                    "You may propose up to 2 alternative next patch actions using the same file_id/span_id schema. "
                    "Return raw JSON only with keys score, decision, failure_risk, stop_reason, branch_proposals."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": {
                            "problem_statement": task.get("problem_statement", ""),
                            "repo": task.get("repo", ""),
                            "language": task.get("repo_language", ""),
                        },
                        "oracle": oracle,
                        "rubric": rubric or {},
                        "branch_state": branch_state,
                        "last_action": last_action,
                        "runtime_feedback": runtime_feedback,
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        raw = self.client.complete(messages=messages, temperature=temperature).get("content", "") or ""
        return _judge_decision_from_payload(_json_payload(raw), raw)

    def summarize_search_node(
        self,
        *,
        task: dict,
        oracle: dict,
        rubric: dict | None,
        checkpoint: dict,
        span_catalog: list[dict],
        last_feedback: str,
        temperature: float = 0.2,
    ) -> TeacherStateSummaryTurn:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are summarizing a SWE search node for low-cost tree search. "
                    "Do not solve the whole task. "
                    "Return raw JSON only with keys root_cause_guess, target_file_ids, target_span_ids, "
                    "minimal_edit_direction, prior_score, value_score, submit_likelihood, dead_end_risk, branch_proposals. "
                    "branch_proposals must use the same structured patch schema as the student."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": {
                            "problem_statement": task.get("problem_statement", ""),
                            "repo": task.get("repo", ""),
                            "language": task.get("repo_language", ""),
                        },
                        "oracle": oracle,
                        "rubric": rubric or {},
                        "checkpoint": checkpoint,
                        "span_catalog": span_catalog,
                        "last_feedback": last_feedback,
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        raw = self.client.complete(messages=messages, temperature=temperature).get("content", "") or ""
        return _teacher_state_summary_from_payload(_json_payload(raw), raw)


class FailureCritiqueSession:
    """Teacher used only for offline failure-point critique and revision."""

    def __init__(self, *, endpoint: str = "", model: str = "", api_key: str = "", client: _OpenAICompatSession | None = None):
        self.endpoint = resolve_teacher_endpoint(endpoint)
        self.model = resolve_teacher_model(model)
        self.api_key = resolve_teacher_api_key(api_key)
        self.client = client or _OpenAICompatSession(
            endpoint=self.endpoint,
            model=self.model,
            api_key=self.api_key,
            max_tokens=280,
            json_mode=True,
        )

    def build_issue_rubric(self, *, task: dict, oracle: dict, temperature: float = 0.2) -> IssueRubricTurn:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are building a scoring rubric for a SWE issue. "
                    "Do not solve the task and do not write a patch. "
                    "Return raw JSON only with keys likely_modules, required_constraints, common_pseudo_solutions, forbidden_patterns."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "problem_statement": task.get("problem_statement", ""),
                        "repo": task.get("repo", ""),
                        "language": task.get("repo_language", ""),
                        "test_command": task.get("test_command", ""),
                        "hidden_oracle": oracle,
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        raw = self.client.complete(messages=messages, temperature=temperature).get("content", "") or ""
        payload = _json_payload(raw)
        likely_modules = _ensure_tuple(payload.get("likely_modules"))
        if not likely_modules:
            likely_modules = tuple(path for path in oracle.get("touched_files", []) if path and path in raw)
        return IssueRubricTurn(
            likely_modules=likely_modules,
            required_constraints=_ensure_tuple(payload.get("required_constraints")),
            common_pseudo_solutions=_ensure_tuple(payload.get("common_pseudo_solutions")),
            forbidden_patterns=_ensure_tuple(payload.get("forbidden_patterns")),
            raw_response=raw,
        )

    def probe(self) -> tuple[bool, str]:
        return _probe_content(self.client, prompt='Return raw JSON only: {"ok": true}', expect_json=True)

    def critique_failure(
        self,
        *,
        task: dict,
        trajectory: dict,
        failure_point: dict,
        window: list[dict],
        rubric: dict | None = None,
        localization: dict | None = None,
        plan: dict | None = None,
        temperature: float = 0.2,
    ) -> CritiqueTurn:
        summary = {
            "instance_id": trajectory.get("instance_id", ""),
            "base_instance_id": trajectory.get("base_instance_id", ""),
            "format": trajectory.get("format", ""),
            "terminal_status": trajectory.get("terminal_status", ""),
            "verify_passed": trajectory.get("verify_passed", False),
            "changed_files": trajectory.get("changed_files", []),
            "failure_kind": failure_point.get("failure_kind", ""),
            "step_index": failure_point.get("step_index", -1),
            "offline_hints_used": failure_point.get("offline_hints_used", []),
            "problem_statement": task.get("problem_statement", ""),
            "window": window,
            "test_output": trajectory.get("terminal_output", ""),
            "current_diff": trajectory.get("final_patch", ""),
            "rubric": rubric or {},
            "localization": localization or {},
            "plan": plan or {},
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an offline SWE near-miss repair teacher. The student already has a concrete state. "
                    "Do not rewrite the whole solution and do not change the action schema. "
                    "Identify what was wrong at the failure point and provide exactly one revised next shell action. "
                    "Return raw JSON only.\n\n"
                    "Return JSON with keys critique and revised_action."
                ),
            },
            {"role": "user", "content": json.dumps(summary, ensure_ascii=False)},
        ]
        response = self.client.complete(messages=messages, temperature=temperature)
        raw_content = response.get("content", "") or ""
        critique = raw_content.strip()
        revised_action = ""
        try:
            payload = json.loads(raw_content)
            critique = str(payload.get("critique", critique)).strip()
            revised_action = str(payload.get("revised_action", "")).strip()
        except json.JSONDecodeError:
            match = ACTION_RE.search(raw_content)
            if match:
                revised_action = match.group(1).strip()
        if not revised_action and SUBMIT_MARKER in raw_content:
            revised_action = SUBMIT_MARKER
        return CritiqueTurn(critique=critique, revised_action=revised_action, raw_response=raw_content)


__all__ = [
    "CodexStudentSession",
    "CritiqueTurn",
    "FailureCritiqueSession",
    "IssueRubricTurn",
    "LocalizationProposal",
    "MiniSweStudentSession",
    "PatchPlanProposal",
    "TeacherStateSummaryTurn",
    "TeacherJudgeDecisionTurn",
    "TeacherJudgeSession",
    "StudentTurn",
    "SweStudentSession",
    "normalize_patch_action_dict",
    "resolve_student_api_key",
    "resolve_student_endpoint",
    "resolve_student_model",
    "resolve_teacher_api_key",
    "resolve_teacher_endpoint",
    "resolve_teacher_model",
]
