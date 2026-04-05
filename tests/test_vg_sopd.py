"""Tests for the VG-SOPD workflow, stage logic, and run-key tracking."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from forge.config import ForgeConfig
from forge.core.control.service import CoreControlService
from forge.core.contracts.experiments import CreateExperimentRequest
from forge.core.contracts.execution import (
    ArtifactManifest,
    CollectArtifactsRequest,
    ExecutionRequest,
    RunHandle,
    RunLogsRequest,
    RunState,
    RunStatus,
    RunStatusRequest,
    TerminateRunRequest,
)
from forge.core.experiments import ExperimentStore
from forge.core.templates.registry import ExecutionTemplateRegistry
from forge.core.execution.bundle import JobBundle
from forge.core.contracts.tasks import TaskSubmission
from forge.tasks import build_default_task_registry
from forge.tasks.vg_sopd.compiler import run_compile
from forge.tasks.vg_sopd.relabel import run_relabel
from forge.tasks.vg_sopd.specs import (
    CompileSpec,
    CompileTaskSpec,
    FrontierRolloutSpec,
    FrontierTaskSpec,
    RelabelSpec,
    RelabelTaskSpec,
    StageExecutionSpec,
    TeacherEndpointSpec,
    TeacherPolicySpec,
)
from forge.tasks.vg_sopd.teacher_router import route_teacher
from forge.tasks.vg_sopd.launcher import launch_vg_sopd_from_path


class _WorkflowExecution:
    def __init__(self):
        self._counter = 0

    async def run(self, request: ExecutionRequest):
        self._counter += 1
        bundle = JobBundle(request.bundle_path)
        job = bundle.load_job()
        handle = RunHandle(
            runtime_kind="fake",
            run_id=f"run-{self._counter:03d}",
            target_id=request.placement.target or request.placement.kind.value,
            bundle_path=request.bundle_path,
        )
        bundle.write_run_handle(handle)
        task_type = str(job.metadata.get("task_type", ""))
        if task_type.startswith("vg_"):
            env = os.environ.copy()
            env["BUNDLE_ROOT"] = str(bundle.path.resolve())
            env["PROJECT_ROOT"] = str(Path(__file__).resolve().parents[1])
            env["FORGE_PYTHON"] = sys.executable
            completed = subprocess.run(["bash", str(bundle.entrypoint_path.resolve())], cwd=str(Path(__file__).resolve().parents[1]), env=env, check=False)
            state = RunState.SUCCEEDED if completed.returncode == 0 else RunState.FAILED
            bundle.write_run_status(RunStatus(runtime_kind="fake", run_id=handle.run_id, state=state, detail=task_type))
        elif task_type == "train":
            checkpoint_dir = bundle.artifacts_dir / "checkpoints" / f"checkpoint-{self._counter:03d}"
            checkpoint_dir.mkdir(parents=True, exist_ok=True)
            (checkpoint_dir / "model.txt").write_text("trained\n", encoding="utf-8")
            (bundle.artifacts_dir / "training.log").write_text(f"{job.job_id}\n", encoding="utf-8")
            bundle.write_run_status(RunStatus(runtime_kind="fake", run_id=handle.run_id, state=RunState.SUCCEEDED, detail="train"))
        elif task_type == "eval":
            eval_dir = bundle.artifacts_dir / "eval"
            eval_dir.mkdir(parents=True, exist_ok=True)
            (eval_dir / "eval_summary.json").write_text(json.dumps({"results": {"GAME": {"mean_score": 1.0}}}), encoding="utf-8")
            (bundle.artifacts_dir / "eval.log").write_text("eval\n", encoding="utf-8")
            bundle.write_run_status(RunStatus(runtime_kind="fake", run_id=handle.run_id, state=RunState.SUCCEEDED, detail="eval"))
        else:
            bundle.write_run_status(RunStatus(runtime_kind="fake", run_id=handle.run_id, state=RunState.SUCCEEDED, detail="default"))
        bundle.record_local_artifacts()
        return handle

    async def status(self, request: RunStatusRequest):
        bundle = JobBundle(request.handle.bundle_path)
        status = bundle.load_run_status()
        return status or RunStatus(runtime_kind="fake", run_id=request.handle.run_id, state=RunState.SUCCEEDED)

    async def logs(self, request: RunLogsRequest):
        bundle = JobBundle(request.handle.bundle_path)
        candidates = [
            bundle.artifacts_dir / "frontier.log",
            bundle.artifacts_dir / "relabel.log",
            bundle.artifacts_dir / "compile.log",
            bundle.artifacts_dir / "training.log",
            bundle.artifacts_dir / "eval.log",
        ]
        for path in candidates:
            if path.exists():
                return path.read_text(encoding="utf-8")
        return ""

    async def collect(self, request: CollectArtifactsRequest):
        bundle = JobBundle(request.handle.bundle_path)
        return bundle.record_local_artifacts()

    async def terminate(self, request: TerminateRunRequest):
        bundle = JobBundle(request.handle.bundle_path)
        bundle.write_run_status(RunStatus(runtime_kind="fake", run_id=request.handle.run_id, state=RunState.TERMINATED, detail="terminated"))
        return None


def _plane(tmp_path: Path) -> CoreControlService:
    return CoreControlService(
        experiments=ExperimentStore(str(tmp_path / "experiments")),
        execution=_WorkflowExecution(),
        templates=ExecutionTemplateRegistry(),
        task_registry=build_default_task_registry(),
    )


def _teacher_policy() -> TeacherPolicySpec:
    return TeacherPolicySpec(
        teachers=(
            TeacherEndpointSpec(name="search", kind="specialized"),
            TeacherEndpointSpec(name="wb", kind="white_box"),
            TeacherEndpointSpec(name="bb", kind="black_box"),
        ),
        env_policies={
            "GAME": {"primary": "search", "fallbacks": ("wb",)},
            "NAVWORLD": {"primary": "wb", "fallbacks": ("bb",)},
        },
    )


def test_teacher_router_prefers_env_specific_policy():
    policy = _teacher_policy()
    assert route_teacher(policy, "GAME").name == "search"
    assert route_teacher(policy, "NAVWORLD").name == "wb"


def test_relabel_and_compile_emit_expected_views(tmp_path):
    frontier_path = tmp_path / "frontier.jsonl"
    frontier_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "experiment_id": "exp",
                        "iteration_index": 1,
                        "task_id": "game-1",
                        "environment": "GAME",
                        "seed": 1,
                        "sample_index": 0,
                        "student_model_revision": "student-a",
                        "prompt": "play",
                        "response": "A1",
                        "expected_answer": "A1",
                        "teacher_repair": "A1",
                    }
                ),
                json.dumps(
                    {
                        "experiment_id": "exp",
                        "iteration_index": 1,
                        "task_id": "nav-1",
                        "environment": "NAVWORLD",
                        "seed": 2,
                        "sample_index": 0,
                        "student_model_revision": "student-a",
                        "prompt": "route",
                        "response": "go south",
                        "expected_answer": "go north",
                        "teacher_repair": "go north",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    relabel_spec = RelabelTaskSpec(
        experiment_id="exp",
        iteration_index=1,
        model_revision="student-a",
        frontier_traces_path=str(frontier_path),
        environments=("GAME", "NAVWORLD"),
        teacher_policy=_teacher_policy(),
        relabel=RelabelSpec(execution=StageExecutionSpec(template_id="local-host")),
    )
    relabel_bundle = tmp_path / "relabel-bundle"
    relabel_bundle.mkdir()
    summary = run_relabel(relabel_spec, bundle_root=str(relabel_bundle))
    assert summary["positive_count"] == 1
    assert summary["repaired_count"] == 1

    compile_spec = CompileTaskSpec(
        experiment_id="exp",
        iteration_index=1,
        model_revision="student-a",
        relabelled_traces_path=str(relabel_bundle / "artifacts" / "relabelled_traces.jsonl"),
        teacher_augmented_traces_path=str(relabel_bundle / "artifacts" / "teacher_augmented_traces.jsonl"),
        environments=("GAME", "NAVWORLD"),
        compile=CompileSpec(execution=StageExecutionSpec(template_id="local-host")),
    )
    compile_bundle = tmp_path / "compile-bundle"
    compile_bundle.mkdir()
    compile_summary = run_compile(compile_spec, bundle_root=str(compile_bundle))
    assert compile_summary["sft_records"] >= 2
    assert compile_summary["preference_records"] == 1
    compiled_sft = (compile_bundle / "artifacts" / "compiled_sft.jsonl").read_text(encoding="utf-8")
    assert "compiler_recipe_version" in compiled_sft


def test_control_tracks_multiple_stage_runs_by_run_key(tmp_path):
    plane = _plane(tmp_path)
    tasks_path = tmp_path / "tasks.jsonl"
    tasks_path.write_text(json.dumps({"task_id": "game-1", "environment": "GAME", "prompt": "play", "expected_answer": "A1"}) + "\n", encoding="utf-8")
    experiment = plane.create_experiment(CreateExperimentRequest(variable="vg", hypothesis="frontier stages should not overwrite each other"))
    stage = FrontierRolloutSpec(execution=StageExecutionSpec(template_id="local-host"))
    for run_key in ("iter01.frontier", "iter02.frontier"):
        plane.submit_task(
            TaskSubmission(
                experiment_id=experiment.id,
                task_type="vg_frontier",
                task_request=FrontierTaskSpec(
                    experiment_id=experiment.id,
                    iteration_index=1 if "01" in run_key else 2,
                    student_model_revision="student-a",
                    task_source_path=str(tasks_path),
                    environments=("GAME",),
                    rollout=stage,
                ).model_dump(mode="json"),
                template_id="local-host",
                run_key=run_key,
                bundle_dir=str(tmp_path / run_key.replace(".", "_")),
            )
        )
    reloaded = plane.load_experiment(experiment.id)
    assert reloaded is not None
    assert "iter01.frontier" in reloaded.results.task_runs
    assert "iter02.frontier" in reloaded.results.task_runs
    assert reloaded.results.task_runs["iter01.frontier"].bundle_path != reloaded.results.task_runs["iter02.frontier"].bundle_path


def test_launch_vg_sopd_from_path_runs_full_workflow(tmp_path):
    plane = _plane(tmp_path)
    frontier_tasks = tmp_path / "frontier_tasks.jsonl"
    frontier_tasks.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "task_id": "game-1",
                        "environment": "GAME",
                        "prompt": "pick move",
                        "expected_answer": "A1",
                        "student_candidates": ["B2", "A1"],
                        "teacher_repair": "A1",
                    }
                ),
                json.dumps(
                    {
                        "task_id": "nav-1",
                        "environment": "NAVWORLD",
                        "prompt": "plan route",
                        "expected_answer": "go north",
                        "student_candidates": ["go south", "go north"],
                        "teacher_repair": "go north",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    cold_start = tmp_path / "cold_start.jsonl"
    cold_start.write_text(json.dumps({"messages": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]}) + "\n", encoding="utf-8")
    guardrail_script = tmp_path / "guardrails.py"
    guardrail_script.write_text(
        "import json, os\n"
        "payload = {'model_revision': os.environ['AFFINE_MODEL_REVISION'], 'stage': os.environ['AFFINE_STAGE_LABEL']}\n"
        "with open(os.environ['AFFINE_OUTPUT_PATH'], 'w', encoding='utf-8') as handle:\n"
        "    json.dump(payload, handle)\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "vg.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "kind": "vg_sopd_launch",
                "experiment": {
                    "id": "v-vg",
                    "variable": "vg workflow",
                    "hypothesis": "staged data compilation should reach training",
                },
                "student_model_revision": "Qwen/Qwen2.5-0.5B-Instruct",
                "environments": ["GAME", "NAVWORLD"],
                "frontier_task_source": {
                    "kind": "local_file",
                    "label": "FRONTIER",
                    "path": str(frontier_tasks),
                },
                "teacher_policy": {
                    "teachers": [
                        {"name": "search", "kind": "specialized"},
                        {"name": "wb", "kind": "white_box"},
                        {"name": "bb", "kind": "black_box"},
                    ],
                    "env_policies": {
                        "GAME": {"primary": "search", "fallbacks": ["wb"]},
                        "NAVWORLD": {"primary": "wb", "fallbacks": ["bb"]},
                    },
                },
                "cold_start": {
                    "enabled": True,
                    "dataset": {"kind": "local_file", "label": "BOOT", "path": str(cold_start)},
                    "training": {
                        "label": "cold_start",
                        "train_config": {
                            "model": "Qwen/Qwen2.5-0.5B-Instruct",
                            "output_dir": "/tmp/checkpoints",
                            "num_train_epochs": 1,
                            "max_length": 256,
                        },
                        "execution": {"template_id": "local-host"},
                    },
                },
                "frontier": {"samples_per_task": 2, "execution": {"template_id": "local-host"}},
                "relabel": {"execution": {"template_id": "local-host"}},
                "compile": {"execution": {"template_id": "local-host"}},
                "sft_stage": {
                    "label": "iter_sft",
                    "train_config": {
                        "model": "Qwen/Qwen2.5-0.5B-Instruct",
                        "output_dir": "/tmp/checkpoints",
                        "num_train_epochs": 1,
                        "max_length": 256,
                    },
                    "execution": {"template_id": "local-host"},
                },
                "preference_stage": {
                    "label": "iter_pref",
                    "train_config": {
                        "model": "Qwen/Qwen2.5-0.5B-Instruct",
                        "train_type": "rlhf",
                        "rlhf_type": "dpo",
                        "output_dir": "/tmp/checkpoints",
                        "num_train_epochs": 1,
                        "max_length": 256,
                    },
                    "execution": {"template_id": "local-host"},
                },
                "guardrails": {
                    "enabled": True,
                    "command": [sys.executable, str(guardrail_script)],
                    "prompts_path": str(frontier_tasks),
                },
                "iteration_count": 1,
                "output_root": str(tmp_path / "vg-output"),
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    result = launch_vg_sopd_from_path(plane, str(config_path), forge_config=ForgeConfig())

    assert result["experiment_id"] == "v-vg"
    assert len(result["iteration_reports"]) == 1
    assert Path(result["current_model_revision"]).exists()
    reloaded = plane.load_experiment("v-vg")
    assert reloaded is not None
    assert reloaded.status == "completed"
    for run_key in ("cold_start.sft", "iter01.frontier", "iter01.relabel", "iter01.compile", "iter01.sft", "iter01.preference"):
        assert run_key in reloaded.results.task_runs
    report = reloaded.results.extra["vg_sopd_iteration_reports"]["iter_01"]
    assert report["guardrail_after"]["stage"] == "iter01"
    compile_record = reloaded.results.task_runs["iter01.compile"]
    assert (Path(compile_record.bundle_path) / compile_record.artifacts["compiled_sft.jsonl"]).exists()
