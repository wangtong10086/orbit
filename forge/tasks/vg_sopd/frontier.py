"""Student-frontier rollout stage for VG-SOPD."""

from __future__ import annotations

import argparse
from pathlib import Path

from forge.tasks.vg_sopd.data_utils import candidate_response, load_jsonl, write_json, write_jsonl
from forge.tasks.vg_sopd.specs import FrontierTaskSpec


def run_frontier(spec: FrontierTaskSpec, *, bundle_root: str) -> dict:
    bundle_path = Path(bundle_root)
    records = load_jsonl(spec.task_source_path)
    selected: list[dict] = []
    seen = 0
    for record in records:
        environment = str(record.get("environment", "") or record.get("env", "")).upper()
        if environment and environment not in spec.environments:
            continue
        if spec.rollout.max_tasks and seen >= spec.rollout.max_tasks:
            break
        seen += 1
        task_id = str(record.get(spec.rollout.task_id_field, record.get("task_id", f"task-{seen}")))
        prompt = str(record.get(spec.rollout.prompt_field, record.get("prompt", "")))
        expected = str(record.get(spec.rollout.expected_answer_field, record.get("expected_answer", "")))
        teacher_repair = str(record.get(spec.rollout.teacher_repair_field, record.get("teacher_repair", "")))
        metadata = dict(record.get(spec.rollout.metadata_field, record.get("metadata", {})) or {})
        for sample_index in range(spec.rollout.samples_per_task):
            response = candidate_response(record, sample_index)
            selected.append(
                {
                    "experiment_id": spec.experiment_id,
                    "iteration_index": spec.iteration_index,
                    "task_id": task_id,
                    "environment": environment or str(spec.environments[0]),
                    "seed": spec.rollout.seed + sample_index,
                    "sample_index": sample_index,
                    "student_model_revision": spec.student_model_revision,
                    "prompt": prompt,
                    "response": response,
                    "expected_answer": expected,
                    "teacher_repair": teacher_repair,
                    "metadata": metadata,
                    "trace_metadata": {
                        "temperature": spec.rollout.temperature,
                        "require_student_prefix": spec.rollout.require_student_prefix,
                        "rollout_mode": "bundle_frontier_sampling",
                    },
                }
            )
    raw_path = bundle_path / "artifacts" / "raw_rollouts.jsonl"
    summary_path = bundle_path / "artifacts" / "frontier_summary.json"
    write_jsonl(raw_path, selected)
    summary = {
        "environment_count": len({record["environment"] for record in selected}),
        "record_count": len(selected),
        "task_count": len({record["task_id"] for record in selected}),
        "student_model_revision": spec.student_model_revision,
    }
    write_json(summary_path, summary)
    return summary


def _main() -> int:
    parser = argparse.ArgumentParser(description="Run the VG-SOPD frontier stage")
    parser.add_argument("--spec", required=True)
    parser.add_argument("--bundle-root", required=True)
    args = parser.parse_args()
    spec = FrontierTaskSpec.model_validate_json(Path(args.spec).read_text(encoding="utf-8"))
    run_frontier(spec, bundle_root=args.bundle_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
