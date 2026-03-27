"""Tests for forge/compute — Targon backend and ComputeManager."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from forge.compute.base import GpuInstance
from forge.compute.targon import TargonBackend, GPU_RESOURCE_MAP


class TestGpuResourceMap:
    def test_h200_small(self):
        assert GPU_RESOURCE_MAP["H200"] == "h200-small"

    def test_h200_medium(self):
        assert GPU_RESOURCE_MAP["H200-M"] == "h200-medium"

    def test_h100_small(self):
        assert GPU_RESOURCE_MAP["H100"] == "h100-small"

    def test_b200_small(self):
        assert GPU_RESOURCE_MAP["B200"] == "b200-small"

    def test_rtx4090(self):
        assert GPU_RESOURCE_MAP["RTX4090"] == "rtx4090-small"

    def test_rtx6000b(self):
        assert GPU_RESOURCE_MAP["RTX6000B"] == "rtx6000b-small"

    def test_passthrough(self):
        """Unknown GPU types should pass through as-is."""
        backend = TargonBackend(api_key="dummy")
        # GPU_RESOURCE_MAP.get() falls back to the raw value
        assert GPU_RESOURCE_MAP.get("custom-tier", "custom-tier") == "custom-tier"


class TestTargonBackendInit:
    def test_init(self):
        backend = TargonBackend(api_key="test-key-123")
        assert backend.api_key == "test-key-123"

    def test_new_client_import(self):
        """Verify targon-sdk Client can be imported."""
        from targon import Client
        assert Client is not None


class TestGpuInstance:
    def test_defaults(self):
        inst = GpuInstance(id="test-123", backend="targon", gpu_type="H200", status="ready")
        assert inst.id == "test-123"
        assert inst.backend == "targon"
        assert inst.gpu_type == "H200"
        assert inst.status == "ready"
        assert inst.gpu_count == 1
        assert inst.cost_per_hour == 0.0
        assert inst.metadata == {}

    def test_with_url(self):
        inst = GpuInstance(
            id="wrk-abc",
            backend="targon",
            gpu_type="H200",
            status="provisioning",
            url="https://wrk-abc.serverless.targon.com",
        )
        assert inst.url == "https://wrk-abc.serverless.targon.com"

    def test_metadata(self):
        inst = GpuInstance(
            id="wrk-abc",
            backend="targon",
            gpu_type="H200",
            status="ready",
            metadata={"name": "my-container", "resource": "h200-small"},
        )
        assert inst.metadata["name"] == "my-container"
        assert inst.metadata["resource"] == "h200-small"
