"""Bucket builders for staged SWE collection."""

from __future__ import annotations

import json
import uuid

from orbit.foundation.data_contracts import CollectResult, ConversationMessage, SweBucketSampleV1, SweCollectionRunManifestV2

from .exporter import SweCollectionExporter
from .judge import SweTerminalVerifier


def _messages_from_dicts(messages: list[dict]) -> tuple[ConversationMessage, ...]:
    return tuple(ConversationMessage.model_validate(message) for message in messages)


def _format_revised_action(fmt: str, revised_action: str) -> dict:
    if fmt == "codex":
        return {
            "role": "assistant",
            "content": "Minimal repair action",
            "tool_calls": [
                {
                    "id": "repair_action_1",
                    "function": {
                        "name": "shell",
                        "arguments": {"command": revised_action},
                    },
                }
            ],
        }
    return {
        "role": "assistant",
        "content": f"THOUGHT: Repair the current patch with one minimal revision.\n\n```bash\n{revised_action}\n```",
    }


def _prefix_messages(trajectory: dict, step_index: int) -> list[dict]:
    messages = list(trajectory.get("messages", []))
    assistant_seen = -1
    kept: list[dict] = []
    for message in messages:
        kept.append(message)
        if message.get("role") == "assistant":
            assistant_seen += 1
        if assistant_seen >= step_index:
            break
    return kept or messages[:2]


def _canonical_row(trajectory: dict) -> dict:
    messages = list(trajectory.get("messages", []))
    while messages and messages[-1].get("role") not in {"assistant", "tool"}:
        messages.pop()
    return {
        "env": "SWE-INFINITE",
        "instance_id": trajectory.get("instance_id", ""),
        "base_instance_id": trajectory.get("base_instance_id", ""),
        "repo": trajectory.get("repo", ""),
        "language": trajectory.get("language", ""),
        "format": trajectory.get("format", ""),
        "score": 1.0,
        "messages": messages,
        "source": "autonomous_student_success",
        "collector": trajectory.get("collector", ""),
        "teacher_calls": trajectory.get("teacher_calls", 0),
        "repair_round": trajectory.get("repair_round", 0),
        "rubric_score": trajectory.get("rubric_score", 0.0),
        "oracle_scores": trajectory.get("oracle_scores", {}),
        "sample_id": trajectory.get("instance_id", ""),
    }


class SweBucketBuilder:
    def __init__(self, *, output_dir: str):
        self.exporter = SweCollectionExporter(output_dir=output_dir)
        self.run_id = uuid.uuid4().hex

    def run(self) -> CollectResult:
        trajectories = self.exporter.load_raw_trajectories()
        for path in [*self.exporter.bucket_paths.values(), self.exporter.canonical_path]:
            if path.exists():
                path.unlink()
        failure_points = {row["trajectory_id"]: row for row in self.exporter.load_failure_points()}
        repairs = {row["trajectory_id"]: row for row in self.exporter.load_critiques()}
        counts = {"A": 0, "B": 0, "C": 0, "V": 0}

        for trajectory in trajectories:
            fmt = trajectory.get("format", "miniswe")
            trajectory_id = trajectory.get("trajectory_id", "")
            failure_point = failure_points.get(trajectory_id)
            repair = repairs.get(trajectory_id)
            step_count = max(len(trajectory.get("state_paths", [])), 1)
            verifier_result = SweTerminalVerifier.build_verifier_result(
                trajectory=trajectory,
                failure_point=failure_point,
                step_count=step_count,
            )

            if trajectory.get("verify_passed", False) and not repair:
                sample_a = SweBucketSampleV1(
                    sample_id=f"{trajectory_id}-A",
                    bucket="A",
                    instance_id=trajectory.get("instance_id", ""),
                    base_instance_id=trajectory.get("base_instance_id", ""),
                    trajectory_id=trajectory_id,
                    format=fmt,
                    messages=_messages_from_dicts(list(trajectory.get("messages", []))),
                    source="autonomous_student_success",
                    terminal_success=True,
                    first_error_index=-1,
                    process_weights=verifier_result.process_weights,
                    metadata={
                        "collector": trajectory.get("collector", ""),
                        "teacher_calls": trajectory.get("teacher_calls", 0),
                        "repair_round": trajectory.get("repair_round", 0),
                        "rubric_score": trajectory.get("rubric_score", 0.0),
                        "oracle_scores": trajectory.get("oracle_scores", {}),
                    },
                )
                self.exporter.append_bucket_sample(sample_a)
                self.exporter.append_canonical(_canonical_row(trajectory))
                counts["A"] += 1

            if failure_point and repair and repair.get("revised_action", "").strip():
                prefix = _prefix_messages(trajectory, int(failure_point.get("step_index", 0)))
                sample_b = SweBucketSampleV1(
                    sample_id=f"{trajectory_id}-B",
                    bucket="B",
                    instance_id=trajectory.get("instance_id", ""),
                    base_instance_id=trajectory.get("base_instance_id", ""),
                    trajectory_id=trajectory_id,
                    failure_id=failure_point.get("failure_id", ""),
                    critique_id=repair.get("critique_id", ""),
                    format=fmt,
                    messages=_messages_from_dicts(
                        [
                            *prefix,
                            {
                                "role": "user",
                                "content": (
                                    "The current branch is near-miss. Provide the corrected next step from this exact state "
                                    "without restarting the solution."
                                ),
                            },
                            _format_revised_action(fmt, repair.get("revised_action", "")),
                        ]
                    ),
                    source="critical_step_correction",
                    terminal_success=False,
                    first_error_index=int(failure_point.get("step_index", 0)),
                    process_weights=verifier_result.process_weights,
                    metadata={
                        "repair_round": repair.get("repair_round", 1),
                        "rubric_score": repair.get("rubric_score", 0.0),
                        "oracle_scores": repair.get("oracle_scores", {}),
                    },
                )
                current_state = {
                    "changed_files": trajectory.get("changed_files", []),
                    "failed_diff": trajectory.get("final_patch", ""),
                    "logs": trajectory.get("terminal_output", ""),
                    "failure_kind": failure_point.get("failure_kind", ""),
                }
                sample_c = SweBucketSampleV1(
                    sample_id=f"{trajectory_id}-C",
                    bucket="C",
                    instance_id=trajectory.get("instance_id", ""),
                    base_instance_id=trajectory.get("base_instance_id", ""),
                    trajectory_id=trajectory_id,
                    failure_id=failure_point.get("failure_id", ""),
                    critique_id=repair.get("critique_id", ""),
                    format=fmt,
                    messages=_messages_from_dicts(
                        [
                            {"role": "system", "content": "Repair the current failed patch with one minimal revision."},
                            {"role": "user", "content": json.dumps(current_state, ensure_ascii=False)},
                            _format_revised_action(fmt, repair.get("revised_action", "")),
                        ]
                    ),
                    source="patch_repair",
                    terminal_success=False,
                    first_error_index=int(failure_point.get("step_index", 0)),
                    process_weights=verifier_result.process_weights,
                    metadata={
                        "critique": repair.get("critique", ""),
                        "repair_round": repair.get("repair_round", 1),
                        "rubric_score": repair.get("rubric_score", 0.0),
                        "oracle_scores": repair.get("oracle_scores", {}),
                    },
                )
                self.exporter.append_bucket_sample(sample_b)
                self.exporter.append_bucket_sample(sample_c)
                counts["B"] += 1
                counts["C"] += 1

            sample_v = SweBucketSampleV1(
                sample_id=f"{trajectory_id}-V",
                bucket="V",
                instance_id=trajectory.get("instance_id", ""),
                base_instance_id=trajectory.get("base_instance_id", ""),
                trajectory_id=trajectory_id,
                failure_id=failure_point.get("failure_id", "") if failure_point else "",
                critique_id=repair.get("critique_id", "") if repair else "",
                format=fmt,
                messages=(),
                source="verifier_training",
                terminal_success=verifier_result.success,
                first_error_index=verifier_result.first_error_index,
                process_weights=verifier_result.process_weights,
                metadata={
                    "collector": trajectory.get("collector", ""),
                    "teacher_calls": trajectory.get("teacher_calls", 0) + (1 if repair else 0),
                    "repair_round": repair.get("repair_round", 0) if repair else 0,
                    "rubric_score": trajectory.get("rubric_score", 0.0),
                    "oracle_scores": trajectory.get("oracle_scores", {}),
                    "verifier_result": verifier_result.model_dump(mode="json"),
                },
            )
            self.exporter.append_bucket_sample(sample_v)
            counts["V"] += 1

        manifest = SweCollectionRunManifestV2(
            run_id=self.run_id,
            format=trajectories[0].get("format", "mixed") if len(trajectories) == 1 else "mixed",
            output_dir=str(self.exporter.output_dir),
            student_model=trajectories[0].get("student_model", "") if trajectories else "",
            student_endpoint=trajectories[0].get("student_endpoint", "") if trajectories else "",
            raw_dir=str(self.exporter.raw_dir),
            states_dir=str(self.exporter.states_dir),
            relabel_dir=str(self.exporter.relabel_dir),
            bucket_dir=str(self.exporter.bucket_dir),
            canonical_path=str(self.exporter.canonical_path),
            verifier_dataset_path=str(self.exporter.verifier_dataset_path),
            log_dir=str(self.exporter.log_dir),
            stage_counts={
                "sampled_trajectories": len(trajectories),
                "successful_trajectories": sum(1 for row in trajectories if row.get("verify_passed", False)),
                "failed_trajectories": sum(1 for row in trajectories if not row.get("verify_passed", False)),
                "failure_points": len(failure_points),
                "repair_records": len(repairs),
                **{f"bucket_{name}": count for name, count in counts.items()},
            },
        )
        self.exporter.write_run_manifest(manifest)
        return CollectResult(
            output=str(self.exporter.bucket_dir),
            staging_path=str(self.exporter.bucket_dir),
            raw_path=str(self.exporter.bucket_dir),
            records=sum(counts.values()),
            success=counts["A"],
            failed=0,
            mode="bucket_builder_v2",
            raw_files=[str(path) for path in self.exporter.bucket_paths.values()] + [str(self.exporter.canonical_path)],
            distribution=counts,
        )


def run_swe_build_buckets(*, input_dir: str) -> CollectResult:
    builder = SweBucketBuilder(output_dir=input_dir)
    return builder.run()


def run_swe_train_verifier_dataset(*, input_dir: str, output_dir: str = "") -> CollectResult:
    exporter = SweCollectionExporter(output_dir=input_dir)
    rows = exporter.load_bucket_samples("V")
    target = SweCollectionExporter(output_dir=output_dir or input_dir)
    dataset_rows = []
    for row in rows:
        verifier_result = dict((row.get("metadata") or {}).get("verifier_result", {}) or {})
        dataset_rows.append(
            {
                "sample_id": row.get("sample_id", ""),
                "instance_id": row.get("instance_id", ""),
                "base_instance_id": row.get("base_instance_id", ""),
                "format": row.get("format", ""),
                "terminal_success": row.get("terminal_success", False),
                "first_error_index": row.get("first_error_index", -1),
                "process_weights": row.get("process_weights", []),
                "verifier_result": verifier_result,
            }
        )
    verifier_path = target.write_verifier_dataset(dataset_rows)
    manifest = SweCollectionRunManifestV2(
        run_id=uuid.uuid4().hex,
        format="mixed",
        output_dir=str(target.output_dir),
        raw_dir=str(target.raw_dir),
        states_dir=str(target.states_dir),
        relabel_dir=str(target.relabel_dir),
        bucket_dir=str(target.bucket_dir),
        canonical_path=str(target.canonical_path),
        verifier_dataset_path=verifier_path,
        log_dir=str(target.log_dir),
        stage_counts={"verifier_rows": len(dataset_rows)},
    )
    target.write_run_manifest(manifest)
    return CollectResult(
        output=verifier_path,
        staging_path=verifier_path,
        raw_path=str(target.bucket_dir),
        records=len(dataset_rows),
        success=len(dataset_rows),
        failed=0,
        mode="verifier_dataset_v2",
        raw_files=[verifier_path, str(target.run_manifest_path)],
    )


__all__ = ["SweBucketBuilder", "run_swe_build_buckets", "run_swe_train_verifier_dataset"]
