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
SUBMIT_MARKER = "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"
REALIZATION_MAX_TOKENS = 1600
RETRYABLE_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}


@dataclass
class StudentTurn:
    assistant_message: dict
    command: str = ""
    submit: bool = False
    action_state: str = "ok"


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
class IssueRubricTurn:
    likely_modules: tuple[str, ...]
    required_constraints: tuple[str, ...]
    common_pseudo_solutions: tuple[str, ...]
    forbidden_patterns: tuple[str, ...]
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
        for attempt in range(4):
            try:
                with urlopen(req, timeout=300) as resp:
                    payload = json.loads(resp.read())
                return payload["choices"][0]["message"]
            except HTTPError as exc:
                if exc.code not in RETRYABLE_STATUS_CODES or attempt == 3:
                    raise
            except (TimeoutError, URLError):
                if attempt == 3:
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
        return PatchPlanProposal(
            target_files=_ensure_tuple(payload.get("target_files")),
            target_symbols=_ensure_tuple(payload.get("target_symbols")),
            diff_sketch=str(payload.get("diff_sketch", raw)).strip(),
            plan_steps=_ensure_tuple(plan_steps),
            edit_type=str(payload.get("edit_type", "unknown")).strip() or "unknown",
            raw_response=raw,
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
        return PatchPlanProposal(
            target_files=_ensure_tuple(payload.get("target_files")),
            target_symbols=_ensure_tuple(payload.get("target_symbols")),
            diff_sketch=str(payload.get("diff_sketch", raw)).strip(),
            plan_steps=_ensure_tuple(plan_steps),
            edit_type=str(payload.get("edit_type", "unknown")).strip() or "unknown",
            raw_response=raw,
        )


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
        return IssueRubricTurn(
            likely_modules=_ensure_tuple(payload.get("likely_modules")),
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
    "StudentTurn",
    "SweStudentSession",
    "resolve_student_api_key",
    "resolve_student_endpoint",
    "resolve_student_model",
    "resolve_teacher_api_key",
    "resolve_teacher_endpoint",
    "resolve_teacher_model",
]
