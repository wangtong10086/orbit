"""Task-submission normalization helpers."""

from __future__ import annotations

from orbit.core.contracts.execution import json_safe_dump
from orbit.core.contracts.tasks import TaskSubmission
from orbit.core.control.registry import TaskPlugin


def normalize_submission(plugin: TaskPlugin, submission: TaskSubmission) -> tuple[TaskSubmission, object]:
    parsed = plugin.parse_request(submission.task_request)
    if hasattr(parsed, "to_payload_dict"):
        normalized = json_safe_dump(parsed.to_payload_dict())
    else:
        normalized = json_safe_dump(parsed)
    return submission.model_copy(update={"task_request": normalized}), parsed
