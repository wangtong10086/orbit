"""Control-plane CLI family."""

from __future__ import annotations

import json

import click

from orbit.config import OrbitConfig
from orbit.core.control.service import CoreControlService
from orbit.core.contracts.experiments import CreateExperimentRequest, RunLogsQuery, RunQuery
from orbit.core.contracts.execution import JobKind, ResourceRequest, RunState
from orbit.core.contracts.tasks import TaskSubmission
from orbit.core.contracts.templates import ExecutionOverrides
from orbit.core.experiments import ExperimentStore, TrainingLifecycleState
from orbit.core.execution.service import ExecutionService
from orbit.core.templates.registry import ExecutionTemplateRegistry
from orbit.data.collect_service import build_collect_spec
from orbit.foundation.contracts import TrainingSpec
from orbit.foundation.schema import RequestContext, SchemaErrorResponse, ValidationIssue
from orbit.tasks import build_default_task_registry
from orbit.tasks.evaluation.specs import EvalTaskSpec
from orbit.tasks.training.launcher import launch_training_from_path
from orbit.tasks.vg_sopd.launcher import launch_vg_sopd_from_path
from orbit.training.config import SwiftConfig

_build_collect_spec = build_collect_spec


def _plane(experiments_dir: str, config) -> CoreControlService:
    return CoreControlService(
        experiments=ExperimentStore(experiments_dir),
        execution=ExecutionService(config),
        templates=ExecutionTemplateRegistry(),
        task_registry=build_default_task_registry(),
    )


def _job_kind(task_name: str) -> JobKind:
    return JobKind(task_name)


def _context(source: str = "cli.control") -> RequestContext:
    return RequestContext(actor="cli", source=source)


def _update_training_lifecycle(plane: CoreControlService, experiment_id: str, status: TrainingLifecycleState, *, context: RequestContext, action: str) -> None:
    experiment = plane.load_experiment(experiment_id)
    if experiment is None:
        return
    experiment.status = status
    plane.save_experiment(experiment, context=context, action=action)


def _build_training_spec(plane: CoreControlService, experiment_id: str, dataset_path: str) -> TrainingSpec:
    experiment = plane.load_experiment(experiment_id)
    if experiment is None:
        raise click.ClickException(f"Experiment not found: {experiment_id}")
    config = SwiftConfig.model_validate(experiment.train_config)
    environments = tuple(sorted(experiment.data_config.keys())) if experiment.data_config else tuple()
    return TrainingSpec(
        experiment_id=experiment.id,
        model=config.model,
        dataset_path=dataset_path,
        train_config=config,
        environments=environments,
        output_dir=config.output_dir,
    )


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


def _execution_overrides(target: str, image: str, gpu_type: str, gpu_count: int, cpu_count: int, memory_gb: int, foreground: bool) -> ExecutionOverrides:
    return ExecutionOverrides(
        image=image,
        target=target,
        detach=not foreground,
        resources=ResourceRequest(gpu_type=gpu_type or "unknown", gpu_count=gpu_count, cpu_count=cpu_count, memory_gb=memory_gb),
    )


@click.group(name="control")
@click.option("--dir", "experiments_dir", default="experiments", help="Experiments directory")
@click.pass_context
def control(ctx, experiments_dir):
    """Control-plane commands."""
    ctx.ensure_object(dict)
    ctx.obj["experiments_dir"] = experiments_dir


@control.group(name="template")
def template_group():
    """Execution template registry commands."""


@template_group.command(name="list")
def list_templates():
    registry = ExecutionTemplateRegistry()
    for template in registry.list_templates():
        click.echo(f"{template.id}\t{template.placement.kind.value}\t{template.launch_mode.kind.value}")


@template_group.command(name="show")
@click.argument("template_id")
def show_template(template_id):
    template = ExecutionTemplateRegistry().load(template_id)
    click.echo(json.dumps(template.model_dump(mode="json"), indent=2, ensure_ascii=False))


@template_group.command(name="validate")
def validate_templates():
    issues = ExecutionTemplateRegistry().validate()
    if issues:
        for issue in issues:
            click.echo(f"ERROR: {issue}", err=True)
        raise click.ClickException("Template validation failed")
    click.echo("Templates are valid")


@control.group(name="experiment")
def experiment_group():
    """Experiment lifecycle commands."""


@experiment_group.command(name="list")
@click.option("--status", default=None, help="Filter by status")
@click.pass_context
def list_experiments(ctx, status):
    plane = _plane(ctx.obj["experiments_dir"], ctx.obj["config"])
    for experiment in plane.list_experiments(status=status):
        click.echo(f"{experiment.id}\t{experiment.status}\t{experiment.variable}")


@experiment_group.command(name="show")
@click.argument("exp_id")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def show_experiment(ctx, exp_id, as_json):
    plane = _plane(ctx.obj["experiments_dir"], ctx.obj["config"])
    experiment = plane.load_experiment(exp_id)
    if experiment is None:
        raise click.ClickException(f"Experiment not found: {exp_id}")
    if as_json:
        click.echo(json.dumps(experiment.model_dump(mode="json"), indent=2, ensure_ascii=False))
        return
    click.echo(f"id: {experiment.id}")
    click.echo(f"status: {experiment.status}")
    click.echo(f"variable: {experiment.variable}")
    click.echo(f"hypothesis: {experiment.hypothesis}")


@experiment_group.command(name="create")
@click.option("--id", "experiment_id", default="", help="Explicit experiment id")
@click.option("--variable", required=True, help="Primary variable under test")
@click.option("--hypothesis", required=True, help="Experiment hypothesis")
@click.option("--status", default="draft", help="Initial status")
@click.option("--train-config", default="{}", help="JSON train config")
@click.option("--data-config", default="{}", help="JSON data config")
@click.option("--notes", default="", help="Free-form notes")
@click.pass_context
def create_experiment(ctx, experiment_id, variable, hypothesis, status, train_config, data_config, notes):
    plane = _plane(ctx.obj["experiments_dir"], ctx.obj["config"])
    try:
        experiment = plane.create_experiment(
            CreateExperimentRequest(
                experiment_id=experiment_id,
                variable=variable,
                hypothesis=hypothesis,
                status=status,
                train_config=json.loads(train_config),
                data_config=json.loads(data_config),
                notes=notes,
                context=_context(),
            )
        )
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"Invalid JSON config: {exc}") from exc
    except Exception as exc:
        if hasattr(exc, "errors"):
            raise _schema_error(exc) from exc
        raise
    click.echo(experiment.id)


@experiment_group.command(name="set-status")
@click.argument("exp_id")
@click.argument("status")
@click.pass_context
def set_status(ctx, exp_id, status):
    plane = _plane(ctx.obj["experiments_dir"], ctx.obj["config"])
    if not plane.update_status(exp_id, status, context=_context()):
        raise click.ClickException(f"Experiment not found: {exp_id}")
    click.echo(f"{exp_id} -> {status}")


@control.group(name="prepare")
def prepare_group():
    """Prepare task bundles for inspection and debugging."""


@control.group(name="launch")
def launch_group():
    """One-command launchers backed by versioned task config files."""


@prepare_group.command(name="train")
@click.argument("exp_id")
@click.argument("dataset_path")
@click.option("--bundle-dir", default="", help="Output bundle directory")
@click.pass_context
def prepare_train(ctx, exp_id, dataset_path, bundle_dir):
    plane = _plane(ctx.obj["experiments_dir"], ctx.obj["config"])
    context = _context()
    bundle = plane.prepare_task(
        TaskSubmission(
            experiment_id=exp_id,
            task_type="training",
            task_request=_build_training_spec(plane, exp_id, dataset_path).model_dump(mode="json"),
            template_id="",
            bundle_dir=bundle_dir or None,
            context=context,
        )
    )
    _update_training_lifecycle(plane, exp_id, TrainingLifecycleState.PREPARED, context=context, action="prepare_training_bundle")
    click.echo(str(bundle.path))


@launch_group.command(name="train")
@click.option("--config", "config_path", required=True, type=click.Path(exists=True, dir_okay=False), help="Training launch config YAML")
@click.pass_context
def launch_train(ctx, config_path):
    plane = _plane(ctx.obj["experiments_dir"], ctx.obj["config"])
    try:
        result = launch_training_from_path(plane, config_path, orbit_config=ctx.obj["config"])
    except Exception as exc:
        if hasattr(exc, "errors"):
            raise _schema_error(exc) from exc
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))


@launch_group.command(name="vg-sopd")
@click.option("--config", "config_path", required=True, type=click.Path(exists=True, dir_okay=False), help="VG-SOPD launch config YAML")
@click.pass_context
def launch_vg_sopd(ctx, config_path):
    plane = _plane(ctx.obj["experiments_dir"], ctx.obj["config"])
    try:
        result = launch_vg_sopd_from_path(plane, config_path, orbit_config=ctx.obj["config"])
    except Exception as exc:
        if hasattr(exc, "errors"):
            raise _schema_error(exc) from exc
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))


@prepare_group.command(name="eval")
@click.argument("exp_id")
@click.option("--model", required=True, help="Model path or identifier")
@click.option("--envs", required=True, help="Comma-separated environments")
@click.option("--samples", default=100, type=int)
@click.option("--base-url", default="http://172.17.0.1:30000/v1")
@click.option("--concurrency", default=5, type=int)
@click.option("--seed", default=42, type=int)
@click.option("--affinetes-dir", default="/root/affinetes")
@click.option("--api-key", default="")
@click.option("--skip-build/--build", default=True)
@click.option("--bundle-dir", default="", help="Output bundle directory")
@click.pass_context
def prepare_eval(ctx, exp_id, model, envs, samples, base_url, concurrency, seed, affinetes_dir, api_key, skip_build, bundle_dir):
    plane = _plane(ctx.obj["experiments_dir"], ctx.obj["config"])
    bundle = plane.prepare_task(
        TaskSubmission(
            experiment_id=exp_id,
            task_type="evaluation",
            task_request=EvalTaskSpec(
                model=model,
                environments=tuple(env.strip() for env in envs.split(",") if env.strip()),
                samples=samples,
                base_url=base_url,
                concurrency=concurrency,
                seed=seed,
                affinetes_dir=affinetes_dir,
                api_key=api_key,
                skip_build=skip_build,
            ).model_dump(mode="json"),
            template_id="",
            bundle_dir=bundle_dir or None,
            context=_context(),
        )
    )
    click.echo(str(bundle.path))


@prepare_group.command(name="collect")
@click.argument("exp_id")
@click.option("--env", "env_name", required=True, type=click.Choice(["GAME", "NAVWORLD", "SWE-INFINITE", "LIVEWEB", "MEMORYGYM"]))
@click.option("-n", "--num", default=10, type=int)
@click.option("-o", "--output-filename", default="", help="Staging output filename")
@click.option("--hf-repo", default="", help="HF dataset repo override")
@click.option("--source", default="", help="Canonical source label")
@click.option("--model", default="qwen3-max")
@click.option("--start-id", default=0, type=int)
@click.option("--concurrency", default=3, type=int)
@click.option("--type", "problem_type", default=None)
@click.option("--phase1", is_flag=True)
@click.option("--seeds", default="1-10", help="LIVEWEB seed range")
@click.option("--subtasks", default="1", help="LIVEWEB subtasks")
@click.option("--plugins", default="openmeteo", help="LIVEWEB plugins")
@click.option("--cache-dir", default="", help="LIVEWEB cache dir")
@click.option("--timeout", default=240, type=int, help="LIVEWEB timeout seconds")
@click.option("--game", "game_name", default=None)
@click.option("--all-games", is_flag=True)
@click.option("--attempt-multiplier", default=4, type=int)
@click.option("--generator-source", default="default", type=click.Choice(["default", "policy_model"]))
@click.option("--template", "templates", multiple=True)
@click.option("--tier", default="lite", type=click.Choice(["lite", "standard", "hard", "multi"]))
@click.option("--tier-mix", is_flag=True)
@click.option("-j", "--jobs", default=1, type=int)
@click.option("--split-target", default=5000, type=int)
@click.option("--balance/--no-balance", default=True)
@click.option("--shuffle-seed", default=42, type=int)
@click.option("--machine", default="", help="SWE machine selector")
@click.option("--bundle-dir", default="", help="Output bundle directory")
@click.pass_context
def prepare_collect(ctx, exp_id, env_name, num, output_filename, hf_repo, source, model, start_id, concurrency, problem_type, phase1, seeds, subtasks, plugins, cache_dir, timeout, game_name, all_games, attempt_multiplier, generator_source, templates, tier, tier_mix, jobs, split_target, balance, shuffle_seed, machine, bundle_dir):
    plane = _plane(ctx.obj["experiments_dir"], ctx.obj["config"])
    default_output = {
        "NAVWORLD": "navworld_synthetic.jsonl",
        "LIVEWEB": "liveweb.jsonl",
        "GAME": "game.jsonl",
        "MEMORYGYM": "memorygym.jsonl",
        "SWE-INFINITE": "swe_infinite.jsonl",
    }[env_name]
    bundle = plane.prepare_task(
        TaskSubmission(
            experiment_id=exp_id,
            task_type="collection",
            task_request=_build_collect_spec(
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
            ).model_dump(mode="json"),
            template_id="",
            bundle_dir=bundle_dir or None,
            context=_context(),
        )
    )
    click.echo(str(bundle.path))


@control.group(name="submit")
def submit_group():
    """Submit tasks through execution templates."""


@submit_group.command(name="train")
@click.argument("exp_id")
@click.argument("dataset_path")
@click.option("--template", "template_id", required=True, help="Execution template id")
@click.option("--bundle-dir", default="", help="Output bundle directory")
@click.option("--target", default="", help="Target override for remote placements")
@click.option("--image", default="", help="Execution image override")
@click.option("--gpu-type", default="", help="Requested GPU type")
@click.option("--gpu-count", default=1, type=int, help="Requested GPU count")
@click.option("--cpu-count", default=0, type=int, help="Requested CPU count")
@click.option("--memory-gb", default=0, type=int, help="Requested memory in GB")
@click.option("--foreground/--detach", default=False)
@click.pass_context
def submit_train(ctx, exp_id, dataset_path, template_id, bundle_dir, target, image, gpu_type, gpu_count, cpu_count, memory_gb, foreground):
    plane = _plane(ctx.obj["experiments_dir"], ctx.obj["config"])
    context = _context()
    handle = plane.submit_task(
        TaskSubmission(
            experiment_id=exp_id,
            task_type="training",
            task_request=_build_training_spec(plane, exp_id, dataset_path).model_dump(mode="json"),
            template_id=template_id,
            overrides=_execution_overrides(target, image, gpu_type, gpu_count, cpu_count, memory_gb, foreground),
            bundle_dir=bundle_dir or None,
            context=context,
        )
    )
    _update_training_lifecycle(plane, exp_id, TrainingLifecycleState.RUNNING, context=context, action="submit_training")
    click.echo(json.dumps({"runtime": handle.runtime_kind, "run_id": handle.run_id, "target": handle.target_id}, indent=2))


@submit_group.command(name="eval")
@click.argument("exp_id")
@click.option("--template", "template_id", required=True, help="Execution template id")
@click.option("--model", required=True, help="Model path or identifier")
@click.option("--envs", required=True, help="Comma-separated environments")
@click.option("--samples", default=100, type=int)
@click.option("--base-url", default="http://172.17.0.1:30000/v1")
@click.option("--concurrency", default=5, type=int)
@click.option("--seed", default=42, type=int)
@click.option("--affinetes-dir", default="/root/affinetes")
@click.option("--api-key", default="")
@click.option("--skip-build/--build", default=True)
@click.option("--bundle-dir", default="", help="Output bundle directory")
@click.option("--target", default="", help="Target override for remote placements")
@click.option("--image", default="", help="Execution image override")
@click.option("--gpu-type", default="", help="Requested GPU type")
@click.option("--gpu-count", default=1, type=int)
@click.option("--cpu-count", default=0, type=int)
@click.option("--memory-gb", default=0, type=int)
@click.option("--foreground/--detach", default=False)
@click.pass_context
def submit_eval(ctx, exp_id, template_id, model, envs, samples, base_url, concurrency, seed, affinetes_dir, api_key, skip_build, bundle_dir, target, image, gpu_type, gpu_count, cpu_count, memory_gb, foreground):
    plane = _plane(ctx.obj["experiments_dir"], ctx.obj["config"])
    handle = plane.submit_task(
        TaskSubmission(
            experiment_id=exp_id,
            task_type="evaluation",
            task_request=EvalTaskSpec(
                model=model,
                environments=tuple(env.strip() for env in envs.split(",") if env.strip()),
                samples=samples,
                base_url=base_url,
                concurrency=concurrency,
                seed=seed,
                affinetes_dir=affinetes_dir,
                api_key=api_key,
                skip_build=skip_build,
            ).model_dump(mode="json"),
            template_id=template_id,
            overrides=_execution_overrides(target, image, gpu_type, gpu_count, cpu_count, memory_gb, foreground),
            bundle_dir=bundle_dir or None,
            context=_context(),
        )
    )
    click.echo(json.dumps({"runtime": handle.runtime_kind, "run_id": handle.run_id, "target": handle.target_id}, indent=2))


@submit_group.command(name="collect")
@click.argument("exp_id")
@click.option("--template", "template_id", required=True, help="Execution template id")
@click.option("--env", "env_name", required=True, type=click.Choice(["GAME", "NAVWORLD", "SWE-INFINITE", "LIVEWEB", "MEMORYGYM"]))
@click.option("-n", "--num", default=10, type=int)
@click.option("-o", "--output-filename", default="", help="Staging output filename")
@click.option("--hf-repo", default="", help="HF dataset repo override")
@click.option("--source", default="", help="Canonical source label")
@click.option("--model", default="qwen3-max")
@click.option("--start-id", default=0, type=int)
@click.option("--concurrency", default=3, type=int)
@click.option("--type", "problem_type", default=None)
@click.option("--phase1", is_flag=True)
@click.option("--seeds", default="1-10", help="LIVEWEB seed range")
@click.option("--subtasks", default="1", help="LIVEWEB subtasks")
@click.option("--plugins", default="openmeteo", help="LIVEWEB plugins")
@click.option("--cache-dir", default="", help="LIVEWEB cache dir")
@click.option("--timeout", default=240, type=int, help="LIVEWEB timeout seconds")
@click.option("--game", "game_name", default=None)
@click.option("--all-games", is_flag=True)
@click.option("--attempt-multiplier", default=4, type=int)
@click.option("--generator-source", default="default", type=click.Choice(["default", "policy_model"]))
@click.option("--template-name", "templates", multiple=True)
@click.option("--tier", default="lite", type=click.Choice(["lite", "standard", "hard", "multi"]))
@click.option("--tier-mix", is_flag=True)
@click.option("-j", "--jobs", default=1, type=int)
@click.option("--split-target", default=5000, type=int)
@click.option("--balance/--no-balance", default=True)
@click.option("--shuffle-seed", default=42, type=int)
@click.option("--machine", default="", help="SWE machine selector")
@click.option("--bundle-dir", default="", help="Output bundle directory")
@click.option("--target", default="", help="Target override for remote placements")
@click.option("--image", default="", help="Execution image override")
@click.option("--gpu-type", default="", help="Requested GPU type")
@click.option("--gpu-count", default=1, type=int)
@click.option("--cpu-count", default=0, type=int)
@click.option("--memory-gb", default=0, type=int)
@click.option("--foreground/--detach", default=False)
@click.pass_context
def submit_collect(ctx, exp_id, template_id, env_name, num, output_filename, hf_repo, source, model, start_id, concurrency, problem_type, phase1, seeds, subtasks, plugins, cache_dir, timeout, game_name, all_games, attempt_multiplier, generator_source, templates, tier, tier_mix, jobs, split_target, balance, shuffle_seed, machine, bundle_dir, target, image, gpu_type, gpu_count, cpu_count, memory_gb, foreground):
    plane = _plane(ctx.obj["experiments_dir"], ctx.obj["config"])
    default_output = {
        "NAVWORLD": "navworld_synthetic.jsonl",
        "LIVEWEB": "liveweb.jsonl",
        "GAME": "game.jsonl",
        "MEMORYGYM": "memorygym.jsonl",
        "SWE-INFINITE": "swe_infinite.jsonl",
    }[env_name]
    handle = plane.submit_task(
        TaskSubmission(
            experiment_id=exp_id,
            task_type="collection",
            task_request=_build_collect_spec(
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
            ).model_dump(mode="json"),
            template_id=template_id,
            overrides=_execution_overrides(target, image, gpu_type, gpu_count, cpu_count, memory_gb, foreground),
            bundle_dir=bundle_dir or None,
            context=_context(),
        )
    )
    click.echo(json.dumps({"runtime": handle.runtime_kind, "run_id": handle.run_id, "target": handle.target_id}, indent=2))


@control.group(name="run")
def run_group():
    """Inspect and manage submitted runs."""


@run_group.command(name="status")
@click.argument("exp_id")
@click.argument("task_name", type=click.Choice(["train", "eval", "collect"]))
@click.option("--run-key", default="", help="Explicit recorded stage key")
@click.pass_context
def run_status(ctx, exp_id, task_name, run_key):
    plane = _plane(ctx.obj["experiments_dir"], ctx.obj["config"])
    status = plane.refresh_run_status(RunQuery(experiment_id=exp_id, run_kind=_job_kind(task_name), run_key=run_key, context=_context()))
    if task_name == "train" and status.state in {RunState.SUCCEEDED, RunState.FAILED, RunState.TERMINATED}:
        _update_training_lifecycle(
            plane,
            exp_id,
            {
                RunState.SUCCEEDED: TrainingLifecycleState.COMPLETED,
                RunState.FAILED: TrainingLifecycleState.FAILED,
                RunState.TERMINATED: TrainingLifecycleState.TERMINATED,
            }[status.state],
            context=_context(),
            action="refresh_run_status_training_state",
        )
    click.echo(json.dumps({"runtime": status.runtime_kind, "run_id": status.run_id, "state": status.state.value, "detail": status.detail, "metadata": status.metadata}, indent=2, ensure_ascii=False))


@run_group.command(name="logs")
@click.argument("exp_id")
@click.argument("task_name", type=click.Choice(["train", "eval", "collect"]))
@click.option("--run-key", default="", help="Explicit recorded stage key")
@click.option("--tail", default=100, type=int)
@click.pass_context
def run_logs(ctx, exp_id, task_name, run_key, tail):
    plane = _plane(ctx.obj["experiments_dir"], ctx.obj["config"])
    output = plane.read_run_logs(RunLogsQuery(experiment_id=exp_id, run_kind=_job_kind(task_name), run_key=run_key, tail=tail, context=_context()))
    if output:
        click.echo(output)


@run_group.command(name="collect")
@click.argument("exp_id")
@click.argument("task_name", type=click.Choice(["train", "eval", "collect"]))
@click.option("--run-key", default="", help="Explicit recorded stage key")
@click.pass_context
def collect_run(ctx, exp_id, task_name, run_key):
    plane = _plane(ctx.obj["experiments_dir"], ctx.obj["config"])
    manifest = plane.collect_run_artifacts(RunQuery(experiment_id=exp_id, run_kind=_job_kind(task_name), run_key=run_key, context=_context()))
    click.echo(json.dumps({"logs": manifest.logs, "artifacts": manifest.artifacts, "metadata": manifest.metadata}, indent=2, ensure_ascii=False))


@run_group.command(name="terminate")
@click.argument("exp_id")
@click.argument("task_name", type=click.Choice(["train", "eval", "collect"]))
@click.option("--run-key", default="", help="Explicit recorded stage key")
@click.pass_context
def terminate_run(ctx, exp_id, task_name, run_key):
    plane = _plane(ctx.obj["experiments_dir"], ctx.obj["config"])
    context = _context()
    plane.terminate_run(RunQuery(experiment_id=exp_id, run_kind=_job_kind(task_name), run_key=run_key, context=context))
    if task_name == "train":
        _update_training_lifecycle(plane, exp_id, TrainingLifecycleState.TERMINATED, context=context, action="terminate_training_run")
    click.echo(f"{exp_id}:{task_name} terminated")
