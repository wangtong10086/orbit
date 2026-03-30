"""Tests for forge.compute in rental-only mode."""

import asyncio
import io
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from forge.compute.base import GpuInstance
from forge.compute.manager import ComputeManager
from forge.compute.ssh import SshBackend
from forge.config import ForgeConfig


class TestGpuInstance:
    def test_defaults(self):
        inst = GpuInstance(id="test-123", backend="ssh", gpu_type="H200", status="ready")
        assert inst.id == "test-123"
        assert inst.backend == "ssh"
        assert inst.gpu_type == "H200"
        assert inst.status == "ready"
        assert inst.gpu_count == 1
        assert inst.cost_per_hour == 0.0
        assert inst.metadata == {}

    def test_with_host(self):
        inst = GpuInstance(
            id="m1",
            backend="ssh",
            gpu_type="H200",
            status="ready",
            host="ssh.deployments.targon.com",
        )
        assert inst.host == "ssh.deployments.targon.com"


class TestSshBackend:
    def test_write_after_sentinel_strips_banner_bytes(self):
        output = io.BytesIO()
        found = SshBackend._write_after_sentinel(
            io.BytesIO(b"Connecting to container demo\n__AFFINE_TAR_BEGIN__\nabc\x00xyz"),
            output,
        )
        assert found is True
        assert output.getvalue() == b"abc\x00xyz"

    def test_upload_uses_tar_fallback_for_directories(self, monkeypatch, tmp_path):
        backend = SshBackend(str(tmp_path / "machines.json"))
        instance = GpuInstance(
            id="m1",
            backend="ssh",
            gpu_type="H200",
            status="ready",
            host="example.com",
            metadata={"key": ""},
        )
        local_dir = tmp_path / "scripts"
        local_dir.mkdir()
        (local_dir / "train.sh").write_text("echo hi")
        tar_calls = []

        def fake_run(cmd, check=False, timeout=None, capture_output=False, **kwargs):
            if cmd[0] in {"rsync", "scp"}:
                raise subprocess.CalledProcessError(1, cmd)
            return None

        monkeypatch.setattr("forge.compute.ssh.subprocess.run", fake_run)
        monkeypatch.setattr(
            backend,
            "_upload_via_tar",
            lambda inst, local_path, remote_path: tar_calls.append((inst.id, local_path, remote_path)),
        )

        asyncio.run(backend.upload(instance, f"{local_dir}/", "/root/project/scripts/"))

        assert tar_calls == [("m1", f"{local_dir}/", "/root/project/scripts/")]


class TestComputeManager:
    def test_only_registers_ssh_backend(self, tmp_path):
        config = ForgeConfig(project_root=tmp_path, data_dir=tmp_path / "data", machines_file=tmp_path / "machines.json")
        manager = ComputeManager(config)
        assert list(manager.backends.keys()) == ["ssh"]

    def test_capacity_empty_in_rental_only_mode(self, tmp_path):
        config = ForgeConfig(project_root=tmp_path, data_dir=tmp_path / "data", machines_file=tmp_path / "machines.json")
        manager = ComputeManager(config)
        assert asyncio.run(manager.capacity()) == {}
