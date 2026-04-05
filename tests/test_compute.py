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

    def test_download_uses_tar_fallback_after_rsync_failure(self, monkeypatch, tmp_path):
        backend = SshBackend(str(tmp_path / "machines.json"))
        instance = GpuInstance(
            id="m1",
            backend="ssh",
            gpu_type="H200",
            status="ready",
            host="example.com",
            metadata={"key": ""},
        )
        tar_calls = []

        def fake_run(cmd, check=False, timeout=None, capture_output=False, **kwargs):
            if cmd[0] == "rsync":
                raise subprocess.CalledProcessError(1, cmd)
            raise AssertionError(f"unexpected subprocess call: {cmd}")

        monkeypatch.setattr("forge.compute.ssh.subprocess.run", fake_run)
        monkeypatch.setattr(
            backend,
            "_download_via_tar",
            lambda inst, remote_path, local_path: tar_calls.append((inst.id, remote_path, local_path)),
        )

        asyncio.run(backend.download(instance, "/root/project/artifacts", str(tmp_path / "artifacts")))

        assert tar_calls == [("m1", "/root/project/artifacts", str(tmp_path / "artifacts"))]

    def test_save_machines_merges_with_existing_registry(self, tmp_path):
        backend = SshBackend(str(tmp_path / "machines.json"))
        backend._save_machines(
            [
                {"name": "machine-a", "host": "10.0.0.1", "port": 22, "user": "root"},
            ]
        )
        backend._save_machines(
            [
                {"name": "machine-b", "host": "10.0.0.2", "port": 2222, "user": "root"},
            ]
        )

        machines = backend._load_machines()
        assert {item["name"] for item in machines} == {"machine-a", "machine-b"}

    def test_save_machines_keeps_distinct_entries_for_same_host_different_ports(self, tmp_path):
        backend = SshBackend(str(tmp_path / "machines.json"))
        backend._save_machines(
            [
                {"name": "machine-a", "host": "10.0.0.1", "port": 30001, "user": "root"},
            ]
        )
        backend._save_machines(
            [
                {"name": "machine-b", "host": "10.0.0.1", "port": 30002, "user": "root"},
            ]
        )

        machines = sorted(backend._load_machines(), key=lambda item: item["name"])
        assert [item["name"] for item in machines] == ["machine-a", "machine-b"]
        assert [item["port"] for item in machines] == [30001, 30002]


class TestComputeManager:
    def test_only_registers_ssh_backend(self, tmp_path):
        config = ForgeConfig(project_root=tmp_path, data_dir=tmp_path / "data", machines_file=tmp_path / "machines.json")
        manager = ComputeManager(config)
        assert list(manager.backends.keys()) == ["ssh"]

    def test_capacity_empty_in_rental_only_mode(self, tmp_path):
        config = ForgeConfig(project_root=tmp_path, data_dir=tmp_path / "data", machines_file=tmp_path / "machines.json")
        manager = ComputeManager(config)
        assert asyncio.run(manager.capacity()) == {}
