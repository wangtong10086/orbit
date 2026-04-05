"""Shared helpers for remote-operations sidecar commands."""

from __future__ import annotations

import asyncio
import json

import click

from orbit.compute.base import GpuInstance
from orbit.compute.ssh import SshBackend


def run_async(coro):
    """Helper to run async functions from Click commands."""

    return asyncio.run(coro)


def get_rental(config, machine_selector=None) -> tuple[SshBackend, GpuInstance]:
    """Load a machine from machines.json, return (SshBackend, GpuInstance)."""

    machines_path = config.project_root / "machines.json"
    if not machines_path.exists():
        raise click.ClickException("machines.json not found. Register a machine first.")

    with open(machines_path) as handle:
        data = json.load(handle)

    machines = data.get("machines", [])
    if not machines:
        raise click.ClickException("No machines in machines.json")

    if machine_selector is None:
        machine = machines[0]
    elif machine_selector.isdigit():
        idx = int(machine_selector)
        if idx >= len(machines):
            raise click.ClickException(f"Machine index {idx} out of range (have {len(machines)})")
        machine = machines[idx]
    else:
        machine = next((x for x in machines if x.get("name") == machine_selector), None)
        if machine is None:
            names = [x.get("name", x["user"]) for x in machines]
            raise click.ClickException(f"Machine '{machine_selector}' not found. Available: {names}")

    backend = SshBackend(str(machines_path))
    instance = GpuInstance(
        id=machine.get("name", machine["host"]),
        backend="ssh",
        gpu_type=machine.get("gpu_type", "unknown"),
        status="unknown",
        host=machine["host"],
        port=machine.get("port", 22),
        user=machine.get("user", "root"),
        metadata=machine,
    )
    return backend, instance
