"""Tests for runtime-facing data operations and remediation fixes."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from forge.data.swe_ops import distill_status, sync_new_trajectories


class TestSweOps:
    def test_distill_status_reports_infra_error_instead_of_parsing_crash(self, monkeypatch):
        responses = iter(
            [
                ("", 1),
                ("", 0),
                ("wrk-remote: Permission denied (publickey).", 255),
            ]
        )
        monkeypatch.setattr("forge.data.swe_ops._ssh_run", lambda *args, **kwargs: next(responses))

        status = distill_status()

        assert status["infra_error"] == (
            "container probe failed: wrk-remote: Permission denied (publickey)."
        )
        assert status["containers"] == 0

    def test_sync_new_trajectories_returns_blocked_reason(self, monkeypatch):
        monkeypatch.setattr(
            "forge.data.swe_ops.distill_status",
            lambda: {
                "running": False,
                "processes": [],
                "output_files": [],
                "containers": 0,
                "infra_error": "process probe failed: permission denied",
            },
        )

        result = sync_new_trajectories(dry_run=True)

        assert result["blocked_reason"] == "process probe failed: permission denied"
        assert result["new_count"] == 0
