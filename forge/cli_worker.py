"""Execution-plane CLI family."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import click

from forge.core.execution.bundle import JobBundle
from forge.core.contracts.execution import (
    CollectArtifactsRequest,
    ExecutionRequest,
    LaunchModeKind,
    LaunchModeSpec,
    PlacementKind,
    PlacementSpec,
    ResourceRequest,
    RunLogsRequest,
    RunStatusRequest,
    TerminateRunRequest,
)
from forge.core.execution.service import ExecutionService
from forge.foundation.audit import AuditEvent, AuditWriter
from forge.foundation.schema import RequestContext, SchemaErrorResponse, ValidationIssue


def _run(coro):
    return asyncio.run(coro)


def _bundle(bundle_dir: str) -> JobBundle:
    return JobBundle(Path(bundle_dir).resolve())


def _load_handle(bundle: JobBundle):
    try:
        return bundle.load_run_handle()
    except FileNotFoundError as exc:
        raise click.ClickException(f"No recorded run handle for bundle: {bundle.path}") from exc


def _context(source: str = "cli.worker") -> RequestContext:
    return RequestContext(actor="cli", source=source)


def _audit(action: str, context: RequestContext, entity_type: str, entity_id: str, request=None, result=None) -> None:
    writer = AuditWriter()
    event = AuditEvent[dict | None, dict | None].build(
        context=context,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        request=request.model_dump(mode="json") if hasattr(request, "model_dump") else request,
        result=result.model_dump(mode="json") if hasattr(result, "model_dump") else result,
    )
    writer.write_event(event)


def _schema_error(exc) -> click.ClickException:
    issues = [
        ValidationIssue(
            loc=tuple(str(part) for part in err.get("loc", ())),
            msg=err.get("msg", "validation error"),
            kind=err.get("type", "value_error"),
        )
        for err in exc.errors()
    ]
    payload = SchemaErrorResponse(issues=issues)
    return click.ClickException(payload.model_dump_json(indent=2))


@click.group()
def worker():
    """Execution-plane worker commands."""


@worker.command(name="validate-bundle")
@click.argument("bundle_dir")
def validate_bundle(bundle_dir):
    bundle = _bundle(bundle_dir)
    issues = bundle.validate()
    if issues:
        for issue in issues:
            click.echo(f"ERROR: {issue}", err=True)
        raise click.ClickException("Bundle validation failed")
    _audit("validate_bundle", _context(), "bundle", str(bundle.path), result={"valid": True})
    click.echo("Bundle is valid")


@worker.command(name="run")
@click.argument("bundle_dir")
@click.option("--placement", "placement_kind", default="local", type=click.Choice(["local", "targon_rental"]))
@click.option("--launch-mode", "launch_mode_kind", default="docker_image", type=click.Choice(["host_process", "docker_image"]))
@click.option("--target", default="", help="Target machine selector for remote placements")
@click.option("--image", default="", help="Container image for docker_image mode")
@click.option("--gpu-type", default="", help="Requested GPU type")
@click.option("--gpu-count", default=1, type=int, help="Requested GPU count")
@click.option("--cpu-count", default=0, type=int, help="Requested CPU count")
@click.option("--memory-gb", default=0, type=int, help="Requested memory in GB")
@click.option("--foreground/--detach", default=False, help="Run in foreground instead of background")
@click.pass_context
def worker_run(ctx, bundle_dir, placement_kind, launch_mode_kind, target, image, gpu_type, gpu_count, cpu_count, memory_gb, foreground):
    bundle = _bundle(bundle_dir)
    execution = ExecutionService(ctx.obj["config"])
    context = _context()
    request = ExecutionRequest(
        bundle_path=str(bundle.path),
        placement=PlacementSpec(kind=PlacementKind(placement_kind), target=target),
        launch_mode=LaunchModeSpec(kind=LaunchModeKind(launch_mode_kind), image=image, detach=not foreground),
        resources=ResourceRequest(gpu_type=gpu_type or "unknown", gpu_count=gpu_count, cpu_count=cpu_count, memory_gb=memory_gb),
        context=context,
    )
    try:
        handle = _run(execution.run(request))
    except Exception as exc:
        if hasattr(exc, "errors"):
            raise _schema_error(exc) from exc
        raise
    bundle.write_run_handle(handle)
    _audit("run_bundle", context, "run_handle", handle.run_id, request=request, result=handle)
    click.echo(json.dumps({"runtime": handle.runtime_kind, "run_id": handle.run_id, "target": handle.target_id}, indent=2))


@worker.command(name="status")
@click.argument("bundle_dir")
@click.pass_context
def worker_status(ctx, bundle_dir):
    bundle = _bundle(bundle_dir)
    handle = _load_handle(bundle)
    execution = ExecutionService(ctx.obj["config"])
    request = RunStatusRequest(handle=handle, context=_context())
    status = _run(execution.status(request))
    bundle.write_run_status(status)
    _audit("run_status", request.context, "run_handle", handle.run_id, request=request, result=status)
    click.echo(json.dumps({"runtime": status.runtime_kind, "run_id": status.run_id, "state": status.state.value, "detail": status.detail, "metadata": status.metadata}, indent=2, ensure_ascii=False))


@worker.command(name="logs")
@click.argument("bundle_dir")
@click.option("--tail", default=100, type=int)
@click.pass_context
def worker_logs(ctx, bundle_dir, tail):
    bundle = _bundle(bundle_dir)
    handle = _load_handle(bundle)
    execution = ExecutionService(ctx.obj["config"])
    request = RunLogsRequest(handle=handle, tail=tail, context=_context())
    output = _run(execution.logs(request))
    _audit("run_logs", request.context, "run_handle", handle.run_id, request=request, result={"tail": tail, "length": len(output)})
    if output:
        click.echo(output)


@worker.command(name="collect")
@click.argument("bundle_dir")
@click.pass_context
def worker_collect(ctx, bundle_dir):
    bundle = _bundle(bundle_dir)
    handle = _load_handle(bundle)
    execution = ExecutionService(ctx.obj["config"])
    request = CollectArtifactsRequest(handle=handle, context=_context())
    manifest = _run(execution.collect(request))
    bundle.update_manifest(manifest)
    _audit("collect_artifacts", request.context, "run_handle", handle.run_id, request=request, result=manifest)
    click.echo(json.dumps({"logs": manifest.logs, "artifacts": manifest.artifacts, "metadata": manifest.metadata}, indent=2, ensure_ascii=False))


@worker.command(name="terminate")
@click.argument("bundle_dir")
@click.pass_context
def worker_terminate(ctx, bundle_dir):
    bundle = _bundle(bundle_dir)
    handle = _load_handle(bundle)
    execution = ExecutionService(ctx.obj["config"])
    request = TerminateRunRequest(handle=handle, context=_context())
    _run(execution.terminate(request))
    _audit("terminate_run", request.context, "run_handle", handle.run_id, request=request, result={"terminated": True})
    click.echo(f"Terminated {handle.runtime_kind}:{handle.run_id}")
