"""Execution-plane CLI family."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import click

from forge.data.collect_service import build_collect_spec
from forge.execution import (
    CollectArtifactsRequest,
    CollectPublishConfig,
    CollectTaskRenderer,
    CollectTaskSpec,
    DockerRuntime,
    DockerTarget,
    EvalTaskRenderer,
    EvalTaskSpec,
    GameCollectConfig,
    JobBundle,
    LivewebCollectConfig,
    MemorygymCollectConfig,
    ResourceRequest,
    RunBundleRequest,
    RunLogsRequest,
    RunStatusRequest,
    RuntimePreferences,
    SshTarget,
    SweCollectConfig,
    TargonProfile,
    TargonTarget,
    TerminateRunRequest,
    SshRuntime,
    TargonRuntime,
    TrainTaskRenderer,
)
from forge.execution.contracts import NavworldCollectConfig
from forge.foundation.audit import AuditEvent, AuditWriter
from forge.foundation.schema import RequestContext, SchemaErrorResponse, ValidationIssue
from forge.training.config import SwiftConfig

_build_collect_spec = build_collect_spec


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


@worker.group()
def render():
    """Render task bundles."""


@render.command(name="train")
@click.argument("dataset_path")
@click.option("--bundle-dir", required=True, help="Output bundle directory")
@click.option("--job-id", default="train-job", help="Job identifier")
@click.option("--model", default="Qwen/Qwen3-32B", help="Base model")
@click.option("--train-type", default="sft", type=click.Choice(["sft", "rlhf", "pt"]))
@click.option("--rlhf-type", default="dpo")
@click.option("--tuner-type", default="lora", type=click.Choice(["lora", "full"]))
@click.option("--lr", default=1e-4, type=float)
@click.option("--epochs", default=1, type=int)
@click.option("--batch-size", default=2, type=int)
@click.option("--grad-accum", default=8, type=int)
@click.option("--max-length", default=4096, type=int)
@click.option("--num-gpus", default=1, type=int)
@click.option("--gpu-type", default="unknown", help="Requested GPU type")
@click.option("--image", default="", help="Preferred runtime image")
@click.option("--overwrite/--no-overwrite", default=False)
def render_train(dataset_path, bundle_dir, job_id, model, train_type, rlhf_type, tuner_type, lr, epochs, batch_size, grad_accum, max_length, num_gpus, gpu_type, image, overwrite):
    """Render a training bundle from a local dataset."""
    context = _context()
    try:
        config = SwiftConfig(
            model=model,
            train_type=train_type,
            rlhf_type=rlhf_type,
            tuner_type=tuner_type,
            learning_rate=lr,
            num_train_epochs=epochs,
            per_device_train_batch_size=batch_size,
            gradient_accumulation_steps=grad_accum,
            max_length=max_length,
            num_gpus=num_gpus,
            quant_method=None if tuner_type == "full" else "bnb",
            quant_bits=None if tuner_type == "full" else 4,
        )
        bundle = TrainTaskRenderer().render(
            bundle_dir,
            job_id=job_id,
            dataset_path=dataset_path,
            config=config,
            resources=ResourceRequest(gpu_type=gpu_type, gpu_count=num_gpus),
            runtime_preferences=RuntimePreferences(image=image),
            overwrite=overwrite,
        )
    except Exception as exc:
        if hasattr(exc, "errors"):
            raise _schema_error(exc) from exc
        raise
    _audit("render_train_bundle", context, "bundle", str(bundle.path), result={"bundle_path": str(bundle.path)})
    click.echo(str(bundle.path))


@render.command(name="eval")
@click.option("--bundle-dir", required=True, help="Output bundle directory")
@click.option("--job-id", default="eval-job", help="Job identifier")
@click.option("--model", required=True, help="Model path or identifier")
@click.option("--envs", default="GAME,NAVWORLD", help="Comma-separated environments")
@click.option("--samples", default=100, type=int)
@click.option("--base-url", default="http://172.17.0.1:30000/v1")
@click.option("--concurrency", default=5, type=int)
@click.option("--seed", default=42, type=int)
@click.option("--affinetes-dir", default="/root/affinetes")
@click.option("--api-key", default="")
@click.option("--skip-build/--build", default=True)
@click.option("--gpu-type", default="unknown")
@click.option("--image", default="", help="Preferred runtime image")
@click.option("--overwrite/--no-overwrite", default=False)
def render_eval(bundle_dir, job_id, model, envs, samples, base_url, concurrency, seed, affinetes_dir, api_key, skip_build, gpu_type, image, overwrite):
    env_list = tuple(env.strip() for env in envs.split(",") if env.strip())
    context = _context()
    try:
        spec = EvalTaskSpec(
            model=model,
            environments=env_list,
            samples=samples,
            base_url=base_url,
            concurrency=concurrency,
            seed=seed,
            affinetes_dir=affinetes_dir,
            api_key=api_key,
            skip_build=skip_build,
        )
        bundle = EvalTaskRenderer().render(
            bundle_dir,
            job_id=job_id,
            spec=spec,
            resources=ResourceRequest(gpu_type=gpu_type),
            runtime_preferences=RuntimePreferences(image=image),
            overwrite=overwrite,
        )
    except Exception as exc:
        if hasattr(exc, "errors"):
            raise _schema_error(exc) from exc
        raise
    _audit("render_eval_bundle", context, "bundle", str(bundle.path), result={"bundle_path": str(bundle.path)})
    click.echo(str(bundle.path))


@render.command(name="collect")
@click.option("--env", "env_name", required=True, type=click.Choice(["GAME", "NAVWORLD", "SWE-INFINITE", "LIVEWEB", "MEMORYGYM"]))
@click.option("--bundle-dir", required=True, help="Output bundle directory")
@click.option("--job-id", default="collect-job", help="Job identifier")
@click.option("-o", "--output-filename", default="", help="Staging output filename")
@click.option("--hf-repo", default="", help="HF dataset repo override")
@click.option("--source", default="", help="Source label recorded in canonical data")
@click.option("-n", "--num", default=10, type=int, help="Generic sample/seeds count for supported collectors")
@click.option("--model", default="qwen3-max")
@click.option("--start-id", default=0, type=int)
@click.option("--concurrency", default=3, type=int)
@click.option("--type", "problem_type", default=None)
@click.option("--phase1", is_flag=True)
@click.option("--seeds", default="1-10", help="LIVEWEB seed range")
@click.option("--subtasks", default="1", help="LIVEWEB subtask counts")
@click.option("--plugins", default="openmeteo", help="LIVEWEB plugins")
@click.option("--cache-dir", default="", help="LIVEWEB cache dir")
@click.option("--timeout", default=240, type=int, help="LIVEWEB timeout seconds")
@click.option("--game", "game_name", default=None, help="GAME single-game selector")
@click.option("--all-games", is_flag=True, help="Generate all supported GAME environments")
@click.option("--attempt-multiplier", default=4, type=int, help="GAME oversampling factor")
@click.option("--generator-source", default="default", type=click.Choice(["default", "policy_model"]), help="GAME generator backend")
@click.option("--template", "templates", multiple=True, help="MEMORYGYM templates")
@click.option("--tier", default="lite", type=click.Choice(["lite", "standard", "hard", "multi"]))
@click.option("--tier-mix", is_flag=True)
@click.option("-j", "--jobs", default=1, type=int, help="MEMORYGYM workers")
@click.option("--split-target", default=5000, type=int, help="MEMORYGYM split target count")
@click.option("--balance/--no-balance", default=True, help="MEMORYGYM split balancing")
@click.option("--shuffle-seed", default=42, type=int)
@click.option("--machine", default="", help="SWE registered machine selector")
@click.option("--image", default="", help="Preferred runtime image")
@click.option("--overwrite/--no-overwrite", default=False)
def render_collect(
    env_name,
    bundle_dir,
    job_id,
    output_filename,
    hf_repo,
    source,
    num,
    model,
    start_id,
    concurrency,
    problem_type,
    phase1,
    seeds,
    subtasks,
    plugins,
    cache_dir,
    timeout,
    game_name,
    all_games,
    attempt_multiplier,
    generator_source,
    templates,
    tier,
    tier_mix,
    jobs,
    split_target,
    balance,
    shuffle_seed,
    machine,
    image,
    overwrite,
):
    context = _context()
    default_output = {
        "NAVWORLD": "navworld_synthetic.jsonl",
        "LIVEWEB": "liveweb.jsonl",
        "GAME": "game.jsonl",
        "MEMORYGYM": "memorygym.jsonl",
        "SWE-INFINITE": "swe_infinite.jsonl",
    }[env_name]
    try:
        spec = _build_collect_spec(
            env_name=env_name,
            output_filename=output_filename or default_output,
            hf_repo=hf_repo,
            source=source,
            num=num,
            model=model,
            start_id=start_id,
            concurrency=concurrency,
            problem_type=problem_type,
            phase1=phase1,
            seeds=seeds,
            subtasks=subtasks,
            plugins=plugins,
            cache_dir=cache_dir,
            timeout=timeout,
            game_name=game_name,
            all_games=all_games,
            attempt_multiplier=attempt_multiplier,
            generator_source=generator_source,
            templates=templates,
            tier=tier,
            tier_mix=tier_mix,
            jobs=jobs,
            split_target=split_target,
            balance=balance,
            shuffle_seed=shuffle_seed,
            machine=machine,
        )
        bundle = CollectTaskRenderer().render(
            bundle_dir,
            job_id=job_id,
            spec=spec,
            runtime_preferences=RuntimePreferences(image=image),
            overwrite=overwrite,
        )
    except Exception as exc:
        if hasattr(exc, "errors"):
            raise _schema_error(exc) from exc
        raise
    _audit("render_collect_bundle", context, "bundle", str(bundle.path), result={"bundle_path": str(bundle.path)})
    click.echo(str(bundle.path))


@render.command(name="collect-navworld")
@click.option("--bundle-dir", required=True, help="Output bundle directory")
@click.option("--job-id", default="collect-navworld", help="Job identifier")
@click.option("-n", "--num", default=10, type=int)
@click.option("-o", "--output-filename", default="navworld_synthetic.jsonl")
@click.option("--model", default="qwen3-max")
@click.option("--start-id", default=0, type=int)
@click.option("--concurrency", default=3, type=int)
@click.option("--type", "problem_type", default=None)
@click.option("--phase1", is_flag=True)
@click.option("--image", default="", help="Preferred runtime image")
@click.option("--overwrite/--no-overwrite", default=False)
def render_collect_navworld(bundle_dir, job_id, num, output_filename, model, start_id, concurrency, problem_type, phase1, image, overwrite):
    return render_collect.callback(
        env_name="NAVWORLD",
        bundle_dir=bundle_dir,
        job_id=job_id,
        output_filename=output_filename,
        hf_repo="",
        source="",
        num=num,
        model=model,
        start_id=start_id,
        concurrency=concurrency,
        problem_type=problem_type,
        phase1=phase1,
        seeds="1-10",
        subtasks="1",
        plugins="openmeteo",
        cache_dir="",
        timeout=240,
        game_name=None,
        all_games=False,
        attempt_multiplier=4,
        generator_source="default",
        templates=(),
        tier="lite",
        tier_mix=False,
        jobs=1,
        split_target=5000,
        balance=True,
        shuffle_seed=42,
        machine="",
        image=image,
        overwrite=overwrite,
    )


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


def _runtime_for(config, runtime_name: str):
    if runtime_name == "docker":
        return DockerRuntime(config)
    if runtime_name == "ssh":
        return SshRuntime(config)
    if runtime_name == "targon":
        return TargonRuntime(config)
    raise click.ClickException(f"Unknown runtime: {runtime_name}")


@worker.command(name="run")
@click.argument("bundle_dir")
@click.option("--runtime", "runtime_name", default="docker", type=click.Choice(["docker", "ssh", "targon"]))
@click.option("--target", default="", help="SSH target machine name or host")
@click.option("--profile", default="", help="Runtime profile such as bootstrap or rental")
@click.option("--image", default="", help="Override runtime image")
@click.option("--gpu-type", default="", help="Requested GPU type")
@click.option("--foreground/--detach", default=False, help="Run in foreground instead of background")
@click.pass_context
def worker_run(ctx, bundle_dir, runtime_name, target, profile, image, gpu_type, foreground):
    bundle = _bundle(bundle_dir)
    runtime = _runtime_for(ctx.obj["config"], runtime_name)
    context = _context()
    if runtime_name == "docker":
        target_model = DockerTarget(target=target, image=image, detach=not foreground)
    elif runtime_name == "ssh":
        target_model = SshTarget(target=target, profile=profile, image=image, gpu_type=gpu_type, detach=not foreground)
    else:
        target_model = TargonTarget(
            target=target,
            profile=TargonProfile(profile) if profile else TargonProfile.RENTAL,
            image=image,
            gpu_type=gpu_type,
            detach=not foreground,
        )
    request = RunBundleRequest(bundle_path=str(bundle.path), target=target_model, context=context)
    handle = _run(runtime.run(request))
    _audit("run_bundle", context, "run_handle", handle.run_id, request=request, result=handle)
    click.echo(json.dumps({"runtime": handle.runtime_kind, "run_id": handle.run_id, "target": handle.target_id}, indent=2))


@worker.command(name="status")
@click.argument("bundle_dir")
@click.pass_context
def worker_status(ctx, bundle_dir):
    bundle = _bundle(bundle_dir)
    handle = _load_handle(bundle)
    runtime = _runtime_for(ctx.obj["config"], handle.runtime_kind)
    request = RunStatusRequest(handle=handle, context=_context())
    status = _run(runtime.status(request))
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
    runtime = _runtime_for(ctx.obj["config"], handle.runtime_kind)
    request = RunLogsRequest(handle=handle, tail=tail, context=_context())
    output = _run(runtime.logs(request))
    _audit("run_logs", request.context, "run_handle", handle.run_id, request=request, result={"tail": tail, "length": len(output)})
    if output:
        click.echo(output)


@worker.command(name="collect")
@click.argument("bundle_dir")
@click.pass_context
def worker_collect(ctx, bundle_dir):
    bundle = _bundle(bundle_dir)
    handle = _load_handle(bundle)
    runtime = _runtime_for(ctx.obj["config"], handle.runtime_kind)
    request = CollectArtifactsRequest(handle=handle, context=_context())
    manifest = _run(runtime.collect(request))
    bundle.update_manifest(manifest)
    _audit("collect_artifacts", request.context, "run_handle", handle.run_id, request=request, result=manifest)
    click.echo(json.dumps({"logs": manifest.logs, "artifacts": manifest.artifacts, "metadata": manifest.metadata}, indent=2, ensure_ascii=False))


@worker.command(name="terminate")
@click.argument("bundle_dir")
@click.pass_context
def worker_terminate(ctx, bundle_dir):
    bundle = _bundle(bundle_dir)
    handle = _load_handle(bundle)
    runtime = _runtime_for(ctx.obj["config"], handle.runtime_kind)
    request = TerminateRunRequest(handle=handle, context=_context())
    _run(runtime.terminate(request))
    _audit("terminate_run", request.context, "run_handle", handle.run_id, request=request, result={"terminated": True})
    click.echo(f"Terminated {handle.runtime_kind}:{handle.run_id}")
