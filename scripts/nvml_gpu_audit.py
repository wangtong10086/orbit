#!/usr/bin/env python3
"""Independent NVML-based GPU/process memory auditor for training bundles."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import socket
import sys
import time
import traceback
from typing import Any

try:
    import pynvml
except Exception as exc:  # pragma: no cover - exercised via runtime behavior
    pynvml = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


_STOP = False


def _handle_stop(signum: int, _frame) -> None:
    global _STOP
    _STOP = True


for _sig in (signal.SIGINT, signal.SIGTERM):
    signal.signal(_sig, _handle_stop)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_mib(value: int | None) -> float | None:
    if value is None:
        return None
    if getattr(pynvml, "NVML_VALUE_NOT_AVAILABLE", object()) == value:
        return None
    return round(value / (1024 * 1024), 3)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _pid_metadata(pid: int) -> dict[str, Any]:
    proc_root = Path("/proc") / str(pid)
    cmdline = ""
    try:
        raw = (proc_root / "cmdline").read_bytes()
        if raw:
            cmdline = raw.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()
    except OSError:
        cmdline = ""
    return {
        "pid": pid,
        "process_name": _read_text(proc_root / "comm"),
        "cmdline": cmdline,
    }


def _get_process_fn(name_candidates: tuple[str, ...]):
    for name in name_candidates:
        fn = getattr(pynvml, name, None)
        if fn is not None:
            return fn
    return None


def _device_processes(handle, *, kind: str) -> list[dict[str, Any]]:
    if kind == "compute":
        fn = _get_process_fn(
            (
                "nvmlDeviceGetComputeRunningProcesses_v3",
                "nvmlDeviceGetComputeRunningProcesses_v2",
                "nvmlDeviceGetComputeRunningProcesses",
            )
        )
    else:
        fn = _get_process_fn(
            (
                "nvmlDeviceGetGraphicsRunningProcesses_v3",
                "nvmlDeviceGetGraphicsRunningProcesses_v2",
                "nvmlDeviceGetGraphicsRunningProcesses",
            )
        )
    if fn is None:
        return []
    try:
        records = fn(handle)
    except Exception:
        return []
    result: list[dict[str, Any]] = []
    for record in records or []:
        pid = int(getattr(record, "pid", -1))
        item = {
            "kind": kind,
            "used_gpu_memory_mib": _to_mib(getattr(record, "usedGpuMemory", None)),
            **_pid_metadata(pid),
        }
        result.append(item)
    return result


def _device_snapshot(index: int) -> dict[str, Any]:
    handle = pynvml.nvmlDeviceGetHandleByIndex(index)
    mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
    util = pynvml.nvmlDeviceGetUtilizationRates(handle)
    return {
        "index": index,
        "uuid": pynvml.nvmlDeviceGetUUID(handle),
        "name": pynvml.nvmlDeviceGetName(handle),
        "memory_total_mib": _to_mib(mem.total),
        "memory_used_mib": _to_mib(mem.used),
        "memory_free_mib": _to_mib(mem.free),
        "utilization_gpu_percent": int(util.gpu),
        "utilization_memory_percent": int(util.memory),
        "processes": _device_processes(handle, kind="compute") + _device_processes(handle, kind="graphics"),
    }


@dataclass
class AuditConfig:
    output: Path
    interval_seconds: float
    max_samples: int | None = None


def _write_record(fp, payload: dict[str, Any]) -> None:
    fp.write(json.dumps(payload, ensure_ascii=False) + "\n")
    fp.flush()


def _run(config: AuditConfig) -> int:
    config.output.parent.mkdir(parents=True, exist_ok=True)
    with config.output.open("a", encoding="utf-8") as fp:
        _write_record(
            fp,
            {
                "event": "start",
                "timestamp": _utc_now(),
                "hostname": socket.gethostname(),
                "audit_pid": os.getpid(),
                "interval_seconds": config.interval_seconds,
            },
        )

        if pynvml is None:
            _write_record(
                fp,
                {
                    "event": "error",
                    "timestamp": _utc_now(),
                    "hostname": socket.gethostname(),
                    "error": f"pynvml import failed: {_IMPORT_ERROR}",
                },
            )
            return 1

        pynvml.nvmlInit()
        try:
            device_count = pynvml.nvmlDeviceGetCount()
            _write_record(
                fp,
                {
                    "event": "inventory",
                    "timestamp": _utc_now(),
                    "hostname": socket.gethostname(),
                    "device_count": device_count,
                    "devices": [_device_snapshot(i) for i in range(device_count)],
                },
            )

            sample_index = 0
            while not _STOP:
                sample_index += 1
                _write_record(
                    fp,
                    {
                        "event": "sample",
                        "timestamp": _utc_now(),
                        "hostname": socket.gethostname(),
                        "sample_index": sample_index,
                        "devices": [_device_snapshot(i) for i in range(device_count)],
                    },
                )
                if config.max_samples is not None and sample_index >= config.max_samples:
                    break
                time.sleep(config.interval_seconds)
        except Exception as exc:  # pragma: no cover - exercised via runtime behavior
            _write_record(
                fp,
                {
                    "event": "error",
                    "timestamp": _utc_now(),
                    "hostname": socket.gethostname(),
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                },
            )
            return 1
        finally:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass
            _write_record(
                fp,
                {
                    "event": "stop",
                    "timestamp": _utc_now(),
                    "hostname": socket.gethostname(),
                    "audit_pid": os.getpid(),
                },
            )
    return 0


def _parse_args(argv: list[str]) -> AuditConfig:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="JSONL output path")
    parser.add_argument("--interval-seconds", type=float, default=1.0, help="Polling interval in seconds")
    parser.add_argument("--max-samples", type=int, default=None, help="Optional limit for testing")
    args = parser.parse_args(argv)
    return AuditConfig(
        output=Path(args.output).expanduser(),
        interval_seconds=args.interval_seconds,
        max_samples=args.max_samples,
    )


def main(argv: list[str] | None = None) -> int:
    return _run(_parse_args(list(argv or sys.argv[1:])))


if __name__ == "__main__":
    raise SystemExit(main())
