"""Control-plane CLI family."""

from __future__ import annotations

import json

import click

from forge.control import ControlPlane, ExperimentStore
from forge.data.collect_service import build_collect_spec
from forge.control.contracts import (
    ControlSubmissionTarget,
    CreateExperimentRequest,
    RenderCollectRequest,
    RenderEvalRequest,
    RenderTrainRequest,
    RunLogsQuery,
    RunQuery,
    SubmitCollectRequest,
    SubmitEvalRequest,
    SubmitTrainRequest,
)
from forge.execution import TargonRuntime
from forge.execution.contracts import CollectTaskSpec, EvalTaskSpec, JobKind, TargonProfile, TargonTarget
from forge.config import ForgeConfig
from forge.foundation.schema import RequestContext, SchemaErrorResponse, ValidationIssue

DEFAULT_EXEC_IMAGE = ForgeConfig.load().default_exec_image

_build_collect_spec = build_collect_spec


def _runtime_for(config, runtime_name: str):
    if runtime_name == "targon":
        return TargonRuntime(config)
    raise click.ClickException(f"Unknown runtime: {runtime_name}")


def _plane(experiments_dir: str, config) -> ControlPlane:
    return ControlPlane(
        experiments=ExperimentStore(experiments_dir),
        runtime_factory=lambda runtime_name: _runtime_for(config, runtime_name),
    )


def _job_kind(task_name: str) -> JobKind:
    return JobKind(task_name)


def _context(source: str = "cli.control") -> RequestContext:
    return RequestContext(actor="cli", source=source)


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


def _submission_target(runtime_name: str, target: str, profile: str, image: str, gpu_type: str):
    if runtime_name != "targon":
        raise click.ClickException("control plane only supports the remote targon runtime")
    if not target:
        raise click.ClickException("targon rental runtime requires --target pointing to a registered rental machine")
    return ControlSubmissionTarget(
        target=TargonTarget(
            target=target,
            profile=TargonProfile(profile) if profile else TargonProfile.RENTAL,
            image=image or DEFAULT_EXEC_IMAGE,
            gpu_type=gpu_type,
        )
    )

@click.group(name="control")
@click.option("--dir", "experiments_dir", default="experiments", help="Experiments directory")
@click.pass_context
def control(ctx, experiments_dir):
    """Control-plane commands."""
    ctx.ensure_object(dict)
    ctx.obj["experiments_dir"] = experiments_dir


@control.command(name="list")
@click.option("--status", default=None, help="Filter by status")
@click.pass_context
def list_experiments(ctx, status):
    plane = _plane(ctx.obj["experiments_dir"], ctx.obj["config"])
    experiments = plane.list_experiments(status=status)
    for experiment in experiments:
        click.echo(f"{experiment.id}\t{experiment.status}\t{experiment.variable}")


@control.command(name="show")
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


@control.command(name="create")
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
        parsed_train = json.loads(train_config)
        parsed_data = json.loads(data_config)
        experiment = plane.create_experiment(
            CreateExperimentRequest(
                experiment_id=experiment_id,
                variable=variable,
                hypothesis=hypothesis,
                status=status,
                train_config=parsed_train,
                data_config=parsed_data,
                notes=notes,
                context=_context(),
            )
        )
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"Invalid JSON config: {exc}") from exc
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    except Exception as exc:
        if hasattr(exc, "errors"):
            raise _schema_error(exc) from exc
        raise
    click.echo(experiment.id)


@control.command(name="set-status")
@click.argument("exp_id")
@click.argument("status")
@click.pass_context
def set_status(ctx, exp_id, status):
    plane = _plane(ctx.obj["experiments_dir"], ctx.obj["config"])
    if not plane.update_status(exp_id, status, context=_context()):
        raise click.ClickException(f"Experiment not found: {exp_id}")
    click.echo(f"{exp_id} -> {status}")


@control.command(name="render-train")
@click.argument("exp_id")
@click.argument("dataset_path")
@click.option("--bundle-dir", default="", help="Output bundle directory")
@click.pass_context
def render_train(ctx, exp_id, dataset_path, bundle_dir):
    plane = _plane(ctx.obj["experiments_dir"], ctx.obj["config"])
    try:
        bundle = plane.render_training_bundle(
            RenderTrainRequest(
                experiment_id=exp_id,
                dataset_path=dataset_path,
                bundle_dir=bundle_dir or None,
                context=_context(),
            )
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    except Exception as exc:
        if hasattr(exc, "errors"):
            raise _schema_error(exc) from exc
        raise
    click.echo(str(bundle.path))


@control.command(name="render-eval")
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
def render_eval(ctx, exp_id, model, envs, samples, base_url, concurrency, seed, affinetes_dir, api_key, skip_build, bundle_dir):
    plane = _plane(ctx.obj["experiments_dir"], ctx.obj["config"])
    try:
        bundle = plane.render_eval_bundle(
            RenderEvalRequest(
                experiment_id=exp_id,
                spec=EvalTaskSpec(
                    model=model,
                    environments=tuple(env.strip() for env in envs.split(",") if env.strip()),
                    samples=samples,
                    base_url=base_url,
                    concurrency=concurrency,
                    seed=seed,
                    affinetes_dir=affinetes_dir,
                    api_key=api_key,
                    skip_build=skip_build,
                ),
                bundle_dir=bundle_dir or None,
                context=_context(),
            )
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    except Exception as exc:
        if hasattr(exc, "errors"):
            raise _schema_error(exc) from exc
        raise
    click.echo(str(bundle.path))


@control.command(name="render-collect")
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
def render_collect(
    ctx,
    exp_id,
    env_name,
    num,
    output_filename,
    hf_repo,
    source,
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
    templates,
    tier,
    tier_mix,
    jobs,
    split_target,
    balance,
    shuffle_seed,
    machine,
    bundle_dir,
):
    plane = _plane(ctx.obj["experiments_dir"], ctx.obj["config"])
    default_output = {
        "NAVWORLD": "navworld_synthetic.jsonl",
        "LIVEWEB": "liveweb.jsonl",
        "GAME": "game.jsonl",
        "MEMORYGYM": "memorygym.jsonl",
        "SWE-INFINITE": "swe_infinite.jsonl",
    }[env_name]
    try:
        bundle = plane.render_collect_bundle(
            RenderCollectRequest(
                experiment_id=exp_id,
                spec=_build_collect_spec(
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
                    templates=templates,
                    tier=tier,
                    tier_mix=tier_mix,
                    jobs=jobs,
                    split_target=split_target,
                    balance=balance,
                    shuffle_seed=shuffle_seed,
                    machine=machine,
                ),
                bundle_dir=bundle_dir or None,
                context=_context(),
            )
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    except Exception as exc:
        if hasattr(exc, "errors"):
            raise _schema_error(exc) from exc
        raise
    click.echo(str(bundle.path))


@control.command(name="render-collect-navworld")
@click.argument("exp_id")
@click.option("-n", "--num", default=10, type=int)
@click.option("-o", "--output-filename", default="navworld_synthetic.jsonl")
@click.option("--model", default="qwen3-max")
@click.option("--start-id", default=0, type=int)
@click.option("--concurrency", default=3, type=int)
@click.option("--type", "problem_type", default=None)
@click.option("--phase1", is_flag=True)
@click.option("--bundle-dir", default="", help="Output bundle directory")
@click.pass_context
def render_collect_navworld(ctx, exp_id, num, output_filename, model, start_id, concurrency, problem_type, phase1, bundle_dir):
    plane = _plane(ctx.obj["experiments_dir"], ctx.obj["config"])
    try:
        bundle = plane.render_collect_bundle(
            RenderCollectRequest(
                experiment_id=exp_id,
                spec=_build_collect_spec(
                    env_name="NAVWORLD",
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
                    templates=(),
                    tier="lite",
                    tier_mix=False,
                    jobs=1,
                    split_target=5000,
                    balance=True,
                    shuffle_seed=42,
                    machine="",
                ),
                bundle_dir=bundle_dir or None,
                context=_context(),
            )
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    except Exception as exc:
        if hasattr(exc, "errors"):
            raise _schema_error(exc) from exc
        raise
    click.echo(str(bundle.path))


@control.command(name="submit-train")
@click.argument("exp_id")
@click.argument("dataset_path")
@click.option("--runtime", "runtime_name", default="targon", type=click.Choice(["targon"]))
@click.option("--bundle-dir", default="", help="Output bundle directory")
@click.option("--target", required=True, help="Registered Targon rental machine name or host")
@click.option("--profile", default="rental", type=click.Choice(["rental"]), help="Runtime profile")
@click.option("--image", default=DEFAULT_EXEC_IMAGE, help="Runtime image override")
@click.option("--gpu-type", default="", help="Requested GPU type")
@click.pass_context
def submit_train(ctx, exp_id, dataset_path, runtime_name, bundle_dir, target, profile, image, gpu_type):
    plane = _plane(ctx.obj["experiments_dir"], ctx.obj["config"])
    try:
        handle = plane.submit_training(
            SubmitTrainRequest(
                experiment_id=exp_id,
                dataset_path=dataset_path,
                submission_target=_submission_target(runtime_name, target, profile, image, gpu_type),
                bundle_dir=bundle_dir or None,
                context=_context(),
            )
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    except Exception as exc:
        if hasattr(exc, "errors"):
            raise _schema_error(exc) from exc
        raise
    click.echo(json.dumps({
        "runtime": handle.runtime_kind,
        "run_id": handle.run_id,
        "target": handle.target_id,
        "bundle_path": handle.bundle_path,
    }, indent=2, ensure_ascii=False))


@control.command(name="submit-eval")
@click.argument("exp_id")
@click.option("--model", required=True, help="Model path or identifier")
@click.option("--envs", required=True, help="Comma-separated environments")
@click.option("--runtime", "runtime_name", default="targon", type=click.Choice(["targon"]))
@click.option("--samples", default=100, type=int)
@click.option("--base-url", default="http://172.17.0.1:30000/v1")
@click.option("--concurrency", default=5, type=int)
@click.option("--seed", default=42, type=int)
@click.option("--affinetes-dir", default="/root/affinetes")
@click.option("--api-key", default="")
@click.option("--skip-build/--build", default=True)
@click.option("--bundle-dir", default="", help="Output bundle directory")
@click.option("--target", required=True, help="Registered Targon rental machine name or host")
@click.option("--profile", default="rental", type=click.Choice(["rental"]), help="Runtime profile")
@click.option("--image", default=DEFAULT_EXEC_IMAGE, help="Runtime image override")
@click.option("--gpu-type", default="", help="Requested GPU type")
@click.pass_context
def submit_eval(ctx, exp_id, model, envs, runtime_name, samples, base_url, concurrency, seed, affinetes_dir, api_key, skip_build, bundle_dir, target, profile, image, gpu_type):
    plane = _plane(ctx.obj["experiments_dir"], ctx.obj["config"])
    try:
        handle = plane.submit_eval(
            SubmitEvalRequest(
                experiment_id=exp_id,
                spec=EvalTaskSpec(
                    model=model,
                    environments=tuple(env.strip() for env in envs.split(",") if env.strip()),
                    samples=samples,
                    base_url=base_url,
                    concurrency=concurrency,
                    seed=seed,
                    affinetes_dir=affinetes_dir,
                    api_key=api_key,
                    skip_build=skip_build,
                ),
                submission_target=_submission_target(runtime_name, target, profile, image, gpu_type),
                bundle_dir=bundle_dir or None,
                context=_context(),
            )
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    except Exception as exc:
        if hasattr(exc, "errors"):
            raise _schema_error(exc) from exc
        raise
    click.echo(json.dumps({
        "runtime": handle.runtime_kind,
        "run_id": handle.run_id,
        "target": handle.target_id,
        "bundle_path": handle.bundle_path,
    }, indent=2, ensure_ascii=False))


@control.command(name="submit-collect")
@click.argument("exp_id")
@click.option("--env", "env_name", required=True, type=click.Choice(["GAME", "NAVWORLD", "SWE-INFINITE", "LIVEWEB", "MEMORYGYM"]))
@click.option("--runtime", "runtime_name", default="targon", type=click.Choice(["targon"]))
@click.option("-n", "--num", default=10, type=int)
@click.option("-o", "--output-filename", default="", help="Staging output filename")
@click.option("--hf-repo", default="", help="HF dataset repo override")
@click.option("--source", default="", help="Canonical source label")
@click.option("--model", default="qwen3-max")
@click.option("--start-id", default=0, type=int)
@click.option("--concurrency", default=3, type=int)
@click.option("--type", "problem_type", default=None)
@click.option("--phase1", is_flag=True)
@click.option("--seeds", default="1-10")
@click.option("--subtasks", default="1")
@click.option("--plugins", default="openmeteo")
@click.option("--cache-dir", default="")
@click.option("--timeout", default=240, type=int)
@click.option("--game", "game_name", default=None)
@click.option("--all-games", is_flag=True)
@click.option("--attempt-multiplier", default=4, type=int)
@click.option("--template", "templates", multiple=True)
@click.option("--tier", default="lite", type=click.Choice(["lite", "standard", "hard", "multi"]))
@click.option("--tier-mix", is_flag=True)
@click.option("-j", "--jobs", default=1, type=int)
@click.option("--split-target", default=5000, type=int)
@click.option("--balance/--no-balance", default=True)
@click.option("--shuffle-seed", default=42, type=int)
@click.option("--machine", default="", help="SWE machine selector")
@click.option("--bundle-dir", default="", help="Output bundle directory")
@click.option("--target", required=True, help="Registered Targon rental machine name or host")
@click.option("--profile", default="rental", type=click.Choice(["rental"]), help="Runtime profile")
@click.option("--image", default=DEFAULT_EXEC_IMAGE, help="Runtime image override")
@click.option("--gpu-type", default="", help="Requested GPU type")
@click.pass_context
def submit_collect(
    ctx,
    exp_id,
    env_name,
    runtime_name,
    num,
    output_filename,
    hf_repo,
    source,
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
    templates,
    tier,
    tier_mix,
    jobs,
    split_target,
    balance,
    shuffle_seed,
    machine,
    bundle_dir,
    target,
    profile,
    image,
    gpu_type,
):
    plane = _plane(ctx.obj["experiments_dir"], ctx.obj["config"])
    default_output = {
        "NAVWORLD": "navworld_synthetic.jsonl",
        "LIVEWEB": "liveweb.jsonl",
        "GAME": "game.jsonl",
        "MEMORYGYM": "memorygym.jsonl",
        "SWE-INFINITE": "swe_infinite.jsonl",
    }[env_name]
    try:
        handle = plane.submit_collect(
            SubmitCollectRequest(
                experiment_id=exp_id,
                spec=_build_collect_spec(
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
                    templates=templates,
                    tier=tier,
                    tier_mix=tier_mix,
                    jobs=jobs,
                    split_target=split_target,
                    balance=balance,
                    shuffle_seed=shuffle_seed,
                    machine=machine,
                ),
                submission_target=_submission_target(runtime_name, target, profile, image, gpu_type),
                bundle_dir=bundle_dir or None,
                context=_context(),
            )
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    except Exception as exc:
        if hasattr(exc, "errors"):
            raise _schema_error(exc) from exc
        raise
    click.echo(json.dumps({
        "runtime": handle.runtime_kind,
        "run_id": handle.run_id,
        "target": handle.target_id,
        "bundle_path": handle.bundle_path,
    }, indent=2, ensure_ascii=False))


@control.command(name="submit-collect-navworld")
@click.argument("exp_id")
@click.option("--runtime", "runtime_name", default="targon", type=click.Choice(["targon"]))
@click.option("-n", "--num", default=10, type=int)
@click.option("-o", "--output-filename", default="navworld_synthetic.jsonl")
@click.option("--model", default="qwen3-max")
@click.option("--start-id", default=0, type=int)
@click.option("--concurrency", default=3, type=int)
@click.option("--type", "problem_type", default=None)
@click.option("--phase1", is_flag=True)
@click.option("--bundle-dir", default="", help="Output bundle directory")
@click.option("--target", required=True, help="Registered Targon rental machine name or host")
@click.option("--profile", default="rental", type=click.Choice(["rental"]), help="Runtime profile")
@click.option("--image", default=DEFAULT_EXEC_IMAGE, help="Runtime image override")
@click.option("--gpu-type", default="", help="Requested GPU type")
@click.pass_context
def submit_collect_navworld(ctx, exp_id, runtime_name, num, output_filename, model, start_id, concurrency, problem_type, phase1, bundle_dir, target, profile, image, gpu_type):
    plane = _plane(ctx.obj["experiments_dir"], ctx.obj["config"])
    try:
        handle = plane.submit_collect(
            SubmitCollectRequest(
                experiment_id=exp_id,
                spec=_build_collect_spec(
                    env_name="NAVWORLD",
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
                    templates=(),
                    tier="lite",
                    tier_mix=False,
                    jobs=1,
                    split_target=5000,
                    balance=True,
                    shuffle_seed=42,
                    machine="",
                ),
                submission_target=_submission_target(runtime_name, target, profile, image, gpu_type),
                bundle_dir=bundle_dir or None,
                context=_context(),
            )
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    except Exception as exc:
        if hasattr(exc, "errors"):
            raise _schema_error(exc) from exc
        raise
    click.echo(json.dumps({
        "runtime": handle.runtime_kind,
        "run_id": handle.run_id,
        "target": handle.target_id,
        "bundle_path": handle.bundle_path,
    }, indent=2, ensure_ascii=False))


@control.command(name="run-status")
@click.argument("exp_id")
@click.option("--task", "task_name", default="train", type=click.Choice(["train", "eval", "collect"]))
@click.pass_context
def run_status(ctx, exp_id, task_name):
    plane = _plane(ctx.obj["experiments_dir"], ctx.obj["config"])
    try:
        status = plane.refresh_run_status(RunQuery(experiment_id=exp_id, run_kind=_job_kind(task_name), context=_context()))
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps({
        "runtime": status.runtime_kind,
        "run_id": status.run_id,
        "state": status.state.value,
        "detail": status.detail,
        "metadata": status.metadata,
    }, indent=2, ensure_ascii=False))


@control.command(name="run-logs")
@click.argument("exp_id")
@click.option("--task", "task_name", default="train", type=click.Choice(["train", "eval", "collect"]))
@click.option("--tail", default=100, type=int)
@click.pass_context
def run_logs(ctx, exp_id, task_name, tail):
    plane = _plane(ctx.obj["experiments_dir"], ctx.obj["config"])
    try:
        output = plane.read_run_logs(RunLogsQuery(experiment_id=exp_id, run_kind=_job_kind(task_name), tail=tail, context=_context()))
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    if output:
        click.echo(output)


@control.command(name="collect-run")
@click.argument("exp_id")
@click.option("--task", "task_name", default="train", type=click.Choice(["train", "eval", "collect"]))
@click.pass_context
def collect_run(ctx, exp_id, task_name):
    plane = _plane(ctx.obj["experiments_dir"], ctx.obj["config"])
    try:
        manifest = plane.collect_run_artifacts(RunQuery(experiment_id=exp_id, run_kind=_job_kind(task_name), context=_context()))
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps({
        "logs": manifest.logs,
        "artifacts": manifest.artifacts,
        "metadata": manifest.metadata,
    }, indent=2, ensure_ascii=False))


@control.command(name="terminate-run")
@click.argument("exp_id")
@click.option("--task", "task_name", default="train", type=click.Choice(["train", "eval", "collect"]))
@click.pass_context
def terminate_run(ctx, exp_id, task_name):
    plane = _plane(ctx.obj["experiments_dir"], ctx.obj["config"])
    try:
        plane.terminate_run(RunQuery(experiment_id=exp_id, run_kind=_job_kind(task_name), context=_context()))
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Terminated {task_name} run for {exp_id}")
