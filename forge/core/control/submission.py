"""Task-submission normalization helpers."""

from __future__ import annotations

from forge.core.contracts.execution import json_safe_dump
from forge.core.contracts.tasks import TaskSubmission
from forge.core.control.registry import TaskPlugin


def normalize_submission(plugin: TaskPlugin, submission: TaskSubmission) -> tuple[TaskSubmission, object]:
    parsed = plugin.parse_request(submission.task_request)
    normalized = json_safe_dump(parsed)
    return submission.model_copy(update={"task_request": normalized}), parsed
