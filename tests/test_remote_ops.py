"""Tests for remote-ops helpers used by launcher workflows."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from forge.compute.base import GpuInstance
from forge.remote_ops.targon_rental_service import wait_for_ssh_ready


class _FakeBackend:
    def __init__(self):
        self.calls = 0

    async def exec(self, instance, command: str, timeout: int = 30):
        self.calls += 1
        if self.calls == 1:
            return 255, "", "connection refused"
        return 0, "affine_ssh_ready\n", ""


def test_wait_for_ssh_ready_retries_until_success(monkeypatch):
    backend = _FakeBackend()
    instance = GpuInstance(id="m1", backend="ssh", gpu_type="H200", status="ready", host="ssh.example.com")
    monkeypatch.setattr("forge.remote_ops.targon_rental_service.time.sleep", lambda *_: None)
    wait_for_ssh_ready(backend, instance, timeout_seconds=5, poll_seconds=0)
    assert backend.calls == 2
