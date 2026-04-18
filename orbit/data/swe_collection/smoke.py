"""Convenience smoke entrypoint for staged SWE collection."""

from __future__ import annotations

from pathlib import Path

from orbit.foundation.data_contracts import CollectResult

from .buckets import run_swe_build_buckets
from .collector import run_swe_sampling
from .relabel import run_swe_relabel


def run_swe_smoke(
    *,
    output_dir: str,
    mini_task_range: str,
    codex_task_range: str,
    cache_dir: str = "/tmp/orbit-swe-task-cache",
    max_steps: int = 4,
    temps: tuple[float, ...] = (0.3,),
    mini_student_endpoint: str = "",
    mini_student_model: str = "",
    mini_student_api_key: str = "",
    codex_student_endpoint: str = "",
    codex_student_model: str = "",
    codex_student_api_key: str = "",
    teacher_endpoint: str = "",
    teacher_model: str = "",
    teacher_api_key: str = "",
) -> CollectResult:
    root = Path(output_dir)
    mini_dir = root / "mini"
    codex_dir = root / "codex"
    results = []
    results.append(
        run_swe_sampling(
            fmt="miniswe",
            task_range=mini_task_range,
            task_file="",
            output_dir=str(mini_dir),
            student_endpoint=mini_student_endpoint,
            student_model=mini_student_model,
            student_api_key=mini_student_api_key,
            teacher_endpoint=teacher_endpoint,
            teacher_model=teacher_model,
            teacher_api_key=teacher_api_key,
            cache_dir=cache_dir,
            max_steps=max_steps,
            resume=False,
            temps=temps,
            localization_budget=8,
            localization_top_k=3,
            plan_samples_per_state=2,
            max_realizations=4,
            search_node_budget=12,
            attempts_per_node=3,
            max_live_nodes=6,
            full_verify_budget=2,
        )
    )
    results.append(
        run_swe_relabel(
            input_dir=str(mini_dir),
            cache_dir=cache_dir,
            teacher_endpoint=teacher_endpoint,
            teacher_model=teacher_model,
            teacher_api_key=teacher_api_key,
        )
    )
    results.append(run_swe_build_buckets(input_dir=str(mini_dir)))
    results.append(
        run_swe_sampling(
            fmt="codex",
            task_range=codex_task_range,
            task_file="",
            output_dir=str(codex_dir),
            student_endpoint=codex_student_endpoint,
            student_model=codex_student_model,
            student_api_key=codex_student_api_key,
            teacher_endpoint=teacher_endpoint,
            teacher_model=teacher_model,
            teacher_api_key=teacher_api_key,
            cache_dir=cache_dir,
            max_steps=max_steps,
            resume=False,
            temps=temps,
            localization_budget=8,
            localization_top_k=3,
            plan_samples_per_state=2,
            max_realizations=4,
            search_node_budget=12,
            attempts_per_node=3,
            max_live_nodes=6,
            full_verify_budget=2,
        )
    )
    results.append(
        run_swe_relabel(
            input_dir=str(codex_dir),
            cache_dir=cache_dir,
            teacher_endpoint=teacher_endpoint,
            teacher_model=teacher_model,
            teacher_api_key=teacher_api_key,
        )
    )
    results.append(run_swe_build_buckets(input_dir=str(codex_dir)))
    return CollectResult(
        output=str(root),
        staging_path=str(root),
        raw_path=str(root),
        records=sum(result.records for result in results),
        success=sum(result.success for result in results),
        failed=sum(result.failed for result in results),
        mode="swe_smoke_v1",
        raw_files=[result.output for result in results],
    )


__all__ = ["run_swe_smoke"]
