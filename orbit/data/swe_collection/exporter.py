"""Artifact export and loading helpers for staged SWE collection runs."""

from __future__ import annotations

import json
from pathlib import Path

from orbit.foundation.data_contracts import (
    SweBucketKind,
    SweBucketSampleV1,
    SweBranchNodeV1,
    SweCollectionRunManifestV2,
    SweCritiqueRecordV1,
    SweFailurePointV1,
    SweIssueOracleV1,
    SweIssueRubricV1,
    SweLocalizationCandidateV1,
    SwePatchPlanV1,
    SweRawTrajectoryV1,
    SweRepairHypothesisV1,
    SweSearchNodeV1,
    SweSearchNodeV2,
    SweStepStateV1,
    SweTeacherStateSummaryV1,
    SweTeacherStateSummaryV2,
    SweTeacherJudgeDecisionV1,
    SweWorkspaceCheckpointV1,
)


class SweCollectionExporter:
    """Persist raw trajectories, step states, relabels, buckets, and manifests."""

    def __init__(self, *, output_dir: str):
        self.output_dir = Path(output_dir)
        self.raw_dir = self.output_dir / "raw"
        self.states_dir = self.output_dir / "states"
        self.oracle_dir = self.output_dir / "oracle"
        self.search_dir = self.output_dir / "search"
        self.relabel_dir = self.output_dir / "relabels"
        self.bucket_dir = self.output_dir / "buckets"
        self.canonical_dir = self.output_dir / "canonical"
        self.log_dir = self.output_dir / "logs"
        self.manifest_dir = self.output_dir / "manifests"
        for path in (
            self.raw_dir,
            self.states_dir,
            self.oracle_dir,
            self.search_dir,
            self.relabel_dir,
            self.bucket_dir,
            self.canonical_dir,
            self.log_dir,
            self.manifest_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
        self.raw_path = self.raw_dir / "trajectories.jsonl"
        self.oracle_path = self.oracle_dir / "oracles.jsonl"
        self.rubric_path = self.oracle_dir / "rubrics.jsonl"
        self.localization_path = self.search_dir / "localizations.jsonl"
        self.plan_path = self.search_dir / "plans.jsonl"
        self.branch_path = self.search_dir / "branches.jsonl"
        self.judge_decision_path = self.search_dir / "judge_decisions.jsonl"
        self.checkpoint_path = self.search_dir / "checkpoints.jsonl"
        self.hypothesis_path = self.search_dir / "hypotheses.jsonl"
        self.search_node_path = self.search_dir / "nodes.jsonl"
        self.teacher_summary_path = self.search_dir / "teacher_state_summaries.jsonl"
        self.failure_path = self.relabel_dir / "failure_points.jsonl"
        self.critique_path = self.relabel_dir / "critiques.jsonl"
        self.bucket_paths = {bucket: self.bucket_dir / f"{bucket}.jsonl" for bucket in ("A", "B", "C", "J", "O", "T", "V")}
        self.canonical_path = self.canonical_dir / "swe_infinite.jsonl"
        self.verifier_dataset_path = self.bucket_dir / "verifier_train.jsonl"
        self.run_manifest_path = self.manifest_dir / "run.json"

    def write_step_state(self, state: SweStepStateV1) -> str:
        path = self.states_dir / f"{state.state_id}.json"
        path.write_text(state.model_dump_json(indent=2) + "\n", encoding="utf-8")
        return str(path)

    def write_raw_log(self, *, trajectory_id: str, raw_log: str) -> str:
        path = self.log_dir / f"{trajectory_id}.log"
        path.write_text(raw_log, encoding="utf-8")
        return str(path)

    def append_raw_trajectory(self, trajectory: SweRawTrajectoryV1) -> None:
        with self.raw_path.open("a", encoding="utf-8") as handle:
            handle.write(trajectory.model_dump_json() + "\n")

    def append_issue_oracle(self, oracle: SweIssueOracleV1) -> None:
        with self.oracle_path.open("a", encoding="utf-8") as handle:
            handle.write(oracle.model_dump_json() + "\n")

    def append_issue_rubric(self, rubric: SweIssueRubricV1) -> None:
        with self.rubric_path.open("a", encoding="utf-8") as handle:
            handle.write(rubric.model_dump_json() + "\n")

    def append_localization(self, candidate: SweLocalizationCandidateV1) -> None:
        with self.localization_path.open("a", encoding="utf-8") as handle:
            handle.write(candidate.model_dump_json() + "\n")

    def append_patch_plan(self, plan: SwePatchPlanV1) -> None:
        with self.plan_path.open("a", encoding="utf-8") as handle:
            handle.write(plan.model_dump_json() + "\n")

    def append_branch_node(self, branch: SweBranchNodeV1) -> None:
        with self.branch_path.open("a", encoding="utf-8") as handle:
            handle.write(branch.model_dump_json() + "\n")

    def append_judge_decision(self, decision: SweTeacherJudgeDecisionV1) -> None:
        with self.judge_decision_path.open("a", encoding="utf-8") as handle:
            handle.write(decision.model_dump_json() + "\n")

    def append_checkpoint(self, checkpoint: SweWorkspaceCheckpointV1) -> None:
        with self.checkpoint_path.open("a", encoding="utf-8") as handle:
            handle.write(checkpoint.model_dump_json() + "\n")

    def append_hypothesis(self, hypothesis: SweRepairHypothesisV1) -> None:
        with self.hypothesis_path.open("a", encoding="utf-8") as handle:
            handle.write(hypothesis.model_dump_json() + "\n")

    def append_search_node(self, node: SweSearchNodeV1 | SweSearchNodeV2) -> None:
        with self.search_node_path.open("a", encoding="utf-8") as handle:
            handle.write(node.model_dump_json() + "\n")

    def append_teacher_state_summary(self, summary: SweTeacherStateSummaryV1 | SweTeacherStateSummaryV2) -> None:
        with self.teacher_summary_path.open("a", encoding="utf-8") as handle:
            handle.write(summary.model_dump_json() + "\n")

    def append_failure_point(self, failure_point: SweFailurePointV1) -> None:
        with self.failure_path.open("a", encoding="utf-8") as handle:
            handle.write(failure_point.model_dump_json() + "\n")

    def append_critique(self, critique: SweCritiqueRecordV1) -> None:
        with self.critique_path.open("a", encoding="utf-8") as handle:
            handle.write(critique.model_dump_json() + "\n")

    def append_bucket_sample(self, sample: SweBucketSampleV1) -> None:
        with self.bucket_paths[sample.bucket].open("a", encoding="utf-8") as handle:
            handle.write(sample.model_dump_json() + "\n")

    def append_canonical(self, row: dict) -> None:
        with self.canonical_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def write_verifier_dataset(self, rows: list[dict]) -> str:
        with self.verifier_dataset_path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        return str(self.verifier_dataset_path)

    def write_run_manifest(self, manifest: SweCollectionRunManifestV2) -> None:
        if self.run_manifest_path.exists():
            existing = json.loads(self.run_manifest_path.read_text(encoding="utf-8"))
            merged = dict(existing)
            incoming = manifest.model_dump(mode="json")
            merged["run_id"] = existing.get("run_id") or incoming["run_id"]
            merged["format"] = incoming["format"] if incoming.get("format") and incoming["format"] != "mixed" else existing.get("format", "mixed")
            for key, value in incoming.items():
                if key in {"schema_version", "run_id", "format", "stage_counts", "notes"}:
                    continue
                if value not in ("", None, {}, [], 0) or key not in merged:
                    merged[key] = value
            merged["stage_counts"] = {**existing.get("stage_counts", {}), **incoming.get("stage_counts", {})}
            merged["notes"] = {**existing.get("notes", {}), **incoming.get("notes", {})}
            manifest = SweCollectionRunManifestV2.model_validate(merged)
        self.run_manifest_path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")

    def load_raw_trajectories(self) -> list[dict]:
        if not self.raw_path.exists():
            return []
        rows: list[dict] = []
        with self.raw_path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    def load_step_states(self, state_paths: list[str] | tuple[str, ...]) -> list[dict]:
        rows: list[dict] = []
        for path_str in state_paths:
            path = Path(path_str)
            if not path.is_absolute():
                path = self.output_dir / path
            if path.exists():
                rows.append(json.loads(path.read_text(encoding="utf-8")))
        return rows

    def load_failure_points(self) -> list[dict]:
        if not self.failure_path.exists():
            return []
        with self.failure_path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def load_critiques(self) -> list[dict]:
        if not self.critique_path.exists():
            return []
        with self.critique_path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def load_bucket_samples(self, bucket: SweBucketKind) -> list[dict]:
        path = self.bucket_paths[bucket]
        if not path.exists():
            return []
        with path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def load_issue_oracles(self) -> list[dict]:
        if not self.oracle_path.exists():
            return []
        with self.oracle_path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def load_issue_rubrics(self) -> list[dict]:
        if not self.rubric_path.exists():
            return []
        with self.rubric_path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def load_localizations(self) -> list[dict]:
        if not self.localization_path.exists():
            return []
        with self.localization_path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def load_patch_plans(self) -> list[dict]:
        if not self.plan_path.exists():
            return []
        with self.plan_path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def load_branch_nodes(self) -> list[dict]:
        if not self.branch_path.exists():
            return []
        with self.branch_path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def load_judge_decisions(self) -> list[dict]:
        if not self.judge_decision_path.exists():
            return []
        with self.judge_decision_path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def load_checkpoints(self) -> list[dict]:
        if not self.checkpoint_path.exists():
            return []
        with self.checkpoint_path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def load_hypotheses(self) -> list[dict]:
        if not self.hypothesis_path.exists():
            return []
        with self.hypothesis_path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def load_search_nodes(self) -> list[dict]:
        if not self.search_node_path.exists():
            return []
        with self.search_node_path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def load_teacher_state_summaries(self) -> list[dict]:
        if not self.teacher_summary_path.exists():
            return []
        with self.teacher_summary_path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]


__all__ = ["SweCollectionExporter"]
