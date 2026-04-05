"""Config-driven VG-SOPD workflow launcher."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from orbit.config import OrbitConfig
from orbit.core.control.service import CoreControlService
from orbit.core.contracts.experiments import CreateExperimentRequest, RunQuery
from orbit.core.contracts.execution import ArtifactManifest, JobKind, RunState
from orbit.core.contracts.tasks import TaskSubmission
from orbit.core.contracts.templates import ExecutionOverrides
from orbit.core.experiments.models import Experiment, TrainingLifecycleState
from orbit.foundation.contracts import TrainingSpec
from orbit.foundation.schema import RequestContext
from orbit.remote_ops.targon_rental_service import provision_targon_rental_ssh
from orbit.tasks.evaluation.specs import EvalTaskSpec
from orbit.tasks.training.launch_config import (
    HuggingFaceDatasetSource,
    LocalDatasetSource,
    ProvisionTargonSshRentalTarget,
    RegisteredMachineTarget,
)
from orbit.tasks.vg_sopd.data_utils import write_json
from orbit.tasks.vg_sopd.specs import (
    ArtifactLineage,
    CompileTaskSpec,
    FrontierTaskSpec,
    GuardrailEvalSpec,
    IterationReport,
    RelabelTaskSpec,
    StageExecutionSpec,
    StageTrainingSpec,
    VGSopdLaunchConfig,
    load_vg_sopd_launch_config,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
TERMINAL_STATES = {RunState.SUCCEEDED, RunState.FAILED, RunState.TERMINATED}


def _require_env_vars(keys: tuple[str, ...]) -> None:
    missing = [key for key in keys if not os.environ.get(key, "")]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")


def _count_jsonl_rows(dataset_path: str) -> int:
    total = 0
    with open(dataset_path, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                total += 1
    return total


def _resolve_dataset_path(source, orbit_config: OrbitConfig) -> str:
    if isinstance(source, LocalDatasetSource):
        dataset_path = str(Path(source.path).expanduser().resolve())
        if not Path(dataset_path).exists():
            raise ValueError(f"Dataset file not found: {dataset_path}")
        return dataset_path
    if isinstance(source, HuggingFaceDatasetSource):
        try:
            from huggingface_hub import hf_hub_download
        except ImportError as exc:
            raise RuntimeError("huggingface_hub is required for hf_dataset_file configs") from exc
        return hf_hub_download(
            repo_id=source.repo_id,
            filename=source.filename,
            repo_type="dataset",
            revision=source.revision,
            token=orbit_config.hf_token or None,
        )
    raise TypeError(f"Unsupported dataset source: {type(source)!r}")


def _resolve_target_name(execution: StageExecutionSpec, orbit_config: OrbitConfig, cache: dict[str, dict]) -> tuple[str, dict | None]:
    target = execution.target
    if target is None:
        return "", None
    cache_key = json.dumps(target.model_dump(mode="json"), sort_keys=True)
    if cache_key in cache:
        payload = cache[cache_key]
        if isinstance(target, RegisteredMachineTarget):
            return target.machine_name, payload
        if isinstance(target, ProvisionTargonSshRentalTarget):
            return target.machine_name, payload
    if isinstance(target, RegisteredMachineTarget):
        cache[cache_key] = {}
        return target.machine_name, None
    if isinstance(target, ProvisionTargonSshRentalTarget):
        payload = provision_targon_rental_ssh(
            orbit_config,
            name=target.workload_name,
            resource=target.resource,
            image=target.image,
            project_id=target.project_id,
            ssh_key_uid=target.ssh_key_uid,
            public_key=target.public_key,
            ssh_port=target.ssh_port,
            machine_name=target.machine_name,
            use_ssh_daemon=target.use_ssh_daemon,
            wait=target.wait,
            timeout_seconds=target.timeout_seconds,
            poll_seconds=target.poll_seconds,
        )
        cache[cache_key] = payload
        return target.machine_name, payload
    raise TypeError(f"Unsupported execution target: {type(target)!r}")


def _stage_overrides(execution: StageExecutionSpec, orbit_config: OrbitConfig, cache: dict[str, dict]) -> tuple[ExecutionOverrides, dict | None]:
    target_name, provision_payload = _resolve_target_name(execution, orbit_config, cache)
    return (
        ExecutionOverrides(
            image=execution.image,
            target=target_name,
            detach=execution.detach,
            resources=execution.resources,
            runtime_env=execution.runtime_env,
        ),
        provision_payload,
    )


def _bundle_dir(output_root: Path, execution: StageExecutionSpec, run_key: str) -> str:
    if execution.bundle_dir:
        return execution.bundle_dir
    return str(output_root / "bundles" / run_key.replace(".", "_"))


def _update_experiment_status(plane: CoreControlService, experiment_id: str, status: TrainingLifecycleState, *, action: str) -> None:
    experiment = plane.load_experiment(experiment_id)
    if experiment is None:
        return
    experiment.status = status
    plane.save_experiment(experiment, context=RequestContext(actor="cli", source="cli.control.launch.vg_sopd"), action=action)


def _record_extra(plane: CoreControlService, experiment_id: str, key: str, value) -> None:
    experiment = plane.load_experiment(experiment_id)
    if experiment is None:
        return
    extra = dict(experiment.results.extra)
    extra[key] = value
    experiment.results.extra = extra
    plane.save_experiment(experiment, context=RequestContext(actor="cli", source="cli.control.launch.vg_sopd"), action=f"record_{key}")


def _record_iteration_report(plane: CoreControlService, experiment_id: str, report: IterationReport) -> None:
    experiment = plane.load_experiment(experiment_id)
    if experiment is None:
        return
    extra = dict(experiment.results.extra)
    reports = dict(extra.get("vg_sopd_iteration_reports", {}))
    reports[f"iter_{report.iteration_index:02d}"] = report.model_dump(mode="json")
    extra["vg_sopd_iteration_reports"] = reports
    experiment.results.extra = extra
    plane.save_experiment(experiment, context=RequestContext(actor="cli", source="cli.control.launch.vg_sopd"), action="record_vg_iteration_report")


def _wait_for_stage(plane: CoreControlService, *, experiment_id: str, run_kind: JobKind, run_key: str, execution: StageExecutionSpec) -> RunState:
    deadline = time.time() + execution.timeout_seconds
    last_state = RunState.SUBMITTED
    while time.time() < deadline:
        status = plane.refresh_run_status(
            RunQuery(
                experiment_id=experiment_id,
                run_kind=run_kind,
                run_key=run_key,
                context=RequestContext(actor="cli", source="cli.control.launch.vg_sopd"),
            )
        )
        last_state = status.state
        if status.state in TERMINAL_STATES:
            return status.state
        time.sleep(execution.poll_interval_seconds)
    raise TimeoutError(f"Timed out waiting for stage {run_key}; last state={last_state.value}")


def _collect_manifest(plane: CoreControlService, *, experiment_id: str, run_kind: JobKind, run_key: str) -> ArtifactManifest:
    return plane.collect_run_artifacts(
        RunQuery(
            experiment_id=experiment_id,
            run_kind=run_kind,
            run_key=run_key,
            context=RequestContext(actor="cli", source="cli.control.launch.vg_sopd"),
        )
    )


def _record_for(plane: CoreControlService, experiment_id: str, run_key: str):
    experiment = plane.load_experiment(experiment_id)
    if experiment is None:
        raise ValueError(f"Experiment not found: {experiment_id}")
    try:
        return experiment.results.task_runs[run_key]
    except KeyError as exc:
        raise ValueError(f"Run key not recorded: {run_key}") from exc


def _artifact_abspath(bundle_path: str, relative_path: str) -> str:
    return str((Path(bundle_path) / relative_path).resolve())


def _artifact_lineage(plane: CoreControlService, experiment_id: str, run_key: str, *, stage: str) -> ArtifactLineage:
    record = _record_for(plane, experiment_id, run_key)
    return ArtifactLineage(
        stage=stage,
        run_key=run_key,
        bundle_path=record.bundle_path,
        artifacts=dict(record.artifacts),
        logs=dict(record.logs),
        metadata={
            "run_id": record.run_id,
            "runtime_kind": record.runtime_kind,
            "status": record.status,
            "template_id": record.template_id,
        },
    )


def _submit_stage(
    plane: CoreControlService,
    *,
    experiment_id: str,
    task_type: str,
    task_request: dict,
    run_key: str,
    run_kind: JobKind,
    execution: StageExecutionSpec,
    orbit_config: OrbitConfig,
    provision_cache: dict[str, dict],
    output_root: Path,
) -> tuple[ArtifactManifest | None, ArtifactLineage, dict | None]:
    overrides, provision_payload = _stage_overrides(execution, orbit_config, provision_cache)
    plane.submit_task(
        TaskSubmission(
            experiment_id=experiment_id,
            task_type=task_type,
            task_request=task_request,
            template_id=execution.template_id,
            run_key=run_key,
            overrides=overrides,
            bundle_dir=_bundle_dir(output_root, execution, run_key),
            context=RequestContext(actor="cli", source="cli.control.launch.vg_sopd"),
        )
    )
    state = _wait_for_stage(plane, experiment_id=experiment_id, run_kind=run_kind, run_key=run_key, execution=execution)
    if state != RunState.SUCCEEDED:
        raise RuntimeError(f"Stage {run_key} finished in state={state.value}")
    manifest = _collect_manifest(plane, experiment_id=experiment_id, run_kind=run_kind, run_key=run_key) if execution.collect_artifacts else None
    return manifest, _artifact_lineage(plane, experiment_id, run_key, stage=task_type), provision_payload


def _build_training_spec(experiment: Experiment, *, model_revision: str, dataset_path: str, stage: StageTrainingSpec) -> TrainingSpec:
    train_config = stage.train_config.model_copy(deep=True)
    train_config.model = model_revision
    return TrainingSpec(
        experiment_id=experiment.id,
        model=model_revision,
        dataset_path=dataset_path,
        train_config=train_config,
        environments=tuple(sorted(experiment.data_config.keys())) if experiment.data_config else tuple(),
        output_dir=train_config.output_dir,
    )


def _training_output_path(plane: CoreControlService, experiment_id: str, run_key: str) -> str:
    record = _record_for(plane, experiment_id, run_key)
    checkpoints = record.artifacts.get("checkpoints", "")
    if checkpoints:
        return _artifact_abspath(record.bundle_path, checkpoints)
    fallback_dir = Path(record.bundle_path) / "artifacts" / "checkpoints"
    if fallback_dir.exists():
        return str(fallback_dir.resolve())
    return str(Path(record.bundle_path).resolve())


def _run_guardrails(spec: GuardrailEvalSpec, *, output_root: Path, experiment_id: str, stage_label: str, model_revision: str) -> dict:
    if not spec.enabled:
        return {}
    output_path = output_root / "guardrails" / f"{stage_label}-{spec.output_filename}"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update(
        {
            "AFFINE_EXPERIMENT_ID": experiment_id,
            "AFFINE_MODEL_REVISION": model_revision,
            "AFFINE_OUTPUT_PATH": str(output_path),
            "AFFINE_PROMPTS_PATH": spec.prompts_path,
            "AFFINE_STAGE_LABEL": stage_label,
        }
    )
    completed = subprocess.run(
        list(spec.command),
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Guardrail command failed for {stage_label}: {completed.stderr.strip()}")
    if output_path.exists():
        return json.loads(output_path.read_text(encoding="utf-8"))
    return {"stdout": completed.stdout.strip(), "stage_label": stage_label}


def _ensure_experiment(plane: CoreControlService, config: VGSopdLaunchConfig, *, frontier_source_path: str) -> Experiment:
    if plane.load_experiment(config.experiment.id) is not None:
        raise ValueError(f"Experiment already exists: {config.experiment.id}")
    primary_train = config.cold_start.training.train_config if config.cold_start.enabled and config.cold_start.training is not None else config.sft_stage.train_config
    count = _count_jsonl_rows(frontier_source_path)
    return plane.create_experiment(
        CreateExperimentRequest(
            experiment_id=config.experiment.id,
            variable=config.experiment.variable,
            hypothesis=config.experiment.hypothesis,
            status=config.experiment.status,
            train_config=primary_train.model_dump(mode="json"),
            data_config={
                env: {
                    "source": "vg_sopd_frontier",
                    "count": count,
                }
                for env in config.environments
            },
            notes=config.experiment.notes,
            context=RequestContext(actor="cli", source="cli.control.launch.vg_sopd"),
        )
    )


def launch_vg_sopd_from_config(
    plane: CoreControlService,
    launch_config: VGSopdLaunchConfig,
    *,
    orbit_config: OrbitConfig | None = None,
    config_path: str = "",
) -> dict:
    orbit_config = orbit_config or OrbitConfig.load()
    _require_env_vars(launch_config.required_env)
    frontier_source_path = _resolve_dataset_path(launch_config.frontier_task_source, orbit_config)
    cold_start_source_path = _resolve_dataset_path(launch_config.cold_start.dataset, orbit_config) if launch_config.cold_start.enabled and launch_config.cold_start.dataset is not None else ""
    output_root = Path(launch_config.output_root).expanduser().resolve() / launch_config.experiment.id
    output_root.mkdir(parents=True, exist_ok=True)
    experiment = _ensure_experiment(plane, launch_config, frontier_source_path=frontier_source_path)
    _record_extra(
        plane,
        experiment.id,
        "vg_sopd_launch",
        {
            "config": launch_config.model_dump(mode="json"),
            "config_path": config_path,
            "frontier_source_path": frontier_source_path,
            "cold_start_source_path": cold_start_source_path,
        },
    )
    _update_experiment_status(plane, experiment.id, TrainingLifecycleState.RUNNING, action="launch_vg_sopd_set_running")
    provision_cache: dict[str, dict] = {}
    provisions: dict[str, dict] = {}
    current_model_revision = launch_config.student_model_revision
    iteration_reports: list[dict] = []
    try:
        guardrail_before = _run_guardrails(launch_config.guardrails, output_root=output_root, experiment_id=experiment.id, stage_label="pretrain", model_revision=current_model_revision)

        if launch_config.cold_start.enabled and launch_config.cold_start.training is not None and cold_start_source_path:
            cold_stage = launch_config.cold_start.training
            cold_run_key = "cold_start.sft"
            manifest, _, provision = _submit_stage(
                plane,
                experiment_id=experiment.id,
                task_type="training",
                task_request=_build_training_spec(experiment, model_revision=current_model_revision, dataset_path=cold_start_source_path, stage=cold_stage).model_dump(mode="json"),
                run_key=cold_run_key,
                run_kind=JobKind.TRAIN,
                execution=cold_stage.execution,
                orbit_config=orbit_config,
                provision_cache=provision_cache,
                output_root=output_root,
            )
            if provision is not None:
                provisions[cold_run_key] = provision
            if manifest is not None:
                current_model_revision = _training_output_path(plane, experiment.id, cold_run_key)

        for iteration_index in range(1, launch_config.iteration_count + 1):
            artifact_lineage: list[ArtifactLineage] = []
            model_revision_in = current_model_revision
            frontier_run_key = f"iter{iteration_index:02d}.frontier"
            _, lineage, provision = _submit_stage(
                plane,
                experiment_id=experiment.id,
                task_type="vg_frontier",
                task_request=FrontierTaskSpec(
                    experiment_id=experiment.id,
                    iteration_index=iteration_index,
                    student_model_revision=current_model_revision,
                    task_source_path=frontier_source_path,
                    environments=launch_config.environments,
                    rollout=launch_config.frontier,
                ).model_dump(mode="json"),
                run_key=frontier_run_key,
                run_kind=JobKind.COLLECT,
                execution=launch_config.frontier.execution,
                orbit_config=orbit_config,
                provision_cache=provision_cache,
                output_root=output_root,
            )
            artifact_lineage.append(lineage)
            if provision is not None:
                provisions[frontier_run_key] = provision
            frontier_record = _record_for(plane, experiment.id, frontier_run_key)
            frontier_traces_path = _artifact_abspath(frontier_record.bundle_path, frontier_record.artifacts["raw_rollouts.jsonl"])

            relabel_run_key = f"iter{iteration_index:02d}.relabel"
            _, lineage, provision = _submit_stage(
                plane,
                experiment_id=experiment.id,
                task_type="vg_relabel",
                task_request=RelabelTaskSpec(
                    experiment_id=experiment.id,
                    iteration_index=iteration_index,
                    model_revision=current_model_revision,
                    frontier_traces_path=frontier_traces_path,
                    environments=launch_config.environments,
                    teacher_policy=launch_config.teacher_policy,
                    relabel=launch_config.relabel,
                ).model_dump(mode="json"),
                run_key=relabel_run_key,
                run_kind=JobKind.COLLECT,
                execution=launch_config.relabel.execution,
                orbit_config=orbit_config,
                provision_cache=provision_cache,
                output_root=output_root,
            )
            artifact_lineage.append(lineage)
            if provision is not None:
                provisions[relabel_run_key] = provision
            relabel_record = _record_for(plane, experiment.id, relabel_run_key)
            relabelled_path = _artifact_abspath(relabel_record.bundle_path, relabel_record.artifacts["relabelled_traces.jsonl"])
            teacher_augmented_path = _artifact_abspath(relabel_record.bundle_path, relabel_record.artifacts["teacher_augmented_traces.jsonl"])

            compile_run_key = f"iter{iteration_index:02d}.compile"
            _, lineage, provision = _submit_stage(
                plane,
                experiment_id=experiment.id,
                task_type="vg_compile",
                task_request=CompileTaskSpec(
                    experiment_id=experiment.id,
                    iteration_index=iteration_index,
                    model_revision=current_model_revision,
                    relabelled_traces_path=relabelled_path,
                    teacher_augmented_traces_path=teacher_augmented_path,
                    environments=launch_config.environments,
                    compile=launch_config.compile,
                ).model_dump(mode="json"),
                run_key=compile_run_key,
                run_kind=JobKind.COLLECT,
                execution=launch_config.compile.execution,
                orbit_config=orbit_config,
                provision_cache=provision_cache,
                output_root=output_root,
            )
            artifact_lineage.append(lineage)
            if provision is not None:
                provisions[compile_run_key] = provision
            compile_record = _record_for(plane, experiment.id, compile_run_key)
            compiled_sft_path = _artifact_abspath(compile_record.bundle_path, compile_record.artifacts["compiled_sft.jsonl"])
            compiled_preference_path = _artifact_abspath(compile_record.bundle_path, compile_record.artifacts["compiled_preference.jsonl"])
            compiled_gkd_path = ""
            if "compiled_gkd.jsonl" in compile_record.artifacts:
                compiled_gkd_path = _artifact_abspath(compile_record.bundle_path, compile_record.artifacts["compiled_gkd.jsonl"])
            stage_metrics = json.loads(Path(_artifact_abspath(compile_record.bundle_path, compile_record.artifacts["iteration_report.json"])).read_text(encoding="utf-8"))

            sft_run_key = f"iter{iteration_index:02d}.sft"
            _, lineage, provision = _submit_stage(
                plane,
                experiment_id=experiment.id,
                task_type="training",
                task_request=_build_training_spec(experiment, model_revision=current_model_revision, dataset_path=compiled_sft_path, stage=launch_config.sft_stage).model_dump(mode="json"),
                run_key=sft_run_key,
                run_kind=JobKind.TRAIN,
                execution=launch_config.sft_stage.execution,
                orbit_config=orbit_config,
                provision_cache=provision_cache,
                output_root=output_root,
            )
            artifact_lineage.append(lineage)
            if provision is not None:
                provisions[sft_run_key] = provision
            current_model_revision = _training_output_path(plane, experiment.id, sft_run_key)

            preference_run_key = f"iter{iteration_index:02d}.preference"
            _, lineage, provision = _submit_stage(
                plane,
                experiment_id=experiment.id,
                task_type="training",
                task_request=_build_training_spec(experiment, model_revision=current_model_revision, dataset_path=compiled_preference_path, stage=launch_config.preference_stage).model_dump(mode="json"),
                run_key=preference_run_key,
                run_kind=JobKind.TRAIN,
                execution=launch_config.preference_stage.execution,
                orbit_config=orbit_config,
                provision_cache=provision_cache,
                output_root=output_root,
            )
            artifact_lineage.append(lineage)
            if provision is not None:
                provisions[preference_run_key] = provision
            current_model_revision = _training_output_path(plane, experiment.id, preference_run_key)

            if launch_config.gkd_stage is not None and launch_config.gkd_stage.enabled and compiled_gkd_path and Path(compiled_gkd_path).exists() and Path(compiled_gkd_path).stat().st_size > 0:
                gkd_run_key = f"iter{iteration_index:02d}.gkd"
                _, lineage, provision = _submit_stage(
                    plane,
                    experiment_id=experiment.id,
                    task_type="training",
                    task_request=_build_training_spec(experiment, model_revision=current_model_revision, dataset_path=compiled_gkd_path, stage=launch_config.gkd_stage).model_dump(mode="json"),
                    run_key=gkd_run_key,
                    run_kind=JobKind.TRAIN,
                    execution=launch_config.gkd_stage.execution,
                    orbit_config=orbit_config,
                    provision_cache=provision_cache,
                    output_root=output_root,
                )
                artifact_lineage.append(lineage)
                if provision is not None:
                    provisions[gkd_run_key] = provision
                current_model_revision = _training_output_path(plane, experiment.id, gkd_run_key)

            if launch_config.evaluation.enabled and launch_config.evaluation.spec is not None and launch_config.evaluation.execution is not None:
                eval_run_key = f"iter{iteration_index:02d}.eval"
                eval_spec = EvalTaskSpec.model_validate(launch_config.evaluation.spec.model_dump(mode="json"))
                eval_spec = eval_spec.model_copy(update={"model": current_model_revision})
                _, lineage, provision = _submit_stage(
                    plane,
                    experiment_id=experiment.id,
                    task_type="evaluation",
                    task_request=eval_spec.model_dump(mode="json"),
                    run_key=eval_run_key,
                    run_kind=JobKind.EVAL,
                    execution=launch_config.evaluation.execution,
                    orbit_config=orbit_config,
                    provision_cache=provision_cache,
                    output_root=output_root,
                )
                artifact_lineage.append(lineage)
                if provision is not None:
                    provisions[eval_run_key] = provision

            guardrail_after = _run_guardrails(
                launch_config.guardrails,
                output_root=output_root,
                experiment_id=experiment.id,
                stage_label=f"iter{iteration_index:02d}",
                model_revision=current_model_revision,
            )
            report = IterationReport(
                iteration_index=iteration_index,
                model_revision_in=model_revision_in,
                model_revision_out=current_model_revision,
                stage_metrics=stage_metrics,
                artifacts=tuple(artifact_lineage),
                guardrail_before=guardrail_before,
                guardrail_after=guardrail_after,
            )
            report_path = output_root / "reports" / f"iter_{iteration_index:02d}.json"
            write_json(report_path, report.model_dump(mode="json"))
            _record_iteration_report(plane, experiment.id, report)
            iteration_reports.append(report.model_dump(mode="json"))
            guardrail_before = guardrail_after
    except Exception:
        _update_experiment_status(plane, experiment.id, TrainingLifecycleState.FAILED, action="launch_vg_sopd_failed")
        raise

    _update_experiment_status(plane, experiment.id, TrainingLifecycleState.COMPLETED, action="launch_vg_sopd_completed")
    result = {
        "experiment_id": experiment.id,
        "current_model_revision": current_model_revision,
        "iteration_reports": iteration_reports,
        "output_root": str(output_root),
        "provision": provisions,
    }
    _record_extra(plane, experiment.id, "vg_sopd_result", result)
    return result


def launch_vg_sopd_from_path(
    plane: CoreControlService,
    config_path: str,
    *,
    orbit_config: OrbitConfig | None = None,
) -> dict:
    launch_config = load_vg_sopd_launch_config(config_path)
    return launch_vg_sopd_from_config(plane, launch_config, orbit_config=orbit_config, config_path=config_path)


__all__ = ["launch_vg_sopd_from_config", "launch_vg_sopd_from_path"]
