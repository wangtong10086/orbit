from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace


def _load_nvml_audit_module(monkeypatch):
    module_path = Path("/home/ubuntu/orbit/scripts/nvml_gpu_audit.py")
    spec = importlib.util.spec_from_file_location("nvml_gpu_audit_test", module_path)
    module = importlib.util.module_from_spec(spec)

    class _Proc:
        def __init__(self, pid: int, used: int):
            self.pid = pid
            self.usedGpuMemory = used

    class _FakePynvml:
        __version__ = "test"
        NVML_VALUE_NOT_AVAILABLE = -1

        @staticmethod
        def nvmlInit():
            return None

        @staticmethod
        def nvmlShutdown():
            return None

        @staticmethod
        def nvmlDeviceGetCount():
            return 1

        @staticmethod
        def nvmlDeviceGetHandleByIndex(index: int):
            return index

        @staticmethod
        def nvmlDeviceGetUUID(handle):
            return f"GPU-{handle}"

        @staticmethod
        def nvmlDeviceGetName(handle):
            return f"Fake GPU {handle}"

        @staticmethod
        def nvmlDeviceGetMemoryInfo(handle):
            return SimpleNamespace(total=10 * 1024 * 1024, used=4 * 1024 * 1024, free=6 * 1024 * 1024)

        @staticmethod
        def nvmlDeviceGetUtilizationRates(handle):
            return SimpleNamespace(gpu=77, memory=55)

        @staticmethod
        def nvmlDeviceGetComputeRunningProcesses(handle):
            return [_Proc(1234, 2 * 1024 * 1024)]

        @staticmethod
        def nvmlDeviceGetGraphicsRunningProcesses(handle):
            return []

    monkeypatch.setitem(sys.modules, "pynvml", _FakePynvml)
    assert spec is not None and spec.loader is not None
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def test_nvml_gpu_audit_writes_jsonl(monkeypatch, tmp_path):
    module = _load_nvml_audit_module(monkeypatch)
    output = tmp_path / "audit.jsonl"
    rc = module.main(["--output", str(output), "--interval-seconds", "0.0", "--max-samples", "1"])
    assert rc == 0

    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert [record["event"] for record in records] == ["start", "inventory", "sample", "stop"]
    inventory = records[1]
    assert inventory["device_count"] == 1
    assert inventory["devices"][0]["name"] == "Fake GPU 0"
    sample = records[2]
    assert sample["devices"][0]["utilization_gpu_percent"] == 77
    assert sample["devices"][0]["processes"][0]["pid"] == 1234
