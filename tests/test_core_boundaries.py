"""Static and lightweight behavior checks for the new core/task split."""

from __future__ import annotations

from pathlib import Path

from orbit.core.control.registry import TaskRegistry
from orbit.tasks import build_default_task_registry


def test_core_package_does_not_import_task_plugins_directly():
    core_root = Path("orbit/core")
    offenders: list[str] = []
    for path in core_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "orbit.tasks" in text:
            offenders.append(str(path))
    assert offenders == []


def test_core_package_does_not_import_rl_package_internals():
    core_root = Path("orbit/core")
    offenders: list[str] = []
    for path in core_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        forbidden = (
            "affine_rl_runtime.",
            "affine_ms_swift.",
            "orbit_env_memorygym.",
            "orbit_env_affinetes.",
        )
        for marker in forbidden:
            if marker in text and f"{marker}api" not in text:
                offenders.append(str(path))
                break
    assert offenders == []


def test_default_task_registry_contains_builtin_plugins():
    registry = build_default_task_registry()
    assert registry.list_task_types() == ["collection", "evaluation", "training"]


def test_task_registry_rejects_duplicate_plugin_ids():
    registry = TaskRegistry()

    class _Plugin:
        task_type = "dup"
        job_kind = None

    registry.register(_Plugin())
    try:
        registry.register(_Plugin())
        assert False, "Expected duplicate registration failure"
    except ValueError as exc:
        assert "already registered" in str(exc)
