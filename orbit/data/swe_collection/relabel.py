"""Near-miss teacher repair for staged SWE collection runs."""

from __future__ import annotations

import uuid

from orbit.foundation.data_contracts import CollectResult, SweCollectionRunManifestV2, SweCritiqueRecordV1, SweFailurePointV1

from .exporter import SweCollectionExporter
from .judge import SweTerminalVerifier
from .sessions import FailureCritiqueSession
from .task_source import SweTaskSource


class SweFailureRelabeler:
    def __init__(
        self,
        *,
        output_dir: str,
        task_source: SweTaskSource,
        critique_session: FailureCritiqueSession,
        window_radius: int = 1,
        max_repairs: int = 2,
    ):
        self.exporter = SweCollectionExporter(output_dir=output_dir)
        self.task_source = task_source
        self.critique_session = critique_session
        self.window_radius = window_radius
        self.max_repairs = max_repairs
        self.run_id = uuid.uuid4().hex
        self.teacher_probe_status = "unprobed"
        self.teacher_degraded_reason = ""

    def _window(self, states: list[dict], step_index: int) -> list[dict]:
        start = max(0, step_index - self.window_radius)
        end = min(len(states), step_index + self.window_radius + 1)
        return states[start:end]

    def run(self) -> CollectResult:
        trajectories = self.exporter.load_raw_trajectories()
        for path in (self.exporter.failure_path, self.exporter.critique_path):
            if path.exists():
                path.unlink()
        rubrics = {row["base_instance_id"]: row for row in self.exporter.load_issue_rubrics()}
        localizations = {row["candidate_id"]: row for row in self.exporter.load_localizations()}
        plans = {row["plan_id"]: row for row in self.exporter.load_patch_plans()}
        repair_count = 0
        failure_count = 0
        pending_repairs: list[tuple[dict, dict, dict | None, dict | None, dict | None, list[dict], dict]] = []
        for trajectory in trajectories:
            if trajectory.get("verify_passed", False):
                continue
            if trajectory.get("terminal_detail", "") in {"truncated_action", "parse_fail"}:
                continue
            task_id = trajectory.get("task_metadata", {}).get("task_id")
            task = self.task_source.load_task(int(task_id)) if task_id is not None else {"instance_id": trajectory.get("base_instance_id", "")}
            step_states = self.exporter.load_step_states(trajectory.get("state_paths", []))
            for state, path in zip(step_states, trajectory.get("state_paths", [])):
                state["path"] = path
            verifier = SweTerminalVerifier(task or {})
            located = verifier.locate_failure_point(trajectory=trajectory, step_states=step_states)
            failure_point = SweFailurePointV1(
                failure_id=f"{trajectory.get('trajectory_id', '')}-failure",
                trajectory_id=trajectory.get("trajectory_id", ""),
                instance_id=trajectory.get("instance_id", ""),
                base_instance_id=trajectory.get("base_instance_id", ""),
                format=trajectory.get("format", "miniswe"),
                step_index=int(located.get("step_index", 0)),
                failure_kind=located.get("failure_kind", "verify_fail"),
                localization_evidence=located.get("localization_evidence", ""),
                offline_hints_used=tuple(located.get("offline_hints_used", ()) or ()),
                state_path=located.get("state_path", ""),
            )
            self.exporter.append_failure_point(failure_point)
            failure_count += 1

            near_miss = bool(trajectory.get("task_metadata", {}).get("near_miss", False))
            if not near_miss:
                continue

            rubric = rubrics.get(trajectory.get("base_instance_id", ""))
            localization = localizations.get(trajectory.get("localization_id", ""))
            plan = plans.get(trajectory.get("plan_id", ""))
            pending_repairs.append(
                (
                    trajectory,
                    task or {},
                    rubric,
                    localization,
                    plan,
                    self._window(step_states, failure_point.step_index),
                    failure_point.model_dump(mode="json"),
                )
            )

        pending_repairs.sort(
            key=lambda item: (
                float((item[0].get("oracle_scores") or {}).get("total", 0.0) or 0.0),
                float(item[0].get("rubric_score", 0.0) or 0.0),
            ),
            reverse=True,
        )
        probe = getattr(self.critique_session, "probe", None)
        teacher_available = True
        if callable(probe):
            teacher_available, reason = probe()
            self.teacher_probe_status = "ok" if teacher_available else f"failed: {reason}"
            if not teacher_available:
                self.teacher_degraded_reason = reason
        else:
            self.teacher_probe_status = "skipped"
        if teacher_available:
            for trajectory, task, rubric, localization, plan, window, failure_point in pending_repairs[: self.max_repairs]:
                critique_turn = self.critique_session.critique_failure(
                    task=task,
                    trajectory=trajectory,
                    failure_point=failure_point,
                    window=window,
                    rubric=rubric,
                    localization=localization,
                    plan=plan,
                )
                critique = SweCritiqueRecordV1(
                    critique_id=f"{failure_point['failure_id']}-repair",
                    trajectory_id=failure_point["trajectory_id"],
                    failure_id=failure_point["failure_id"],
                    instance_id=failure_point["instance_id"],
                    base_instance_id=failure_point["base_instance_id"],
                    format=failure_point["format"],
                    teacher_model=self.critique_session.model,
                    teacher_endpoint=self.critique_session.endpoint,
                    repair_round=1,
                    near_miss=True,
                    rubric_score=float(trajectory.get("rubric_score", 0.0) or 0.0),
                    oracle_scores=dict(trajectory.get("oracle_scores", {}) or {}),
                    localization_id=trajectory.get("localization_id", ""),
                    plan_id=trajectory.get("plan_id", ""),
                    critique=critique_turn.critique,
                    revised_action=critique_turn.revised_action,
                    raw_response=critique_turn.raw_response,
                    metadata={
                        "collector": trajectory.get("collector", ""),
                        "teacher_calls_before_repair": trajectory.get("teacher_calls", 0),
                    },
                )
                self.exporter.append_critique(critique)
                repair_count += 1

        manifest = SweCollectionRunManifestV2(
            run_id=self.run_id,
            format=trajectories[0].get("format", "mixed") if len(trajectories) == 1 else "mixed",
            output_dir=str(self.exporter.output_dir),
            student_model=trajectories[0].get("student_model", "") if trajectories else "",
            student_endpoint=trajectories[0].get("student_endpoint", "") if trajectories else "",
            teacher_model=self.critique_session.model,
            teacher_endpoint=self.critique_session.endpoint,
            teacher_probe_status=self.teacher_probe_status,
            rubric_enabled=teacher_available,
            rubric_degraded_reason=self.teacher_degraded_reason,
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
                "failure_points": failure_count,
                "repair_records": repair_count,
                "repair_cap": self.max_repairs,
            },
        )
        self.exporter.write_run_manifest(manifest)
        return CollectResult(
            output=str(self.exporter.critique_path),
            staging_path=str(self.exporter.critique_path),
            raw_path=str(self.exporter.relabel_dir),
            records=failure_count,
            success=repair_count,
            failed=max(failure_count - repair_count, 0),
            mode="near_miss_repair_v1",
            raw_files=[str(self.exporter.failure_path), str(self.exporter.critique_path), str(self.exporter.run_manifest_path)],
            reason=self.teacher_degraded_reason,
        )


def run_swe_relabel(
    *,
    input_dir: str,
    cache_dir: str = "/tmp/orbit-swe-task-cache",
    teacher_endpoint: str = "",
    teacher_model: str = "",
    teacher_api_key: str = "",
    window_radius: int = 1,
    max_repairs: int = 2,
) -> CollectResult:
    critique_session = FailureCritiqueSession(endpoint=teacher_endpoint, model=teacher_model, api_key=teacher_api_key)
    relabeler = SweFailureRelabeler(
        output_dir=input_dir,
        task_source=SweTaskSource(cache_dir=cache_dir),
        critique_session=critique_session,
        window_radius=window_radius,
        max_repairs=max_repairs,
    )
    return relabeler.run()


__all__ = ["SweFailureRelabeler", "run_swe_relabel"]
