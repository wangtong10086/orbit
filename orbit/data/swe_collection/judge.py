"""Terminal verification and offline failure localization for SWE collection."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from orbit.verifiers.base import VerifierResult


def _normalize_expected_tests(value) -> set[str]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return {str(item) for item in parsed}
        except json.JSONDecodeError:
            return {value}
    if isinstance(value, list):
        return {str(item) for item in value}
    return set()


def parse_test_output(stdout: str, returncode: int, language: str, test_command: str) -> tuple[set[str], set[str]]:
    """Approximate SWE eval-aligned test parsing for common runners."""
    text = stdout or ""
    passed: set[str] = set()
    failed: set[str] = set()

    patterns = [
        (re.compile(r"^PASSED\s+(.+)$", re.MULTILINE), passed),
        (re.compile(r"^FAILED\s+(.+)$", re.MULTILINE), failed),
        (re.compile(r"^ok\s+\S+\s+(.+)$", re.MULTILINE), passed),
        (re.compile(r"^--- FAIL: ([^(]+)", re.MULTILINE), failed),
        (re.compile(r"^--- PASS: ([^(]+)", re.MULTILINE), passed),
        (re.compile(r"^\s*(test_[^\s:]+)", re.MULTILINE), passed if returncode == 0 else failed),
    ]
    for pattern, target in patterns:
        for match in pattern.findall(text):
            target.add(str(match).strip())

    if returncode == 0 and not failed and not passed and test_command:
        passed.add(test_command.strip())
    if returncode != 0 and not failed and test_command:
        failed.add(test_command.strip())
    return passed, failed


def extract_ref_files(patch: str) -> set[str]:
    files = set()
    for line in patch.splitlines():
        if line.startswith("+++ b/"):
            files.add(line[6:].strip())
    return files


@dataclass(frozen=True)
class VerificationOutcome:
    verified: bool
    status: str
    output: str
    passed_tests: tuple[str, ...]
    failed_tests: tuple[str, ...]
    changed_files: tuple[str, ...]


class SweTerminalVerifier:
    """Eval-aligned verification and failure-point localization helper."""

    def __init__(self, task: dict):
        self.task = task
        self.ref_files = extract_ref_files(str(task.get("patch", "") or ""))

    def verify(self, *, workspace, task: dict | None = None) -> VerificationOutcome:
        active_task = task or self.task
        test_command = str(active_task.get("test_command", "")).strip()
        changed_files = tuple(workspace.changed_files())
        if not workspace.has_patch():
            return VerificationOutcome(
                verified=False,
                status="no_patch",
                output="no patch produced",
                passed_tests=(),
                failed_tests=(),
                changed_files=changed_files,
            )
        if not test_command:
            return VerificationOutcome(
                verified=True,
                status="success",
                output="missing test_command; accepted patched workspace",
                passed_tests=(),
                failed_tests=(),
                changed_files=changed_files,
            )
        test_result = workspace.exec(f"cd /app && {test_command}", timeout=300)
        passed, failed = parse_test_output(
            test_result.output,
            test_result.returncode,
            str(active_task.get("repo_language", "")),
            test_command,
        )
        fail_to_pass = _normalize_expected_tests(active_task.get("fail_to_pass", []))
        pass_to_pass = _normalize_expected_tests(active_task.get("pass_to_pass", []))
        verified = True
        if fail_to_pass:
            verified = fail_to_pass.issubset(passed)
        else:
            verified = test_result.returncode == 0
        if pass_to_pass:
            verified = verified and not (pass_to_pass & failed)
        elif test_result.returncode != 0:
            verified = False
        return VerificationOutcome(
            verified=verified,
            status="success" if verified else "verify_fail",
            output=test_result.output,
            passed_tests=tuple(sorted(passed)),
            failed_tests=tuple(sorted(failed)),
            changed_files=changed_files,
        )

    def locate_failure_point(self, *, trajectory: dict, step_states: list[dict]) -> dict:
        if trajectory.get("terminal_status") == "no_patch":
            index = max(len(step_states) - 1, 0)
            state_path = step_states[index]["path"] if step_states else ""
            return {
                "step_index": index,
                "failure_kind": "no_patch",
                "localization_evidence": "student ended without a patch",
                "offline_hints_used": tuple(sorted(self.ref_files)) if self.ref_files else (),
                "state_path": state_path,
            }

        failed_tests = set(trajectory.get("task_metadata", {}).get("failed_tests", []) or [])
        pass_to_pass = _normalize_expected_tests(trajectory.get("task_metadata", {}).get("pass_to_pass", []))
        ref_paths = self.ref_files
        chosen_index = max(len(step_states) - 1, 0)
        chosen_reason = "last state before terminal failure"
        offline_hints_used: list[str] = []

        for idx in range(len(step_states) - 1, -1, -1):
            changed_files = set(step_states[idx].get("changed_files", []))
            if ref_paths and changed_files & ref_paths:
                chosen_index = idx
                chosen_reason = "last state touching reference files"
                offline_hints_used.append("ref_files")
                break
            if changed_files:
                chosen_index = idx
                chosen_reason = "last state that changed the workspace"
                break

        failure_kind = "verify_fail"
        if failed_tests and pass_to_pass and (failed_tests & pass_to_pass):
            failure_kind = "terminal_test_regression"
            offline_hints_used.append("pass_to_pass")
        elif ref_paths and step_states:
            changed_files = set(step_states[chosen_index].get("changed_files", []))
            if not (changed_files & ref_paths):
                failure_kind = "wrong_patch"
                offline_hints_used.append("ref_files")

        return {
            "step_index": chosen_index,
            "failure_kind": failure_kind,
            "localization_evidence": chosen_reason,
            "offline_hints_used": tuple(dict.fromkeys(offline_hints_used)),
            "state_path": step_states[chosen_index]["path"] if step_states else "",
        }

    @staticmethod
    def build_verifier_result(*, trajectory: dict, failure_point: dict | None = None, step_count: int) -> VerifierResult:
        success = bool(trajectory.get("verify_passed", False))
        near_miss = (not success) and trajectory.get("terminal_status") == "verify_fail" and bool(trajectory.get("changed_files"))
        if step_count <= 0:
            step_count = 1
        first_error_index = failure_point.get("step_index", -1) if failure_point else (-1 if success else 0)
        local_scores: list[float] = []
        for idx in range(step_count):
            if success:
                local_scores.append(1.0)
            elif first_error_index >= 0 and idx < first_error_index:
                local_scores.append(0.5)
            else:
                local_scores.append(0.0)
        terminal_score = 1.0 if success else (0.5 if near_miss else 0.0)
        process_weights = tuple(1.0 if score > 0 else -1.0 for score in local_scores)
        return VerifierResult(
            terminal_score=terminal_score,
            success=success,
            near_miss=near_miss,
            first_error_index=first_error_index,
            switch_step=0,
            potentials=tuple(local_scores),
            local_scores=tuple(local_scores),
            env_rewards=tuple(0.0 for _ in range(step_count)),
            process_rewards=tuple(local_scores),
            process_returns=tuple(local_scores),
            process_weights=process_weights,
            baseline=0.0,
            metadata={
                "terminal_status": trajectory.get("terminal_status", ""),
                "changed_files": trajectory.get("changed_files", []),
            },
        )


__all__ = [
    "SweTerminalVerifier",
    "VerificationOutcome",
    "extract_ref_files",
    "parse_test_output",
]
