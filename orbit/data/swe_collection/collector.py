"""Cascade sampler for staged SWE collection."""

from __future__ import annotations

import json
import uuid
from urllib.error import HTTPError, URLError

from orbit.foundation.data_contracts import (
    CollectResult,
    ConversationMessage,
    SweBranchNodeV1,
    SweCollectionRunManifestV2,
    SweIssueOracleV1,
    SweIssueRubricV1,
    SweLocalizationCandidateV1,
    SwePatchPlanV1,
    SweRawTrajectoryV1,
    SweRepairHypothesisV1,
    SweSearchNodeV2,
    SweStepStateV1,
    SweTeacherStateSummaryV2,
    SweTeacherJudgeDecisionV1,
    SweWorkspaceCheckpointV1,
)

from .exporter import SweCollectionExporter
from .judge import SweTerminalVerifier, VerificationOutcome
from .oracle import aggregate_oracle_scores, build_hidden_oracle, score_rubric_alignment
from .sessions import (
    CodexStudentSession,
    MiniSweStudentSession,
    TeacherJudgeSession,
    normalize_patch_action_dict,
    resolve_teacher_api_key,
    resolve_teacher_endpoint,
)
from .task_source import SweTaskSource


def parse_sampling_temps(spec: str) -> tuple[float, ...]:
    if not spec.strip():
        return (0.3, 0.6, 0.9)
    values: list[float] = []
    for chunk in spec.split(","):
        part = chunk.strip()
        if not part:
            continue
        values.append(float(part))
    return tuple(values) or (0.3, 0.6, 0.9)


def _task_metadata(
    task: dict,
    verification,
    *,
    failed_tests: tuple[str, ...],
    passed_tests: tuple[str, ...],
    near_miss: bool,
    rubric_enabled: bool,
    rubric_degraded_reason: str,
    terminal_detail: str,
    localization_id: str,
    plan_id: str,
    rubric_id: str,
) -> dict:
    return {
        "task_id": task.get("task_id"),
        "base_commit": task.get("base_commit", ""),
        "test_command": task.get("test_command", ""),
        "fail_to_pass": task.get("fail_to_pass", []),
        "pass_to_pass": task.get("pass_to_pass", []),
        "dockerhub_tag": task.get("dockerhub_tag", ""),
        "patch": task.get("patch", ""),
        "test_patch": task.get("test_patch", ""),
        "failed_tests": list(failed_tests),
        "passed_tests": list(passed_tests),
        "verify_status": verification.status,
        "near_miss": near_miss,
        "rubric_enabled": rubric_enabled,
        "rubric_degraded_reason": rubric_degraded_reason,
        "terminal_detail": terminal_detail,
        "localization_id": localization_id,
        "plan_id": plan_id,
        "rubric_id": rubric_id,
    }


def _line_count_from_patch(diff_patch: str) -> int:
    return sum(1 for line in diff_patch.splitlines() if line.startswith(("+", "-")) and not line.startswith(("+++", "---")))


def _sample_instance_id(base_instance_id: str, localization_rank: int, plan_rank: int, realization_round: int = 1) -> str:
    return f"{base_instance_id}::loc{localization_rank}::patch{plan_rank}::r{realization_round}"


def _is_collector_side_no_patch(detail: str) -> bool:
    return detail in {"truncated_action", "parse_fail"}


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return default


class SweAutonomousSampler:
    """Run hidden-oracle-guided cascade search and persist raw trajectories/state."""

    collector_name = "student_cascade_v1"

    def __init__(
        self,
        *,
        fmt: str,
        task_source: SweTaskSource,
        runtime,
        student_session,
        output_dir: str,
        teacher_session=None,
        teacher_online: bool = True,
        teacher_online_budget: int = 12,
        teacher_branch_fanout: int = 2,
        max_steps: int = 4,
        temps: tuple[float, ...] = (0.3, 0.6, 0.9),
        resume: bool = False,
        localization_budget: int = 8,
        localization_top_k: int = 3,
        plan_samples_per_state: int = 2,
        max_realizations: int = 4,
        search_node_budget: int = 12,
        attempts_per_node: int = 3,
        max_live_nodes: int = 6,
        full_verify_budget: int = 2,
        root_race_rounds: int = 2,
        root_race_keep: int = 3,
        progressive_bias_beta: float = 0.30,
    ):
        self.format = fmt
        self.task_source = task_source
        self.runtime = runtime
        self.student_session = student_session
        self.output_dir = output_dir
        self.teacher_session = teacher_session
        self.teacher_model_name = teacher_session.model if teacher_session is not None else ""
        self.teacher_endpoint_name = teacher_session.endpoint if teacher_session is not None else ""
        self.teacher_online = teacher_online
        self.teacher_online_budget = teacher_online_budget
        self.teacher_branch_fanout = teacher_branch_fanout
        self.max_total_branches_per_issue = 8
        self.max_steps = max_steps
        self.temps = temps
        self.resume = resume
        self.localization_budget = localization_budget
        self.localization_top_k = localization_top_k
        self.plan_samples_per_state = plan_samples_per_state
        self.max_realizations = max_realizations
        self.search_node_budget = search_node_budget
        self.attempts_per_node = attempts_per_node
        self.max_live_nodes = max_live_nodes
        self.full_verify_budget = full_verify_budget
        self.root_race_rounds = root_race_rounds
        self.root_race_keep = root_race_keep
        self.progressive_bias_beta = progressive_bias_beta
        self.exporter = SweCollectionExporter(output_dir=output_dir)
        self.run_id = uuid.uuid4().hex
        self.student_probe_status = "unprobed"
        self.teacher_probe_status = "disabled"
        self.docker_probe_status = "unprobed"
        self.rubric_enabled = teacher_session is not None
        self.rubric_degraded_reason = ""
        self.teacher_online_calls_total = 0
        self.teacher_branches_total = 0
        self.branch_nodes_total = 0
        self.teacher_shaped_successes = 0
        self.root_nodes_total = 0
        self.root_race_rounds_run = 0
        self.hypothesis_nodes_total = 0
        self.hypothesis_children_total = 0
        self.teacher_hypotheses_total = 0
        self.near_miss_nodes_total = 0
        self.dead_end_nodes_total = 0
        self.selection_tier_histogram: dict[str, int] = {}
        self._near_miss_node_ids: set[str] = set()
        self._dead_end_node_ids: set[str] = set()
        self._node_tiers: dict[str, int] = {}
        self._teacher_budget_remaining = teacher_online_budget

    def _existing_base_ids(self) -> set[str]:
        if not self.resume:
            return set()
        seen: set[str] = set()
        for row in self.exporter.load_raw_trajectories():
            seen.add(str(row.get("base_instance_id") or row.get("instance_id", "")))
        return seen

    def _append_hidden_oracle(self, task: dict) -> SweIssueOracleV1:
        oracle = build_hidden_oracle(task)
        self.exporter.append_issue_oracle(oracle)
        return oracle

    def _append_issue_rubric(self, *, task: dict, oracle: SweIssueOracleV1) -> tuple[SweIssueRubricV1 | None, str]:
        if self.teacher_session is None:
            return None, self.rubric_degraded_reason or "teacher rubric disabled"
        try:
            turn = self.teacher_session.build_issue_rubric(task=task, oracle=oracle.model_dump(mode="json"))
        except (HTTPError, URLError, TimeoutError) as exc:
            return None, f"{type(exc).__name__}: {exc}"
        rubric = SweIssueRubricV1(
            rubric_id=f"{oracle.base_instance_id}-rubric",
            base_instance_id=oracle.base_instance_id,
            likely_modules=turn.likely_modules,
            required_constraints=turn.required_constraints,
            common_pseudo_solutions=turn.common_pseudo_solutions,
            forbidden_patterns=turn.forbidden_patterns,
            raw_response=turn.raw_response,
        )
        self.exporter.append_issue_rubric(rubric)
        return rubric, ""

    def _probe_dependencies(self, tasks: list[dict]) -> None:
        student_probe = getattr(self.student_session, "probe", None)
        if callable(student_probe):
            ok, reason = student_probe()
            self.student_probe_status = "ok" if ok else f"failed: {reason}"
            if not ok:
                raise RuntimeError(f"student probe failed: {reason}")
        else:
            self.student_probe_status = "skipped"

        if self.teacher_session is not None:
            teacher_probe = getattr(self.teacher_session, "probe", None)
            if callable(teacher_probe):
                ok, reason = teacher_probe()
                if ok:
                    self.teacher_probe_status = "ok"
                else:
                    self.teacher_probe_status = f"failed: {reason}"
                    self.rubric_enabled = False
                    self.rubric_degraded_reason = reason
                    self.teacher_session = None
            else:
                self.teacher_probe_status = "skipped"
        else:
            self.teacher_probe_status = "disabled"
            self.rubric_enabled = False
            self.rubric_degraded_reason = self.rubric_degraded_reason or "teacher rubric disabled"

        if tasks:
            runtime_probe = getattr(self.runtime, "probe_workspace", None)
            if callable(runtime_probe):
                ok, reason = runtime_probe(tasks[0])
                self.docker_probe_status = "ok" if ok else f"failed: {reason}"
                if not ok:
                    raise RuntimeError(f"docker probe failed: {reason}")
            else:
                self.docker_probe_status = "skipped"
        else:
            self.docker_probe_status = "skipped"

    def _teacher_online_ready(self) -> bool:
        return bool(
            self.teacher_online
            and self.teacher_session is not None
            and hasattr(self.teacher_session, "judge_localization")
            and hasattr(self.teacher_session, "judge_plan")
            and hasattr(self.teacher_session, "summarize_search_node")
            and self._teacher_budget_remaining > 0
        )

    def _next_branch_id(self, *, base_instance_id: str, stage: str, seed: str = "") -> str:
        suffix = seed or uuid.uuid4().hex[:6]
        return f"{base_instance_id}-{stage}-branch-{suffix}"

    def _append_branch_node(
        self,
        *,
        base_instance_id: str,
        trajectory_id: str = "",
        branch_id: str,
        parent_branch_id: str = "",
        stage: str,
        source: str,
        teacher_shaped: bool,
        current_score: float = 0.0,
        patch_hash: str = "",
        changed_files: tuple[str, ...] = (),
        alive: bool = True,
        submitted: bool = False,
        metadata: dict | None = None,
    ) -> None:
        self.exporter.append_branch_node(
            SweBranchNodeV1(
                branch_id=branch_id,
                base_instance_id=base_instance_id,
                trajectory_id=trajectory_id,
                parent_branch_id=parent_branch_id,
                format=self.format,
                stage=stage,
                source=source,
                teacher_shaped=teacher_shaped,
                alive=alive,
                submitted=submitted,
                current_score=current_score,
                patch_hash=patch_hash,
                changed_files=changed_files,
                metadata=metadata or {},
            )
        )
        self.branch_nodes_total += 1
        if source == "teacher":
            self.teacher_branches_total += 1

    def _record_teacher_decision(
        self,
        *,
        base_instance_id: str,
        stage: str,
        decision_turn,
        trajectory_id: str = "",
        branch_id: str = "",
        parent_branch_id: str = "",
        teacher_shaped: bool = False,
        metadata: dict | None = None,
    ) -> SweTeacherJudgeDecisionV1:
        decision = SweTeacherJudgeDecisionV1(
            decision_id=f"{base_instance_id}-{stage}-judge-{uuid.uuid4().hex[:8]}",
            base_instance_id=base_instance_id,
            trajectory_id=trajectory_id,
            branch_id=branch_id,
            parent_branch_id=parent_branch_id,
            format=self.format,
            stage=stage,
            score=decision_turn.score,
            decision=decision_turn.decision,
            stop_reason=decision_turn.stop_reason,
            teacher_shaped=teacher_shaped,
            branch_proposals=tuple(decision_turn.branch_proposals),
            teacher_model=self.teacher_model_name,
            teacher_endpoint=self.teacher_endpoint_name,
            raw_response=decision_turn.raw_response,
            metadata=metadata or {},
        )
        self.exporter.append_judge_decision(decision)
        self.teacher_online_calls_total += 1
        self._teacher_budget_remaining = max(self._teacher_budget_remaining - 1, 0)
        return decision

    def _append_checkpoint(self, checkpoint: SweWorkspaceCheckpointV1) -> None:
        self.exporter.append_checkpoint(checkpoint)

    def _append_hypothesis(self, hypothesis: SweRepairHypothesisV1) -> None:
        self.exporter.append_hypothesis(hypothesis)
        self.hypothesis_nodes_total += 1
        if hypothesis.source == "teacher":
            self.teacher_hypotheses_total += 1

    def _append_search_node_record(self, node: dict) -> None:
        record = SweSearchNodeV2(
            node_id=node["node_id"],
            base_instance_id=node["base_instance_id"],
            checkpoint_id=node["checkpoint_id"],
            parent_node_id=node.get("parent_node_id", ""),
            trajectory_id=node.get("trajectory_id", ""),
            hypothesis_id=str(node.get("hypothesis_id", "") or ""),
            parent_hypothesis_id=str(node.get("parent_hypothesis_id", "") or ""),
            best_checkpoint_id=str(node.get("best_checkpoint_id", "") or ""),
            best_hypothesis_id=str(node.get("best_hypothesis_id", "") or ""),
            format=self.format,
            teacher_shaped=bool(node.get("teacher_shaped", False)),
            visit_count=int(node.get("visit_count", 0)),
            attempts_used=int(node.get("attempts_used", 0)),
            prior_score=float(node.get("prior_score", 0.0) or 0.0),
            value_mean=float(node.get("value_mean", 0.0) or 0.0),
            selection_score=float(node.get("selection_score", 0.0) or 0.0),
            selection_tier=int(node.get("selection_tier", 0) or 0),
            value_vector=dict(node.get("value_vector", {}) or {}),
            last_action=dict(node.get("last_action", {}) or {}),
            terminal_status=str(node.get("terminal_status", "") or ""),
            terminal_detail=str(node.get("terminal_detail", "") or ""),
            metadata=dict(node.get("metadata", {}) or {}),
        )
        self.exporter.append_search_node(record)

    @staticmethod
    def _checkpoint_summary(checkpoint: SweWorkspaceCheckpointV1) -> dict:
        return {
            "checkpoint_id": checkpoint.checkpoint_id,
            "parent_checkpoint_id": checkpoint.parent_checkpoint_id,
            "changed_files": list(checkpoint.changed_files),
            "patch_hash": checkpoint.patch_hash,
            "git_status_short": checkpoint.git_status_short,
            "diff_patch": checkpoint.diff_patch[:4000],
        }

    def _record_teacher_state_summary(
        self,
        *,
        base_instance_id: str,
        checkpoint: SweWorkspaceCheckpointV1,
        node: dict,
        summary_turn,
    ) -> SweTeacherStateSummaryV2:
        summary = SweTeacherStateSummaryV2(
            summary_id=f"{base_instance_id}-summary-{uuid.uuid4().hex[:8]}",
            base_instance_id=base_instance_id,
            checkpoint_id=checkpoint.checkpoint_id,
            trajectory_id=node.get("trajectory_id", ""),
            node_id=node["node_id"],
            parent_node_id=node.get("parent_node_id", ""),
            hypothesis_id=str(node.get("hypothesis_id", "") or ""),
            parent_hypothesis_id=str(node.get("parent_hypothesis_id", "") or ""),
            format=self.format,
            root_cause_guess=summary_turn.root_cause_guess,
            target_file_ids=summary_turn.target_file_ids,
            target_span_ids=summary_turn.target_span_ids,
            minimal_edit_direction=summary_turn.minimal_edit_direction,
            prior_score=summary_turn.prior_score,
            value_score=summary_turn.value_score,
            submit_likelihood=summary_turn.submit_likelihood,
            dead_end_risk=summary_turn.dead_end_risk,
            branch_proposals=tuple(summary_turn.branch_proposals),
            teacher_model=self.teacher_model_name,
            teacher_endpoint=self.teacher_endpoint_name,
            raw_response=summary_turn.raw_response,
            metadata={
                "search_node_budget_remaining": self.search_node_budget,
                "attempts_used": int(node.get("attempts_used", 0)),
                "last_feedback": str(node.get("last_feedback", "") or ""),
            },
        )
        self.exporter.append_teacher_state_summary(summary)
        self.teacher_online_calls_total += 1
        self._teacher_budget_remaining = max(self._teacher_budget_remaining - 1, 0)
        return summary

    def _teacher_summary_for_node(
        self,
        *,
        task: dict,
        oracle: SweIssueOracleV1,
        rubric: SweIssueRubricV1 | None,
        checkpoint: SweWorkspaceCheckpointV1,
        span_catalog: list[dict],
        node: dict,
    ) -> SweTeacherStateSummaryV2 | None:
        if not self._teacher_online_ready():
            return None
        try:
            turn = self.teacher_session.summarize_search_node(
                task=task,
                oracle=oracle.model_dump(mode="json"),
                rubric=rubric.model_dump(mode="json") if rubric else None,
                checkpoint=self._checkpoint_summary(checkpoint),
                span_catalog=span_catalog,
                last_feedback=str(node.get("last_feedback", "") or ""),
            )
        except (HTTPError, URLError, TimeoutError):
            return None
        return self._record_teacher_state_summary(
            base_instance_id=oracle.base_instance_id,
            checkpoint=checkpoint,
            node=node,
            summary_turn=turn,
        )

    def _progressive_selection_score(self, *, tier_score: float, empirical_value: float, teacher_prior: float, visit_count: int, parent_visits: int, submit_candidate: bool) -> float:
        exploration_bonus = 0.0
        if parent_visits >= 0:
            exploration_bonus = 0.15 * (((max(parent_visits, 0) + 1) ** 0.5) / ((visit_count + 1) ** 0.5))
        progressive_prior_bonus = float(self.progressive_bias_beta) * float(teacher_prior or 0.0) / float(visit_count + 1)
        score = float(tier_score or 0.0) + float(empirical_value or 0.0) + exploration_bonus + progressive_prior_bonus
        if submit_candidate:
            score += 0.10
        return score

    @staticmethod
    def _empty_value_vector() -> dict[str, float]:
        return {
            "full_verify_mean": 0.0,
            "cheap_verify_mean": 0.0,
            "syntax_mean": 0.0,
            "progress_mean": 0.0,
            "dead_end_mean": 0.0,
            "best_tier": 0.0,
        }

    @staticmethod
    def _tier_score(tier: int) -> float:
        return {4: 1.0, 3: 0.75, 2: 0.5, 1: 0.25, 0: 0.0}.get(int(tier), 0.0)

    @staticmethod
    def _node_progress(changed_files: tuple[str, ...], oracle_scores: dict) -> float:
        if not changed_files:
            return 0.0
        file_overlap = _safe_float((oracle_scores or {}).get("file_overlap", 0.0))
        symbol_overlap = _safe_float((oracle_scores or {}).get("symbol_overlap", 0.0))
        patch_size = _safe_float((oracle_scores or {}).get("patch_size", 0.0))
        return max(0.0, min(1.0, 0.5 * file_overlap + 0.3 * symbol_overlap + 0.2 * patch_size))

    def _node_tier(self, node: dict) -> int:
        verification: VerificationOutcome = node.get("verification") or VerificationOutcome(
            verified=False,
            status="max_steps",
            output="",
            passed_tests=(),
            failed_tests=(),
            changed_files=(),
        )
        changed_files = tuple(node.get("changed_files", ()) or ())
        syntax_ok = bool(node.get("syntax_ok", False))
        cheap_verify_status = str(node.get("cheap_verify_status", "") or "")
        progress = self._node_progress(changed_files, dict(node.get("oracle_scores", {}) or {}))
        if verification.verified:
            return 4
        if (bool(node.get("full_verified", False)) and changed_files) or (cheap_verify_status == "verify_fail" and syntax_ok and progress >= 0.3):
            return 3
        if syntax_ok and changed_files:
            return 2
        if changed_files:
            return 1
        return 0

    def _update_node_value_vector(self, node: dict) -> None:
        vector = dict(node.get("value_vector", {}) or self._empty_value_vector())
        visit_count = max(int(node.get("visit_count", 0) or 0), 1)
        verification: VerificationOutcome = node.get("verification") or VerificationOutcome(
            verified=False,
            status="max_steps",
            output="",
            passed_tests=(),
            failed_tests=(),
            changed_files=(),
        )
        changed_files = tuple(node.get("changed_files", ()) or ())
        syntax_ok = bool(node.get("syntax_ok", False))
        cheap_verify_status = str(node.get("cheap_verify_status", "") or "")
        progress = self._node_progress(changed_files, dict(node.get("oracle_scores", {}) or {}))
        dead_end = 1.0 if node.get("terminal_detail") in {
            "invalid_target",
            "invalid_span",
            "no_action",
            "parse_fail",
            "duplicate_patch",
            "no_progress",
        } else 0.0
        full_value = 1.0 if verification.verified else (0.55 if bool(node.get("full_verified", False)) and changed_files else 0.0)
        cheap_value = 0.45 if cheap_verify_status == "verify_fail" and syntax_ok else (0.2 if cheap_verify_status == "success" and syntax_ok else 0.0)
        syntax_value = 1.0 if syntax_ok and changed_files else (0.4 if changed_files else 0.0)
        for key, value in {
            "full_verify_mean": full_value,
            "cheap_verify_mean": cheap_value,
            "syntax_mean": syntax_value,
            "progress_mean": progress,
            "dead_end_mean": dead_end,
        }.items():
            previous = _safe_float(vector.get(key, 0.0))
            vector[key] = ((previous * (visit_count - 1)) + value) / visit_count
        vector["best_tier"] = max(_safe_float(vector.get("best_tier", 0.0)), float(self._node_tier(node)))
        node["value_vector"] = vector
        node["selection_tier"] = int(vector["best_tier"])
        node["value_mean"] = max(
            _safe_float(node.get("value_mean", 0.0)),
            0.45 * _safe_float(vector.get("full_verify_mean", 0.0))
            + 0.30 * _safe_float(vector.get("cheap_verify_mean", 0.0))
            + 0.15 * _safe_float(vector.get("syntax_mean", 0.0))
            + 0.10 * _safe_float(vector.get("progress_mean", 0.0))
            - 0.20 * _safe_float(vector.get("dead_end_mean", 0.0)),
        )
        node_id = str(node.get("node_id", "") or "")
        self._node_tiers[node_id] = int(node["selection_tier"])
        if node["selection_tier"] >= 3:
            self._near_miss_node_ids.add(node_id)
        if node["selection_tier"] == 0:
            self._dead_end_node_ids.add(node_id)
        self.near_miss_nodes_total = len(self._near_miss_node_ids)
        self.dead_end_nodes_total = len(self._dead_end_node_ids)
        histogram: dict[str, int] = {}
        for tier in self._node_tiers.values():
            key = str(tier)
            histogram[key] = histogram.get(key, 0) + 1
        self.selection_tier_histogram = histogram

    @staticmethod
    def _hypothesis_key(hypothesis: dict) -> tuple[tuple[str, ...], tuple[str, ...], str]:
        return (
            tuple(str(item).strip() for item in hypothesis.get("target_file_ids", []) if str(item).strip()),
            tuple(str(item).strip() for item in hypothesis.get("target_span_ids", []) if str(item).strip()),
            str(hypothesis.get("minimal_edit_direction", "") or "").strip(),
        )

    @staticmethod
    def _localization_key(candidate: SweLocalizationCandidateV1) -> tuple[tuple[str, ...], tuple[str, ...], str]:
        files = tuple(candidate.metadata.get("existing_files", candidate.candidate_files) or candidate.candidate_files)
        return files, candidate.candidate_symbols, candidate.edit_type

    @staticmethod
    def _plan_key(plan: SwePatchPlanV1) -> tuple[tuple[str, ...], tuple[str, ...], str]:
        files = tuple(plan.metadata.get("existing_files", plan.target_files) or plan.target_files)
        return files, plan.target_symbols, plan.edit_type

    @staticmethod
    def _frontier_summary(items: list[dict], *, limit: int = 3) -> dict:
        return {
            "count": len(items),
            "top": items[:limit],
        }

    def _judge_localization_candidate(
        self,
        *,
        task: dict,
        oracle: SweIssueOracleV1,
        rubric: SweIssueRubricV1 | None,
        candidate: SweLocalizationCandidateV1,
        frontier_summary: dict,
    ) -> SweTeacherJudgeDecisionV1 | None:
        if not self._teacher_online_ready():
            return None
        try:
            turn = self.teacher_session.judge_localization(
                task=task,
                oracle=oracle.model_dump(mode="json"),
                rubric=rubric.model_dump(mode="json") if rubric else None,
                candidate=candidate.model_dump(mode="json"),
                frontier_summary=frontier_summary,
            )
        except (HTTPError, URLError, TimeoutError):
            return None
        return self._record_teacher_decision(
            base_instance_id=oracle.base_instance_id,
            stage="localization",
            decision_turn=turn,
            branch_id=candidate.candidate_id,
            teacher_shaped=False,
            metadata={"candidate_id": candidate.candidate_id},
        )

    def _judge_plan_candidate(
        self,
        *,
        task: dict,
        oracle: SweIssueOracleV1,
        rubric: SweIssueRubricV1 | None,
        localization: SweLocalizationCandidateV1,
        plan: SwePatchPlanV1,
        frontier_summary: dict,
    ) -> SweTeacherJudgeDecisionV1 | None:
        if not self._teacher_online_ready():
            return None
        try:
            turn = self.teacher_session.judge_plan(
                task=task,
                oracle=oracle.model_dump(mode="json"),
                rubric=rubric.model_dump(mode="json") if rubric else None,
                localization=localization.model_dump(mode="json"),
                plan=plan.model_dump(mode="json"),
                frontier_summary=frontier_summary,
            )
        except (HTTPError, URLError, TimeoutError):
            return None
        return self._record_teacher_decision(
            base_instance_id=oracle.base_instance_id,
            stage="plan",
            decision_turn=turn,
            branch_id=plan.plan_id,
            parent_branch_id=localization.candidate_id,
            teacher_shaped=False,
            metadata={"plan_id": plan.plan_id, "localization_id": localization.candidate_id},
        )

    def _judge_realization_step(
        self,
        *,
        task: dict,
        oracle: SweIssueOracleV1,
        rubric: SweIssueRubricV1 | None,
        trajectory_id: str,
        branch_id: str,
        parent_branch_id: str,
        teacher_shaped: bool,
        branch_state: dict,
        last_action: dict,
        runtime_feedback: dict,
    ) -> SweTeacherJudgeDecisionV1 | None:
        if not self._teacher_online_ready():
            return None
        try:
            turn = self.teacher_session.judge_realization_step(
                task=task,
                oracle=oracle.model_dump(mode="json"),
                rubric=rubric.model_dump(mode="json") if rubric else None,
                branch_state=branch_state,
                last_action=last_action,
                runtime_feedback=runtime_feedback,
            )
        except (HTTPError, URLError, TimeoutError):
            return None
        return self._record_teacher_decision(
            base_instance_id=oracle.base_instance_id,
            stage="realization",
            decision_turn=turn,
            trajectory_id=trajectory_id,
            branch_id=branch_id,
            parent_branch_id=parent_branch_id,
            teacher_shaped=teacher_shaped,
            metadata={
                "branch_state": branch_state,
                "last_action": last_action,
                "runtime_feedback": runtime_feedback,
            },
        )

    def _collect_localizations(
        self,
        *,
        task: dict,
        oracle: SweIssueOracleV1,
        rubric: SweIssueRubricV1 | None,
        repo_files: set[str],
    ) -> tuple[list[SweLocalizationCandidateV1], int]:
        candidates: list[SweLocalizationCandidateV1] = []
        rubric_dict = rubric.model_dump(mode="json") if rubric else None
        stable_top2: tuple[tuple[str, ...], ...] = ()
        stable_hits = 0
        for index in range(self.localization_budget):
            temperature = self.temps[index % len(self.temps)]
            proposal = self.student_session.propose_localization(task=task, temperature=temperature)
            existing_files = tuple(path for path in proposal.candidate_files if path in repo_files)
            oracle_scores = aggregate_oracle_scores(
                files=existing_files or proposal.candidate_files,
                symbols=proposal.candidate_symbols,
                edit_type=proposal.edit_type,
                oracle=oracle,
            )
            rubric_score = score_rubric_alignment(
                files=existing_files or proposal.candidate_files,
                symbols=proposal.candidate_symbols,
                hypothesis=proposal.hypothesis,
                rubric=rubric_dict,
            )
            total_score = oracle_scores["total"] * 0.75 + rubric_score * 0.25
            if proposal.candidate_files and not existing_files:
                total_score -= 0.5
            if existing_files:
                total_score += min(0.2, 0.1 * len(existing_files))
            candidate = SweLocalizationCandidateV1(
                candidate_id=f"{oracle.base_instance_id}-loc-{index + 1}",
                base_instance_id=oracle.base_instance_id,
                format=self.format,
                temperature=temperature,
                candidate_files=proposal.candidate_files,
                candidate_symbols=proposal.candidate_symbols,
                hypothesis=proposal.hypothesis,
                edit_type=proposal.edit_type,
                oracle_scores=oracle_scores,
                rubric_score=rubric_score,
                total_score=total_score,
                raw_response=proposal.raw_response,
                metadata={
                    "existing_files": list(existing_files),
                    "file_exists": bool(existing_files),
                    "source": "student",
                    "teacher_shaped": False,
                },
            )
            self.exporter.append_localization(candidate)
            candidates.append(candidate)
            self._append_branch_node(
                base_instance_id=oracle.base_instance_id,
                branch_id=candidate.candidate_id,
                stage="localization",
                source="student",
                teacher_shaped=False,
                current_score=candidate.total_score,
                metadata={"candidate_files": list(candidate.candidate_files), "candidate_symbols": list(candidate.candidate_symbols)},
            )
            ranked = sorted(candidates, key=lambda item: item.total_score, reverse=True)
            top2 = tuple(tuple(item.metadata.get("existing_files", item.candidate_files)) for item in ranked[:2])
            both_existing = len(top2) == 2 and all(group for group in top2)
            if index + 1 >= 4 and both_existing and top2 == stable_top2:
                stable_hits += 1
            else:
                stable_hits = 0
                stable_top2 = top2
            if stable_hits >= 1:
                break
        teacher_candidates: list[SweLocalizationCandidateV1] = []
        shortlisted_for_judge = sorted(candidates, key=lambda item: item.total_score, reverse=True)[: max(self.localization_top_k, 1)]
        frontier_summary = self._frontier_summary([row.model_dump(mode="json") for row in shortlisted_for_judge])
        for candidate in shortlisted_for_judge:
            decision = self._judge_localization_candidate(
                task=task,
                oracle=oracle,
                rubric=rubric,
                candidate=candidate,
                frontier_summary=frontier_summary,
            )
            if decision is None:
                continue
            updated = candidate.model_copy(
                update={
                    "total_score": min(1.0, candidate.total_score * 0.6 + decision.score * 0.4 - (0.4 if decision.decision == "drop" else 0.0)),
                    "metadata": {
                        **candidate.metadata,
                        "judge_score": decision.score,
                        "judge_decision": decision.decision,
                        "failure_risk": decision.metadata.get("runtime_feedback", {}).get("failure_risk", 0.0) if isinstance(decision.metadata, dict) else 0.0,
                    },
                }
            )
            for index, existing in enumerate(candidates):
                if existing.candidate_id == candidate.candidate_id:
                    candidates[index] = updated
                    break
            candidate = updated
            for proposal_index, branch in enumerate(decision.branch_proposals[: self.teacher_branch_fanout], start=1):
                branch_files = tuple(path for path in branch.get("candidate_files", []) if path in repo_files)
                branch_symbols = tuple(str(item).strip() for item in branch.get("candidate_symbols", []) if str(item).strip())
                branch_hypothesis = str(branch.get("hypothesis", "") or candidate.hypothesis)
                branch_edit_type = str(branch.get("edit_type", "") or candidate.edit_type)
                branch_oracle_scores = aggregate_oracle_scores(
                    files=branch_files or tuple(str(path).strip() for path in branch.get("candidate_files", []) if str(path).strip()),
                    symbols=branch_symbols,
                    edit_type=branch_edit_type,
                    oracle=oracle,
                )
                branch_rubric_score = score_rubric_alignment(
                    files=branch_files or tuple(str(path).strip() for path in branch.get("candidate_files", []) if str(path).strip()),
                    symbols=branch_symbols,
                    hypothesis=branch_hypothesis,
                    rubric=rubric_dict,
                )
                teacher_candidate = SweLocalizationCandidateV1(
                    candidate_id=self._next_branch_id(base_instance_id=oracle.base_instance_id, stage="loc", seed=f"t{candidate.candidate_id}-{proposal_index}"),
                    base_instance_id=oracle.base_instance_id,
                    format=self.format,
                    temperature=candidate.temperature,
                    candidate_files=branch_files or tuple(str(path).strip() for path in branch.get("candidate_files", []) if str(path).strip()),
                    candidate_symbols=branch_symbols,
                    hypothesis=branch_hypothesis,
                    edit_type=branch_edit_type,
                    oracle_scores=branch_oracle_scores,
                    rubric_score=branch_rubric_score,
                    total_score=min(1.0, decision.score * 0.75 + branch_oracle_scores["total"] * 0.2 + branch_rubric_score * 0.05),
                    raw_response=decision.raw_response,
                    metadata={
                        "existing_files": list(branch_files),
                        "file_exists": bool(branch_files),
                        "source": "teacher",
                        "teacher_shaped": True,
                        "parent_candidate_id": candidate.candidate_id,
                    },
                )
                self.exporter.append_localization(teacher_candidate)
                teacher_candidates.append(teacher_candidate)
                self._append_branch_node(
                    base_instance_id=oracle.base_instance_id,
                    branch_id=teacher_candidate.candidate_id,
                    parent_branch_id=candidate.candidate_id,
                    stage="localization",
                    source="teacher",
                    teacher_shaped=True,
                    current_score=teacher_candidate.total_score,
                    metadata={"candidate_files": list(teacher_candidate.candidate_files), "candidate_symbols": list(teacher_candidate.candidate_symbols)},
                )
        candidates.extend(teacher_candidates)
        deduped: dict[tuple[tuple[str, ...], tuple[str, ...], str], SweLocalizationCandidateV1] = {}
        for candidate in sorted(candidates, key=lambda item: item.total_score, reverse=True):
            key = self._localization_key(candidate)
            if key not in deduped:
                deduped[key] = candidate
        ranked = sorted(deduped.values(), key=lambda item: item.total_score, reverse=True)
        return ranked[: self.localization_top_k], len(candidates)

    def _collect_patch_plans(
        self,
        *,
        task: dict,
        oracle: SweIssueOracleV1,
        rubric: SweIssueRubricV1 | None,
        localizations: list[SweLocalizationCandidateV1],
        repo_files: set[str],
    ) -> tuple[list[SwePatchPlanV1], int]:
        plans: list[SwePatchPlanV1] = []
        rubric_dict = rubric.model_dump(mode="json") if rubric else None
        for loc_rank, localization in enumerate(localizations, start=1):
            localization_payload = localization.model_dump(mode="json")
            for plan_index in range(self.plan_samples_per_state):
                temperature = self.temps[(loc_rank + plan_index - 1) % len(self.temps)]
                proposal = self.student_session.propose_patch_plan(
                    task=task,
                    localization=localization_payload,
                    temperature=temperature,
                )
                existing_files = tuple(path for path in proposal.target_files if path in repo_files) or tuple(
                    path for path in localization.candidate_files if path in repo_files
                )
                patch_line_count = _line_count_from_patch(proposal.diff_sketch)
                oracle_scores = aggregate_oracle_scores(
                    files=existing_files or proposal.target_files,
                    symbols=proposal.target_symbols or localization.candidate_symbols,
                    edit_type=proposal.edit_type,
                    patch_line_count=patch_line_count,
                    oracle=oracle,
                )
                rubric_score = score_rubric_alignment(
                    files=existing_files or proposal.target_files,
                    symbols=proposal.target_symbols,
                    hypothesis=proposal.diff_sketch,
                    rubric=rubric_dict,
                )
                total_score = oracle_scores["total"] * 0.7 + rubric_score * 0.2
                if set(existing_files) & set(localization.candidate_files):
                    total_score += 0.1
                if proposal.target_files and not existing_files:
                    total_score -= 0.6
                if existing_files:
                    total_score += min(0.2, 0.1 * len(existing_files))
                plan = SwePatchPlanV1(
                    plan_id=f"{oracle.base_instance_id}-plan-{loc_rank}-{plan_index + 1}",
                    base_instance_id=oracle.base_instance_id,
                    format=self.format,
                    localization_id=localization.candidate_id,
                    target_files=existing_files or proposal.target_files,
                    target_symbols=proposal.target_symbols,
                    plan_steps=proposal.plan_steps,
                    diff_sketch=proposal.diff_sketch,
                    edit_type=proposal.edit_type,
                    oracle_scores=oracle_scores,
                    rubric_score=rubric_score,
                    total_score=min(1.0, total_score),
                    raw_response=proposal.raw_response,
                    metadata={
                        "file_exists": bool(existing_files),
                        "existing_files": list(existing_files),
                        "source": "student",
                        "teacher_shaped": bool(localization.metadata.get("teacher_shaped", False)),
                    },
                )
                self.exporter.append_patch_plan(plan)
                plans.append(plan)
                self._append_branch_node(
                    base_instance_id=oracle.base_instance_id,
                    branch_id=plan.plan_id,
                    parent_branch_id=localization.candidate_id,
                    stage="plan",
                    source="student",
                    teacher_shaped=bool(localization.metadata.get("teacher_shaped", False)),
                    current_score=plan.total_score,
                    metadata={"target_files": list(plan.target_files), "target_symbols": list(plan.target_symbols)},
                )
        teacher_plans: list[SwePatchPlanV1] = []
        shortlisted_for_judge = sorted(plans, key=lambda item: item.total_score, reverse=True)[: max(self.max_realizations, 1)]
        frontier_summary = self._frontier_summary([row.model_dump(mode="json") for row in shortlisted_for_judge])
        localization_by_id = {localization.candidate_id: localization for localization in localizations}
        for plan in shortlisted_for_judge:
            localization = localization_by_id.get(plan.localization_id)
            if localization is None:
                continue
            decision = self._judge_plan_candidate(
                task=task,
                oracle=oracle,
                rubric=rubric,
                localization=localization,
                plan=plan,
                frontier_summary=frontier_summary,
            )
            if decision is None:
                continue
            updated = plan.model_copy(
                update={
                    "total_score": min(1.0, plan.total_score * 0.6 + decision.score * 0.4 - (0.5 if decision.decision == "drop" else 0.0)),
                    "metadata": {
                        **plan.metadata,
                        "judge_score": decision.score,
                        "judge_decision": decision.decision,
                    },
                }
            )
            for index, existing in enumerate(plans):
                if existing.plan_id == plan.plan_id:
                    plans[index] = updated
                    break
            plan = updated
            for proposal_index, branch in enumerate(decision.branch_proposals[: self.teacher_branch_fanout], start=1):
                target_files = tuple(path for path in branch.get("target_files", []) if path in repo_files) or tuple(
                    path for path in localization.candidate_files if path in repo_files
                )
                target_symbols = tuple(str(item).strip() for item in branch.get("target_symbols", []) if str(item).strip())
                diff_sketch = str(branch.get("diff_sketch", "") or "")
                plan_steps = tuple(str(item).strip() for item in branch.get("plan_steps", []) if str(item).strip())
                edit_type = str(branch.get("edit_type", "") or localization.edit_type)
                patch_line_count = _line_count_from_patch(diff_sketch)
                branch_oracle_scores = aggregate_oracle_scores(
                    files=target_files,
                    symbols=target_symbols or localization.candidate_symbols,
                    edit_type=edit_type,
                    patch_line_count=patch_line_count,
                    oracle=oracle,
                )
                branch_rubric_score = score_rubric_alignment(
                    files=target_files,
                    symbols=target_symbols,
                    hypothesis=diff_sketch,
                    rubric=rubric_dict,
                )
                teacher_plan = SwePatchPlanV1(
                    plan_id=self._next_branch_id(base_instance_id=oracle.base_instance_id, stage="plan", seed=f"t{plan.plan_id}-{proposal_index}"),
                    base_instance_id=oracle.base_instance_id,
                    format=self.format,
                    localization_id=localization.candidate_id,
                    target_files=target_files,
                    target_symbols=target_symbols,
                    plan_steps=plan_steps,
                    diff_sketch=diff_sketch,
                    edit_type=edit_type,
                    oracle_scores=branch_oracle_scores,
                    rubric_score=branch_rubric_score,
                    total_score=min(1.0, decision.score * 0.75 + branch_oracle_scores["total"] * 0.2 + branch_rubric_score * 0.05),
                    raw_response=decision.raw_response,
                    metadata={
                        "file_exists": bool(target_files),
                        "existing_files": list(target_files),
                        "source": "teacher",
                        "teacher_shaped": True,
                        "parent_plan_id": plan.plan_id,
                    },
                )
                self.exporter.append_patch_plan(teacher_plan)
                teacher_plans.append(teacher_plan)
                self._append_branch_node(
                    base_instance_id=oracle.base_instance_id,
                    branch_id=teacher_plan.plan_id,
                    parent_branch_id=plan.plan_id,
                    stage="plan",
                    source="teacher",
                    teacher_shaped=True,
                    current_score=teacher_plan.total_score,
                    metadata={"target_files": list(teacher_plan.target_files), "target_symbols": list(teacher_plan.target_symbols)},
                )
        plans.extend(teacher_plans)
        deduped: dict[tuple[tuple[str, ...], tuple[str, ...], str], SwePatchPlanV1] = {}
        for plan in sorted(plans, key=lambda item: item.total_score, reverse=True):
            key = self._plan_key(plan)
            if key not in deduped:
                deduped[key] = plan
        ranked = sorted(deduped.values(), key=lambda item: item.total_score, reverse=True)
        return ranked[: self.max_realizations], len(plans)

    def _capture_numbered_context(
        self,
        *,
        workspace,
        files: tuple[str, ...],
        focus_terms: tuple[str, ...],
        max_lines: int,
    ) -> dict[str, str]:
        contexts: dict[str, str] = {}
        read_context = getattr(workspace, "read_context", None)
        if not callable(read_context):
            return contexts
        for path in files:
            if not path:
                continue
            snippet = read_context(path, focus_terms=focus_terms, max_lines=max_lines)
            if snippet.strip():
                contexts[path] = snippet
        return contexts

    def _realization_context(
        self,
        *,
        task: dict,
        workspace,
        localization: SweLocalizationCandidateV1,
        plan: SwePatchPlanV1,
        oracle: SweIssueOracleV1,
        step_index: int,
        allowed_steps: int,
        last_feedback: str,
    ) -> dict:
        target_files = tuple(dict.fromkeys([*plan.target_files, *localization.candidate_files]))[:2]
        target_symbols = tuple(dict.fromkeys([*plan.target_symbols, *localization.candidate_symbols]))
        related_tests = tuple(path for path in oracle.related_tests if path)[:1]
        span_catalog = workspace.build_span_catalog(target_files, focus_terms=target_symbols)
        return {
            "problem_statement": task.get("problem_statement", ""),
            "repo": task.get("repo", ""),
            "language": task.get("repo_language", ""),
            "context_note": (
                "Numbered prefixes like 0042: are line markers only. "
                "Use them to choose spans, but do not copy them into replacement text."
            ),
            "selected_localization": {
                "candidate_files": list(localization.candidate_files),
                "candidate_symbols": list(localization.candidate_symbols),
                "hypothesis": localization.hypothesis,
                "edit_type": localization.edit_type,
            },
            "selected_patch_plan": {
                "target_files": list(plan.target_files),
                "target_symbols": list(plan.target_symbols),
                "plan_steps": list(plan.plan_steps),
                "diff_sketch": plan.diff_sketch,
                "edit_type": plan.edit_type,
            },
            "file_contexts": self._capture_numbered_context(
                workspace=workspace,
                files=target_files,
                focus_terms=target_symbols,
                max_lines=220,
            ),
            "test_contexts": self._capture_numbered_context(
                workspace=workspace,
                files=related_tests,
                focus_terms=(),
                max_lines=180,
            ),
            "span_catalog": span_catalog,
            "current_diff": workspace.diff_patch(),
            "changed_files": workspace.changed_files(),
            "last_feedback": last_feedback,
            "step_index": step_index,
            "remaining_steps": max(allowed_steps - step_index, 0),
            "edit_constraints": {
                "max_files": 2,
                "max_changed_lines": 80,
                "prefer_local_edit": True,
                "avoid_whole_file_rewrite": True,
            },
        }

    def _capture_step_state(
        self,
        *,
        trajectory_id: str,
        instance_id: str,
        base_instance_id: str,
        step_index: int,
        tool_name: str,
        command: str,
        submit: bool,
        result,
        workspace,
        target_exists: bool = False,
        span_valid: bool = False,
        syntax_ok: bool = False,
        cheap_verify_status: str = "",
        verify_stage: str = "",
        patch_hash: str = "",
        repair_eligible_reason: str = "",
        teacher_online_calls: int = 0,
        teacher_shaped: bool = False,
        hypothesis_id: str = "",
        parent_hypothesis_id: str = "",
        branch_id: str = "",
        parent_branch_id: str = "",
        branch_source: str = "",
        judge_score: float = 0.0,
        judge_stage: str = "",
        judge_decision: str = "",
    ) -> str:
        state = SweStepStateV1(
            state_id=f"{trajectory_id}-s{step_index}",
            trajectory_id=trajectory_id,
            instance_id=instance_id,
            base_instance_id=base_instance_id,
            format=self.format,
            step_index=step_index,
            tool_name=tool_name,
            command=command,
            submit=submit,
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
            target_exists=target_exists,
            span_valid=span_valid,
            syntax_ok=syntax_ok,
            cheap_verify_status=cheap_verify_status,
            verify_stage=verify_stage,
            patch_hash=patch_hash,
            repair_eligible_reason=repair_eligible_reason,
            teacher_online_calls=teacher_online_calls,
            teacher_shaped=teacher_shaped,
            hypothesis_id=hypothesis_id,
            parent_hypothesis_id=parent_hypothesis_id,
            branch_id=branch_id,
            parent_branch_id=parent_branch_id,
            branch_source=branch_source,
            judge_score=judge_score,
            judge_stage=judge_stage,
            judge_decision=judge_decision,
            git_status_short=workspace.git_status_short() if hasattr(workspace, "git_status_short") else "",
            changed_files=tuple(workspace.changed_files()),
            diff_excerpt=(workspace.diff_patch() or "")[:4000],
        )
        return self.exporter.write_step_state(state)

    @staticmethod
    def _span_lookup(span_catalog: list[dict]) -> dict[str, tuple[str, dict, dict]]:
        lookup: dict[str, tuple[str, dict, dict]] = {}
        for file_entry in span_catalog:
            for span in file_entry.get("spans", []):
                lookup[str(span.get("span_id", "") or "")] = (str(file_entry.get("path", "") or ""), file_entry, span)
        return lookup

    def _resolve_patch_action(self, *, action: dict, context: dict) -> tuple[dict, bool, bool]:
        resolved = dict(action)
        span_catalog = list(context.get("span_catalog", []) or [])
        span_lookup = self._span_lookup(span_catalog)
        file_lookup = {str(entry.get("file_id", "") or ""): entry for entry in span_catalog}
        file_by_path = {str(entry.get("path", "") or ""): entry for entry in span_catalog}
        span_id = str(action.get("span_id", "") or "").strip()
        file_id = str(action.get("file_id", "") or "").strip()
        if span_id and span_id in span_lookup:
            target_path, file_entry, span = span_lookup[span_id]
            resolved["resolved_target_file"] = target_path
            resolved["resolved_span"] = {"start_line": int(span.get("start_line", 0) or 0), "end_line": int(span.get("end_line", 0) or 0)}
            resolved["target_file"] = target_path
            resolved["start_line"] = int(span.get("start_line", 0) or 0)
            resolved["end_line"] = int(span.get("end_line", 0) or 0)
            resolved["resolved_file_id"] = str(file_entry.get("file_id", "") or "")
            return resolved, True, True
        file_entry = None
        if file_id and file_id in file_lookup:
            file_entry = file_lookup[file_id]
        elif file_id and file_id in file_by_path:
            file_entry = file_by_path[file_id]
        target_file = str(action.get("target_file", "") or "").strip()
        if file_entry is None and target_file and target_file in file_by_path:
            file_entry = file_by_path[target_file]
        if file_entry is not None:
            target_path = str(file_entry.get("path", "") or "")
            resolved["resolved_target_file"] = target_path
            spans = list(file_entry.get("spans", []) or [])
            if spans:
                chosen_span = spans[0]
                if span_id:
                    digits = "".join(ch for ch in span_id if ch.isdigit())
                    if digits:
                        line_hint = int(digits)
                        for span in spans:
                            if int(span.get("start_line", 0) or 0) <= line_hint <= int(span.get("end_line", 0) or 0):
                                chosen_span = span
                                break
                resolved["resolved_span"] = {"start_line": int(chosen_span.get("start_line", 0) or 0), "end_line": int(chosen_span.get("end_line", 0) or 0)}
                resolved["start_line"] = int(chosen_span.get("start_line", 0) or 0)
                resolved["end_line"] = int(chosen_span.get("end_line", 0) or 0)
                resolved["resolved_file_id"] = str(file_entry.get("file_id", "") or "")
                return resolved, True, True
            return resolved, True, False
        if target_file:
            resolved["resolved_target_file"] = target_file
            return resolved, True, int(action.get("start_line", 0) or 0) > 0
        return resolved, False, False

    @staticmethod
    def _repair_reason(*, changed_files: tuple[str, ...], syntax_ok: bool, oracle: SweIssueOracleV1, rubric: SweIssueRubricV1 | None, plan: SwePatchPlanV1) -> str:
        changed = set(changed_files)
        rubric_hits = set(rubric.likely_modules) if rubric else set()
        if changed & set(plan.target_files) and syntax_ok:
            return "target_file_hit_syntax_ok"
        if changed & set(oracle.touched_files):
            return "oracle_file_hit"
        if changed & rubric_hits:
            return "rubric_module_hit"
        if syntax_ok and changed:
            return "syntax_ok_changed_files"
        return ""

    @staticmethod
    def _action_policy_violation(*, action: dict, context: dict) -> str:
        edit_type = str(action.get("edit_type", "") or "")
        resolved_target = str(action.get("resolved_target_file") or action.get("target_file", "") or "")
        replacement = str(action.get("replacement", "") or "")
        if len(replacement.splitlines()) > 80:
            return "replacement_too_large"
        span_catalog = list(context.get("span_catalog", []) or [])
        file_lookup = {str(entry.get("path", "") or ""): entry for entry in span_catalog}
        file_entry = file_lookup.get(resolved_target)
        line_count = int(file_entry.get("line_count", 0) or 0) if file_entry else 0
        start_line = int((action.get("resolved_span", {}) or {}).get("start_line", action.get("start_line", 0)) or 0)
        if edit_type == "insert_before" and start_line <= 1 and line_count > 80:
            return "top_insert_forbidden"
        scaffold_hits = sum(1 for token in ("module ", "class ", "def ", "require ") if token in replacement)
        if scaffold_hits >= 3 and edit_type != "replace":
            return "skeleton_insert"
        return ""

    def _run_verify_funnel(
        self,
        *,
        task: dict,
        oracle: SweIssueOracleV1,
        workspace,
        verifier: SweTerminalVerifier,
        patch_hash: str,
        cheap_cache: dict[str, tuple[str, str]],
        full_cache: dict[str, VerificationOutcome],
    ) -> tuple[VerificationOutcome, str, str]:
        cheap_status = cheap_cache.get(patch_hash, ("", ""))[0]
        cheap_output = cheap_cache.get(patch_hash, ("", ""))[1]
        if not cheap_status:
            cheap_result = workspace.cheap_targeted_verify(task, oracle.related_tests)
            cheap_output = cheap_result.output
            if "skipped" in cheap_result.output.lower():
                cheap_status = "skipped"
            else:
                cheap_status = "success" if cheap_result.returncode == 0 else "verify_fail"
            cheap_cache[patch_hash] = (cheap_status, cheap_output)
        if cheap_status == "verify_fail":
            return (
                VerificationOutcome(
                    verified=False,
                    status="verify_fail",
                    output=cheap_output,
                    passed_tests=(),
                    failed_tests=(),
                    changed_files=tuple(workspace.changed_files()),
                ),
                cheap_status,
                "cheap",
            )
        if patch_hash not in full_cache:
            full_cache[patch_hash] = verifier.verify(workspace=workspace)
        return full_cache[patch_hash], cheap_status, "full"

    def _realization_messages(self, *, task: dict, localization: SweLocalizationCandidateV1, plan: SwePatchPlanV1) -> list[dict]:
        messages = self.student_session.initial_messages(task)
        messages.append(
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "selected_localization": {
                            "candidate_files": list(localization.candidate_files),
                            "candidate_symbols": list(localization.candidate_symbols),
                            "hypothesis": localization.hypothesis,
                            "edit_type": localization.edit_type,
                        },
                        "selected_patch_plan": {
                            "target_files": list(plan.target_files),
                            "target_symbols": list(plan.target_symbols),
                            "plan_steps": list(plan.plan_steps),
                            "diff_sketch": plan.diff_sketch,
                            "edit_type": plan.edit_type,
                        },
                        "instruction": (
                            "Realize this patch plan in the repository. Prefer the selected files. "
                            "Do not restart localization from scratch. Keep commands short and local. "
                            "Prefer inspect-then-edit, avoid rewriting whole files, and avoid giant one-shot here-doc commands. "
                            "The shell-turn budget is very small, so start editing no later than the second command."
                        ),
                    },
                    ensure_ascii=False,
                ),
            }
        )
        return messages

    def _quality_status(
        self,
        *,
        workspace,
        oracle: SweIssueOracleV1,
        plan: SwePatchPlanV1,
    ) -> tuple[str, dict[str, float]]:
        changed_files = tuple(workspace.changed_files())
        if not changed_files:
            return "no_patch", {"file_overlap": 0.0, "symbol_overlap": 0.0, "edit_type": 0.0, "patch_size": 0.0, "total": 0.0}
        diff_patch = workspace.diff_patch()
        scores = aggregate_oracle_scores(
            files=changed_files,
            symbols=plan.target_symbols,
            edit_type=plan.edit_type,
            patch_line_count=_line_count_from_patch(diff_patch),
            oracle=oracle,
        )
        if plan.target_files and not (set(changed_files) & set(plan.target_files)):
            return "quality_fail", scores
        if len(changed_files) > 2:
            return "quality_fail", scores
        if _line_count_from_patch(diff_patch) > 80:
            return "quality_fail", scores
        if scores["file_overlap"] < 0.1:
            return "quality_fail", scores
        return "", scores

    @staticmethod
    def _teacher_action_turn(action: dict):
        edit_type = str(action.get("edit_type", "") or "no_action")
        action_state = "no_action" if edit_type == "no_action" else "ok"
        return type(
            "TeacherActionTurn",
            (),
            {
                "assistant_message": {
                    "role": "assistant",
                    "content": "Teacher online branch action",
                    "tool_calls": [
                        {
                            "id": f"teacher_patch_{uuid.uuid4().hex[:6]}",
                            "function": {
                                "name": "apply_patch_action",
                                "arguments": action,
                            },
                        }
                    ],
                },
                "submit": bool(action.get("submit", False)),
                "action_state": action_state,
                "tool_name": "apply_patch_action",
                "action": dict(action),
                "command": "",
            },
        )()

    def _make_root_search_node(
        self,
        *,
        task: dict,
        localization: SweLocalizationCandidateV1,
        localization_rank: int,
        plan: SwePatchPlanV1,
        plan_rank: int,
        base_checkpoint: SweWorkspaceCheckpointV1,
    ) -> dict:
        teacher_shaped = bool(plan.metadata.get("teacher_shaped", False) or localization.metadata.get("teacher_shaped", False))
        source = str(plan.metadata.get("source", localization.metadata.get("source", "student")) or "student")
        hypothesis_id = self._next_branch_id(base_instance_id=task.get("instance_id", ""), stage="hyp")
        node = {
            "node_id": plan.plan_id or self._next_branch_id(base_instance_id=task.get("instance_id", ""), stage="realize"),
            "base_instance_id": task.get("instance_id", ""),
            "checkpoint_id": base_checkpoint.checkpoint_id,
            "parent_node_id": "",
            "hypothesis_id": hypothesis_id,
            "parent_hypothesis_id": "",
            "best_checkpoint_id": base_checkpoint.checkpoint_id,
            "best_hypothesis_id": hypothesis_id,
            "trajectory_id": "",
            "localization": localization,
            "plan": plan,
            "localization_rank": localization_rank,
            "plan_rank": plan_rank,
            "root_round": 1,
            "is_root": True,
            "root_race_rounds_used": 0,
            "messages": self._realization_messages(task=task, localization=localization, plan=plan),
            "raw_log": [],
            "state_paths": [],
            "attempts_used": 0,
            "visit_count": 0,
            "prior_score": float(plan.total_score or 0.0),
            "value_mean": 0.0,
            "selection_score": float(plan.total_score or 0.0),
            "selection_tier": 0,
            "value_vector": self._empty_value_vector(),
            "last_action": {},
            "last_feedback": "",
            "teacher_shaped": teacher_shaped,
            "teacher_summary_calls": 0,
            "cached_teacher_hypotheses": [],
            "submit_candidate": False,
            "terminal_status": "",
            "terminal_detail": "",
            "terminal_output": "",
            "verification": VerificationOutcome(
                verified=False,
                status="max_steps",
                output="",
                passed_tests=(),
                failed_tests=(),
                changed_files=(),
            ),
            "full_verified": False,
            "syntax_ok": False,
            "cheap_verify_status": "",
            "verify_stage": "",
            "repair_eligible_reason": "",
            "oracle_scores": {},
            "patch_hash": base_checkpoint.patch_hash,
            "changed_files": tuple(base_checkpoint.changed_files),
            "source": source,
            "summary_ids": [],
            "emitted": False,
            "metadata": {
                "source": source,
                "teacher_shaped": teacher_shaped,
                "localization_id": localization.candidate_id,
                "plan_id": plan.plan_id,
            },
        }
        root_hypothesis = SweRepairHypothesisV1(
            hypothesis_id=hypothesis_id,
            base_instance_id=task.get("instance_id", ""),
            checkpoint_id=base_checkpoint.checkpoint_id,
            parent_hypothesis_id="",
            trajectory_id="",
            node_id=node["node_id"],
            format=self.format,
            source=source,
            teacher_shaped=teacher_shaped,
            target_file_ids=tuple(plan.target_files or localization.candidate_files),
            target_span_ids=(),
            root_cause_guess=localization.hypothesis,
            minimal_edit_direction=plan.diff_sketch or "realize the shortlisted patch plan",
            expected_fix_type=plan.edit_type or localization.edit_type,
            supporting_evidence=tuple(item for item in [localization.hypothesis, *plan.plan_steps] if item),
            prior_score=float(plan.total_score or 0.0),
            value_score=0.0,
            raw_response=plan.raw_response,
            metadata={
                "localization_id": localization.candidate_id,
                "plan_id": plan.plan_id,
                "root": True,
            },
        )
        self._append_hypothesis(root_hypothesis)
        self._append_search_node_record(node)
        self._append_branch_node(
            base_instance_id=node["base_instance_id"],
            branch_id=node["node_id"],
            stage="realization",
            source=source,
            teacher_shaped=teacher_shaped,
            current_score=node["selection_score"],
            patch_hash=node["patch_hash"],
            changed_files=node["changed_files"],
            metadata={
                "localization_id": localization.candidate_id,
                "plan_id": plan.plan_id,
            },
        )
        self.root_nodes_total += 1
        return node

    def _build_hypothesis_record(
        self,
        *,
        task: dict,
        checkpoint_id: str,
        node_id: str,
        parent_hypothesis_id: str,
        source: str,
        teacher_shaped: bool,
        payload: dict,
        raw_response: str = "",
    ) -> SweRepairHypothesisV1:
        return SweRepairHypothesisV1(
            hypothesis_id=self._next_branch_id(base_instance_id=task.get("instance_id", ""), stage="hyp"),
            base_instance_id=task.get("instance_id", ""),
            checkpoint_id=checkpoint_id,
            parent_hypothesis_id=parent_hypothesis_id,
            trajectory_id="",
            node_id=node_id,
            format=self.format,
            source=source,
            teacher_shaped=teacher_shaped,
            target_file_ids=tuple(str(item).strip() for item in payload.get("target_file_ids", []) if str(item).strip()),
            target_span_ids=tuple(str(item).strip() for item in payload.get("target_span_ids", []) if str(item).strip()),
            root_cause_guess=str(payload.get("root_cause_guess", "") or "").strip(),
            minimal_edit_direction=str(payload.get("minimal_edit_direction", "") or "").strip(),
            expected_fix_type=str(payload.get("expected_fix_type", payload.get("edit_type", "unknown")) or "unknown").strip() or "unknown",
            supporting_evidence=tuple(str(item).strip() for item in payload.get("supporting_evidence", []) if str(item).strip()),
            prior_score=_safe_float(payload.get("prior_score", 0.0)),
            value_score=_safe_float(payload.get("value_score", 0.0)),
            raw_response=raw_response,
            metadata=dict(payload.get("metadata", {}) or {}),
        )

    def _root_race_active(self, live_nodes: list[dict]) -> bool:
        return any(
            bool(node.get("is_root", False))
            and not node.get("terminal_status")
            and int(node.get("attempts_used", 0)) < self.attempts_per_node
            and int(node.get("root_race_rounds_used", 0)) < self.root_race_rounds
            for node in live_nodes
        )

    def _prune_root_race_frontier(self, live_nodes: list[dict], emitted_nodes: list[dict]) -> None:
        roots = [node for node in live_nodes if bool(node.get("is_root", False)) and not node.get("terminal_status")]
        if len(roots) <= self.root_race_keep:
            return
        deduped: dict[str, dict] = {}
        for node in sorted(
            roots,
            key=lambda item: (
                int(item.get("selection_tier", 0) or 0),
                float(item.get("value_mean", 0.0) or 0.0),
                float(item.get("selection_score", 0.0) or 0.0),
            ),
            reverse=True,
        ):
            novelty_key = str(node.get("patch_hash", "") or f"node:{node['node_id']}")
            if novelty_key not in deduped:
                deduped[novelty_key] = node
        keep = set(node["node_id"] for node in list(deduped.values())[: self.root_race_keep])
        for node in list(roots):
            if node["node_id"] in keep:
                continue
            node["terminal_status"] = node.get("terminal_status") or "quality_fail"
            node["terminal_detail"] = node.get("terminal_detail") or "root_race_pruned"
            live_nodes.remove(node)
            emitted_nodes.append(node)

    def _update_node_from_summary(self, *, node: dict, summary: SweTeacherStateSummaryV2 | None, parent_visits: int = 0) -> None:
        if summary is None:
            node["selection_score"] = self._progressive_selection_score(
                tier_score=self._tier_score(int(node.get("selection_tier", 0) or 0)),
                empirical_value=float(node.get("value_mean", 0.0) or 0.0),
                teacher_prior=float(node.get("prior_score", 0.0) or 0.0),
                visit_count=int(node.get("visit_count", 0)),
                parent_visits=parent_visits,
                submit_candidate=bool(node.get("submit_candidate", False)),
            )
            return
        node["teacher_summary_calls"] = int(node.get("teacher_summary_calls", 0)) + 1
        node["summary_ids"].append(summary.summary_id)
        node["prior_score"] = max(float(node.get("prior_score", 0.0) or 0.0), float(summary.prior_score or 0.0))
        node["value_mean"] = max(float(node.get("value_mean", 0.0) or 0.0), float(summary.value_score or 0.0))
        node["submit_candidate"] = bool(node.get("submit_candidate", False) or summary.submit_likelihood >= 0.65)
        node["cached_teacher_hypotheses"] = [dict(item) for item in summary.branch_proposals[: self.teacher_branch_fanout]]
        node["last_feedback"] = str(summary.minimal_edit_direction or node.get("last_feedback", "") or "")
        node["metadata"] = {
            **dict(node.get("metadata", {}) or {}),
            "root_cause_guess": summary.root_cause_guess,
            "target_file_ids": list(summary.target_file_ids),
            "target_span_ids": list(summary.target_span_ids),
            "submit_likelihood": summary.submit_likelihood,
            "dead_end_risk": summary.dead_end_risk,
        }
        node["selection_score"] = self._progressive_selection_score(
            tier_score=self._tier_score(int(node.get("selection_tier", 0) or 0)),
            empirical_value=float(node["value_mean"]),
            teacher_prior=float(node["prior_score"]),
            visit_count=int(node.get("visit_count", 0)),
            parent_visits=parent_visits,
            submit_candidate=bool(node["submit_candidate"]),
        )
        self._append_search_node_record(node)

    @staticmethod
    def _node_reward(node: dict) -> float:
        verification: VerificationOutcome = node.get("verification") or VerificationOutcome(
            verified=False,
            status="max_steps",
            output="",
            passed_tests=(),
            failed_tests=(),
            changed_files=(),
        )
        changed_files = tuple(node.get("changed_files", ()) or ())
        if verification.verified:
            return 1.0
        if node.get("full_verified") and changed_files:
            return 0.55
        if str(node.get("cheap_verify_status", "") or "") == "verify_fail" and bool(node.get("syntax_ok", False)):
            return 0.45
        if str(node.get("terminal_detail", "") or "") == "syntax_fail" and changed_files:
            return 0.20
        return 0.0

    def _finalize_search_node(
        self,
        *,
        task: dict,
        oracle: SweIssueOracleV1,
        rubric: SweIssueRubricV1 | None,
        node: dict,
        checkpoints_by_id: dict[str, SweWorkspaceCheckpointV1],
    ) -> SweRawTrajectoryV1:
        if node.get("emitted", False):
            raise RuntimeError("search node already emitted")
        checkpoint = checkpoints_by_id[node["checkpoint_id"]]
        verification: VerificationOutcome = node.get("verification") or VerificationOutcome(
            verified=False,
            status="max_steps",
            output="",
            passed_tests=(),
            failed_tests=(),
            changed_files=(),
        )
        instance_id = _sample_instance_id(
            task.get("instance_id", ""),
            int(node.get("localization_rank", 1)),
            int(node.get("plan_rank", 1)),
            int(node.get("root_round", 1)),
        )
        trajectory_id = node.get("trajectory_id") or f"{instance_id}-{uuid.uuid4().hex[:8]}"
        node["trajectory_id"] = trajectory_id
        changed_files = tuple(node.get("changed_files", checkpoint.changed_files))
        repair_eligible_reason = str(node.get("repair_eligible_reason", "") or "")
        terminal_status = str(node.get("terminal_status", "") or "")
        terminal_detail = str(node.get("terminal_detail", "") or "")
        if not terminal_status:
            if verification.verified:
                terminal_status = "success"
            elif bool(node.get("full_verified", False)) and verification.status not in {"", "max_steps"}:
                terminal_status = verification.status
            elif str(node.get("cheap_verify_status", "") or "") == "verify_fail" and bool(node.get("syntax_ok", False)):
                terminal_status = "verify_fail"
            elif terminal_detail == "syntax_fail" and changed_files:
                terminal_status = "quality_fail"
            elif checkpoint.patch_hash:
                terminal_status = "quality_fail"
            else:
                terminal_status = "no_patch"
        near_miss = bool(changed_files) and bool(repair_eligible_reason) and terminal_status in {"verify_fail", "quality_fail"} and not _is_collector_side_no_patch(terminal_detail)
        raw_log_path = self.exporter.write_raw_log(trajectory_id=trajectory_id, raw_log="\n".join(node.get("raw_log", [])))
        trajectory = SweRawTrajectoryV1(
            trajectory_id=trajectory_id,
            run_id=self.run_id,
            instance_id=instance_id,
            base_instance_id=task.get("instance_id", ""),
            repo=task.get("repo", ""),
            language=task.get("repo_language", ""),
            format=self.format,
            sampling_temperature=self.temps[(int(node.get("plan_rank", 1)) - 1) % len(self.temps)],
            student_model=self.student_session.model,
            student_endpoint=self.student_session.endpoint,
            collector=self.collector_name,
            teacher_calls=(1 if rubric is not None else 0) + int(node.get("teacher_summary_calls", 0)),
            repair_round=0,
            rubric_score=float(node["plan"].rubric_score),
            oracle_scores=dict(node.get("oracle_scores", {}) or {}),
            localization_id=node["localization"].candidate_id,
            plan_id=node["plan"].plan_id,
            messages=tuple(ConversationMessage.model_validate(message) for message in node.get("messages", [])),
            state_paths=tuple(node.get("state_paths", [])),
            final_patch=checkpoint.diff_patch,
            terminal_status=terminal_status,
            terminal_detail=terminal_detail,
            verify_passed=bool(verification.verified),
            patch_hash=checkpoint.patch_hash,
            syntax_ok=bool(node.get("syntax_ok", False)),
            cheap_verify_status=str(node.get("cheap_verify_status", "") or ""),
            verify_stage=str(node.get("verify_stage", "") or ""),
            repair_eligible_reason=repair_eligible_reason,
            teacher_online_calls=int(node.get("teacher_summary_calls", 0)),
            teacher_shaped=bool(node.get("teacher_shaped", False)),
            hypothesis_id=str(node.get("best_hypothesis_id", node.get("hypothesis_id", "")) or ""),
            parent_hypothesis_id=str(node.get("parent_hypothesis_id", "") or ""),
            branch_id=node["node_id"],
            parent_branch_id=str(node.get("parent_node_id", "") or ""),
            branch_source=str(node.get("source", "") or ""),
            judge_score=float(node.get("value_mean", 0.0) or 0.0),
            judge_stage="realization_summary",
            judge_decision="submit_candidate" if node.get("submit_candidate", False) else terminal_status,
            terminal_output=str(node.get("terminal_output", verification.output) or verification.output or ""),
            assistant_turns=sum(1 for message in node.get("messages", []) if message.get("role") == "assistant"),
            changed_files=changed_files,
            rubric_enabled=bool(rubric is not None),
            rubric_degraded_reason="" if rubric is not None else self.rubric_degraded_reason,
            task_metadata=_task_metadata(
                task,
                verification,
                failed_tests=verification.failed_tests,
                passed_tests=verification.passed_tests,
                near_miss=near_miss,
                rubric_enabled=bool(rubric is not None),
                rubric_degraded_reason="" if rubric is not None else self.rubric_degraded_reason,
                terminal_detail=terminal_detail,
                localization_id=node["localization"].candidate_id,
                plan_id=node["plan"].plan_id,
                rubric_id=rubric.rubric_id if rubric is not None else "",
            ),
            raw_log_path=raw_log_path,
        )
        self.exporter.append_raw_trajectory(trajectory)
        node["emitted"] = True
        if trajectory.verify_passed and trajectory.teacher_shaped:
            self.teacher_shaped_successes += 1
        return trajectory

    def _select_live_node(self, live_nodes: list[dict]) -> dict | None:
        candidates = [node for node in live_nodes if not node.get("terminal_status") and int(node.get("attempts_used", 0)) < self.attempts_per_node]
        if not candidates:
            return None
        if self._root_race_active(live_nodes):
            raced = [node for node in candidates if bool(node.get("is_root", False)) and int(node.get("root_race_rounds_used", 0)) < self.root_race_rounds]
            if raced:
                raced.sort(
                    key=lambda item: (
                        int(item.get("root_race_rounds_used", 0)),
                        int(item.get("attempts_used", 0)),
                        int(item.get("plan_rank", 0)),
                    )
                )
                return raced[0]
        parent_visits = sum(int(node.get("visit_count", 0)) for node in live_nodes)
        for node in candidates:
            node["selection_score"] = self._progressive_selection_score(
                tier_score=self._tier_score(int(node.get("selection_tier", 0) or 0)),
                empirical_value=float(node.get("value_mean", 0.0) or 0.0),
                teacher_prior=float(node.get("prior_score", 0.0) or 0.0),
                visit_count=int(node.get("visit_count", 0)),
                parent_visits=parent_visits,
                submit_candidate=bool(node.get("submit_candidate", False)),
            )
        candidates.sort(
            key=lambda item: (
                int(item.get("selection_tier", 0) or 0),
                float(item.get("selection_score", 0.0) or 0.0),
                float(item.get("value_mean", 0.0) or 0.0),
            ),
            reverse=True,
        )
        return candidates[0]

    def _default_hypothesis_payload(self, *, node: dict, context: dict) -> dict:
        span_catalog = list(context.get("span_catalog", []) or [])
        span_ids: list[str] = []
        for file_entry in span_catalog[:1]:
            spans = list(file_entry.get("spans", []) or [])
            if spans:
                span_ids.append(str(spans[0].get("span_id", "") or ""))
        supporting = [str(node["localization"].hypothesis or "").strip(), *[str(step).strip() for step in node["plan"].plan_steps if str(step).strip()]]
        return {
            "target_file_ids": list(node["plan"].target_files or node["localization"].candidate_files),
            "target_span_ids": span_ids,
            "root_cause_guess": str(node["localization"].hypothesis or "").strip(),
            "minimal_edit_direction": str(node.get("last_feedback", "") or node["plan"].diff_sketch or "apply a minimal local fix").strip(),
            "expected_fix_type": str(node["plan"].edit_type or node["localization"].edit_type or "unknown"),
            "supporting_evidence": supporting,
            "prior_score": _safe_float(node.get("prior_score", 0.0)),
            "value_score": _safe_float(node.get("value_mean", 0.0)),
            "metadata": {"fallback": True},
        }

    def _next_hypothesis_for_node(self, *, task: dict, node: dict, checkpoint: SweWorkspaceCheckpointV1, context: dict, attempt_index: int):
        if attempt_index == 1 and node.get("cached_teacher_hypotheses"):
            payload = dict(node["cached_teacher_hypotheses"].pop(0))
            payload.setdefault("target_file_ids", list(node["plan"].target_files or node["localization"].candidate_files))
            hypothesis = self._build_hypothesis_record(
                task=task,
                checkpoint_id=checkpoint.checkpoint_id,
                node_id=node["node_id"],
                parent_hypothesis_id=str(node.get("hypothesis_id", "") or ""),
                source="teacher",
                teacher_shaped=True,
                payload=payload,
                raw_response=str(node.get("summary_ids", [])[-1] if node.get("summary_ids") else ""),
            )
            self._append_hypothesis(hypothesis)
            return hypothesis
        propose = getattr(self.student_session, "propose_repair_hypothesis", None)
        if callable(propose):
            temperature = self.temps[attempt_index % len(self.temps)]
            proposal = propose(task=task, context=context, temperature=temperature)
            payload = {
                "target_file_ids": list(proposal.target_file_ids),
                "target_span_ids": list(proposal.target_span_ids),
                "root_cause_guess": proposal.root_cause_guess,
                "minimal_edit_direction": proposal.minimal_edit_direction,
                "expected_fix_type": proposal.expected_fix_type,
                "supporting_evidence": list(proposal.supporting_evidence),
                "prior_score": proposal.prior_score,
                "value_score": proposal.value_score,
            }
            hypothesis = self._build_hypothesis_record(
                task=task,
                checkpoint_id=checkpoint.checkpoint_id,
                node_id=node["node_id"],
                parent_hypothesis_id=str(node.get("hypothesis_id", "") or ""),
                source="student",
                teacher_shaped=bool(node.get("teacher_shaped", False)),
                payload=payload,
                raw_response=proposal.raw_response,
            )
            self._append_hypothesis(hypothesis)
            return hypothesis
        fallback = self._default_hypothesis_payload(node=node, context=context)
        hypothesis = self._build_hypothesis_record(
            task=task,
            checkpoint_id=checkpoint.checkpoint_id,
            node_id=node["node_id"],
            parent_hypothesis_id=str(node.get("hypothesis_id", "") or ""),
            source="student",
            teacher_shaped=bool(node.get("teacher_shaped", False)),
            payload=fallback,
            raw_response="",
        )
        self._append_hypothesis(hypothesis)
        return hypothesis

    def _realize_hypothesis_turn(self, *, task: dict, context: dict, hypothesis: SweRepairHypothesisV1, attempt_index: int):
        context = dict(context)
        if attempt_index >= 2:
            context["last_feedback"] = (
                str(context.get("last_feedback", "") or "") + "\nDo not inspect again. Emit one minimal structured patch action now."
            ).strip()
        realize = getattr(self.student_session, "realize_repair_hypothesis", None)
        if callable(realize):
            return realize(
                task=task,
                context=context,
                hypothesis={
                    "hypothesis_id": hypothesis.hypothesis_id,
                    "target_file_ids": list(hypothesis.target_file_ids),
                    "target_span_ids": list(hypothesis.target_span_ids),
                    "root_cause_guess": hypothesis.root_cause_guess,
                    "minimal_edit_direction": hypothesis.minimal_edit_direction,
                    "expected_fix_type": hypothesis.expected_fix_type,
                    "supporting_evidence": list(hypothesis.supporting_evidence),
                    "prior_score": hypothesis.prior_score,
                    "value_score": hypothesis.value_score,
                },
                temperature=self.temps[attempt_index % len(self.temps)],
            )
        return self.student_session.realize_patch_action(
            task=task,
            context=context,
            temperature=self.temps[attempt_index % len(self.temps)],
        )

    def _sample_task_tree(
        self,
        *,
        task: dict,
        localizations: list[SweLocalizationCandidateV1],
        plans: list[SwePatchPlanV1],
        oracle: SweIssueOracleV1,
        rubric: SweIssueRubricV1 | None,
        rubric_enabled: bool,
        rubric_degraded_reason: str,
    ) -> list[SweRawTrajectoryV1]:
        if not plans:
            return []
        trajectories: list[SweRawTrajectoryV1] = []
        workspace = self.runtime.create_workspace(task)
        verifier = SweTerminalVerifier(task)
        checkpoints_by_id: dict[str, SweWorkspaceCheckpointV1] = {}
        emitted_nodes: list[dict] = []
        live_nodes: list[dict] = []
        seen_patch_hashes: set[str] = set()
        verified_patch_hashes: set[str] = set()
        full_cache: dict[str, VerificationOutcome] = {}
        cheap_cache: dict[str, tuple[str, str]] = {}
        full_verify_used = 0
        expansions = 0
        try:
            base_checkpoint = workspace.capture_checkpoint(base_instance_id=task.get("instance_id", ""))
            checkpoints_by_id[base_checkpoint.checkpoint_id] = base_checkpoint
            self._append_checkpoint(base_checkpoint)
            localization_by_id = {candidate.candidate_id: candidate for candidate in localizations}
            shortlisted = plans[: self.max_realizations]
            for plan_rank, plan in enumerate(shortlisted, start=1):
                localization = localization_by_id.get(plan.localization_id)
                if localization is None:
                    continue
                loc_rank = localizations.index(localization) + 1
                live_nodes.append(
                    self._make_root_search_node(
                        task=task,
                        localization=localization,
                        localization_rank=loc_rank,
                        plan=plan,
                        plan_rank=plan_rank,
                        base_checkpoint=base_checkpoint,
                    )
                )

            while expansions < self.search_node_budget and live_nodes:
                node = self._select_live_node(live_nodes)
                if node is None:
                    break
                checkpoint = checkpoints_by_id[node["checkpoint_id"]]
                restore = workspace.restore_checkpoint(checkpoint)
                if restore.returncode != 0:
                    node["terminal_status"] = "infra_fail"
                    node["terminal_detail"] = "restore_failed"
                    node["terminal_output"] = restore.output
                    live_nodes.remove(node)
                    emitted_nodes.append(node)
                    self._append_search_node_record(node)
                    continue
                expansions += 1
                node["visit_count"] = int(node.get("visit_count", 0)) + 1
                if bool(node.get("is_root", False)) and int(node.get("root_race_rounds_used", 0)) < self.root_race_rounds:
                    node["root_race_rounds_used"] = int(node.get("root_race_rounds_used", 0)) + 1
                    self.root_race_rounds_run = max(self.root_race_rounds_run, int(node["root_race_rounds_used"]))
                attempt_index = int(node.get("attempts_used", 0))
                context = self._realization_context(
                    task=task,
                    workspace=workspace,
                    localization=node["localization"],
                    plan=node["plan"],
                    oracle=oracle,
                    step_index=attempt_index,
                    allowed_steps=self.max_steps,
                    last_feedback=str(node.get("last_feedback", "") or ""),
                )
                if not node.get("summary_ids"):
                    summary = self._teacher_summary_for_node(
                        task=task,
                        oracle=oracle,
                        rubric=rubric,
                        checkpoint=checkpoint,
                        span_catalog=list(context.get("span_catalog", []) or []),
                        node=node,
                    )
                    self._update_node_from_summary(
                        node=node,
                        summary=summary,
                        parent_visits=sum(int(item.get("visit_count", 0)) for item in live_nodes),
                    )
                    context = self._realization_context(
                        task=task,
                        workspace=workspace,
                        localization=node["localization"],
                        plan=node["plan"],
                        oracle=oracle,
                        step_index=attempt_index,
                        allowed_steps=self.max_steps,
                        last_feedback=str(node.get("last_feedback", "") or ""),
                    )
                hypothesis = self._next_hypothesis_for_node(
                    task=task,
                    node=node,
                    checkpoint=checkpoint,
                    context=context,
                    attempt_index=attempt_index,
                )
                node["hypothesis_id"] = hypothesis.hypothesis_id
                node["parent_hypothesis_id"] = hypothesis.parent_hypothesis_id
                node["best_hypothesis_id"] = str(node.get("best_hypothesis_id", "") or hypothesis.hypothesis_id)
                if hypothesis.source == "teacher":
                    node["teacher_shaped"] = True
                    node["source"] = "teacher"

                structured_mode = callable(getattr(self.student_session, "realize_repair_hypothesis", None)) and hasattr(workspace, "apply_patch_action")
                if structured_mode:
                    turn = self._realize_hypothesis_turn(
                        task=task,
                        context=context,
                        hypothesis=hypothesis,
                        attempt_index=attempt_index,
                    )
                else:
                    turn = self.student_session.next_turn(
                        task=task,
                        messages=node["messages"],
                        temperature=self.temps[attempt_index % len(self.temps)],
                    )
                node["messages"] = [*node["messages"], turn.assistant_message]
                node["raw_log"].append(turn.assistant_message.get("content", ""))
                tool_name = getattr(turn, "tool_name", "shell")
                action = getattr(turn, "action", None)
                command_repr = getattr(turn, "command", "") or ""
                target_exists = False
                span_valid = False
                terminal_detail = ""

                if structured_mode and tool_name == "apply_patch_action":
                    action_state = getattr(turn, "action_state", "") or "parse_fail"
                    if action_state == "no_action":
                        result = type("Result", (), {"stdout": "no_action", "stderr": "", "output": "no_action", "returncode": 0})()
                        command_repr = workspace.render_patch_action(action or {"edit_type": "no_action"})
                        terminal_detail = "no_action"
                    elif action_state != "ok" or not isinstance(action, dict):
                        result = type("Result", (), {"stdout": "", "stderr": action_state, "output": action_state, "returncode": 1})()
                        command_repr = workspace.render_patch_action(action or {})
                        terminal_detail = action_state
                    else:
                        resolved_action, target_exists, span_valid = self._resolve_patch_action(action=action, context=context)
                        violation = self._action_policy_violation(action=resolved_action, context=context) if target_exists and span_valid else ""
                        command_repr = workspace.render_patch_action(resolved_action)
                        if not target_exists:
                            result = type("Result", (), {"stdout": "", "stderr": "target_file does not exist", "output": "target_file does not exist", "returncode": 1})()
                            terminal_detail = "invalid_target"
                        elif not span_valid:
                            result = type("Result", (), {"stdout": "", "stderr": "invalid span", "output": "invalid span", "returncode": 1})()
                            terminal_detail = "invalid_span"
                        elif violation:
                            result = type("Result", (), {"stdout": "", "stderr": violation, "output": violation, "returncode": 1})()
                            terminal_detail = violation
                        else:
                            result = workspace.apply_patch_action(resolved_action, timeout=120)
                elif not turn.command.strip():
                    result = type("Result", (), {"stdout": "", "stderr": "no_action", "output": "no_action", "returncode": 1})()
                    terminal_detail = "no_action"
                else:
                    result = workspace.exec(f"cd /app && {turn.command}", timeout=120)

                node["raw_log"].append(result.output)
                node["messages"] = [*node["messages"], self.student_session.observation_message(turn=turn, output=result.output, returncode=result.returncode)]
                current_hash = workspace.patch_hash()
                changed_files = tuple(workspace.changed_files())
                node["attempts_used"] = attempt_index + 1
                node["last_action"] = {
                    "tool_name": tool_name,
                    "command": command_repr,
                    "submit": bool(getattr(turn, "submit", False)),
                    "action": dict(action or {}),
                    "hypothesis_id": hypothesis.hypothesis_id,
                }
                node["patch_hash"] = current_hash
                node["changed_files"] = changed_files

                if terminal_detail == "no_action" and checkpoint.patch_hash and bool(node.get("syntax_ok", False)):
                    if checkpoint.patch_hash not in verified_patch_hashes and full_verify_used < self.full_verify_budget:
                        verification = verifier.verify(workspace=workspace)
                        full_cache[checkpoint.patch_hash] = verification
                        verified_patch_hashes.add(checkpoint.patch_hash)
                        full_verify_used += 1
                        node["verification"] = verification
                        node["full_verified"] = True
                        node["terminal_output"] = verification.output
                        node["terminal_status"] = verification.status
                        node["verify_stage"] = "full"
                        node["terminal_detail"] = terminal_detail
                        self._update_node_value_vector(node)
                        live_nodes.remove(node)
                        emitted_nodes.append(node)
                        self._append_search_node_record(node)
                        if not self._root_race_active(live_nodes):
                            self._prune_root_race_frontier(live_nodes, emitted_nodes)
                        continue

                if current_hash and current_hash == checkpoint.patch_hash:
                    terminal_detail = terminal_detail or "duplicate_patch"

                if terminal_detail in {
                    "invalid_target",
                    "invalid_span",
                    "no_action",
                    "parse_fail",
                    "top_insert_forbidden",
                    "skeleton_insert",
                    "replacement_too_large",
                    "duplicate_patch",
                }:
                    node["terminal_detail"] = terminal_detail
                    node["terminal_status"] = ""
                    node["last_feedback"] = "Emit a concrete minimal patch action on the next attempt."
                    state_path = self._capture_step_state(
                        trajectory_id=node.get("trajectory_id", node["node_id"]),
                        instance_id=_sample_instance_id(
                            task.get("instance_id", ""),
                            int(node.get("localization_rank", 1)),
                            int(node.get("plan_rank", 1)),
                            int(node.get("root_round", 1)),
                        ),
                        base_instance_id=task.get("instance_id", ""),
                        step_index=len(node["state_paths"]),
                        tool_name=tool_name,
                        command=command_repr,
                        submit=False,
                        result=result,
                        workspace=workspace,
                        target_exists=target_exists,
                        span_valid=span_valid,
                        syntax_ok=bool(node.get("syntax_ok", False)),
                        cheap_verify_status=str(node.get("cheap_verify_status", "") or ""),
                        verify_stage=str(node.get("verify_stage", "") or ""),
                        patch_hash=current_hash,
                        repair_eligible_reason=str(node.get("repair_eligible_reason", "") or ""),
                        teacher_online_calls=int(node.get("teacher_summary_calls", 0)),
                        teacher_shaped=bool(node.get("teacher_shaped", False)),
                        hypothesis_id=hypothesis.hypothesis_id,
                        parent_hypothesis_id=hypothesis.parent_hypothesis_id,
                        branch_id=node["node_id"],
                        parent_branch_id=str(node.get("parent_node_id", "") or ""),
                        branch_source=str(node.get("source", "") or ""),
                        judge_score=float(node.get("value_mean", 0.0) or 0.0),
                        judge_stage="realization_summary",
                        judge_decision=node["terminal_status"],
                    )
                    node["state_paths"].append(state_path)
                    self._update_node_value_vector(node)
                    self._append_search_node_record(node)
                    if int(node["attempts_used"]) >= self.attempts_per_node:
                        if bool(node.get("full_verified", False)) and node.get("verification") and node["verification"].status not in {"", "max_steps"}:
                            node["terminal_status"] = node["verification"].status
                        elif str(node.get("cheap_verify_status", "") or "") == "verify_fail" and bool(node.get("syntax_ok", False)):
                            node["terminal_status"] = "verify_fail"
                        else:
                            node["terminal_status"] = "no_patch" if not checkpoint.patch_hash else "quality_fail"
                        live_nodes.remove(node)
                        emitted_nodes.append(node)
                    if not self._root_race_active(live_nodes):
                        self._prune_root_race_frontier(live_nodes, emitted_nodes)
                    continue

                syntax_result = workspace.syntax_check(task.get("repo_language", ""), list(changed_files), timeout=120)
                node["raw_log"].append(syntax_result.output)
                child_checkpoint = workspace.capture_checkpoint(
                    base_instance_id=task.get("instance_id", ""),
                    parent_checkpoint_id=checkpoint.checkpoint_id,
                )
                checkpoints_by_id[child_checkpoint.checkpoint_id] = child_checkpoint
                self._append_checkpoint(child_checkpoint)
                child_oracle_scores = aggregate_oracle_scores(
                    files=changed_files,
                    symbols=node["plan"].target_symbols,
                    edit_type=hypothesis.expected_fix_type or node["plan"].edit_type,
                    patch_line_count=_line_count_from_patch(child_checkpoint.diff_patch),
                    oracle=oracle,
                )
                repair_reason = self._repair_reason(
                    changed_files=changed_files,
                    syntax_ok=syntax_result.returncode == 0,
                    oracle=oracle,
                    rubric=rubric,
                    plan=node["plan"],
                )
                child_messages = list(node["messages"])
                child_last_feedback = ""
                cheap_verify_status = ""
                verify_stage = ""
                submit_requested = bool(getattr(turn, "submit", False))
                verification = VerificationOutcome(
                    verified=False,
                    status="max_steps",
                    output="",
                    passed_tests=(),
                    failed_tests=(),
                    changed_files=changed_files,
                )
                terminal_output = syntax_result.output
                terminal_detail_child = ""
                terminal_status_child = ""
                if syntax_result.returncode != 0:
                    terminal_detail_child = "syntax_fail"
                    child_last_feedback = f"Syntax check failed.\n{syntax_result.output}"
                    child_messages.append({"role": "user", "content": child_last_feedback})
                else:
                    cheap_result = workspace.cheap_targeted_verify(task, oracle.related_tests)
                    node["raw_log"].append(cheap_result.output)
                    terminal_output = cheap_result.output
                    if "skipped" in cheap_result.output.lower():
                        cheap_verify_status = "skipped"
                    else:
                        cheap_verify_status = "success" if cheap_result.returncode == 0 else "verify_fail"
                    cheap_cache[child_checkpoint.patch_hash] = (cheap_verify_status, cheap_result.output)
                    verify_stage = "cheap"
                    child_last_feedback = (
                        "Cheap verify failed. Make one minimal revision."
                        if cheap_verify_status == "verify_fail"
                        else "Syntax and cheap verify passed. Submit candidate is plausible."
                    )
                    child_messages.append({"role": "user", "content": child_last_feedback})

                child = {
                    **node,
                    "node_id": self._next_branch_id(base_instance_id=task.get("instance_id", ""), stage="node"),
                    "parent_node_id": node["node_id"],
                    "checkpoint_id": child_checkpoint.checkpoint_id,
                    "hypothesis_id": "",
                    "parent_hypothesis_id": hypothesis.hypothesis_id,
                    "best_checkpoint_id": child_checkpoint.checkpoint_id,
                    "best_hypothesis_id": hypothesis.hypothesis_id,
                    "messages": child_messages,
                    "raw_log": list(node["raw_log"]),
                    "state_paths": list(node["state_paths"]),
                    "attempts_used": 0,
                    "visit_count": 0,
                    "value_mean": 0.0,
                    "selection_score": 0.0,
                    "selection_tier": 0,
                    "value_vector": self._empty_value_vector(),
                    "last_feedback": child_last_feedback,
                    "teacher_shaped": bool(node.get("teacher_shaped", False) or hypothesis.teacher_shaped),
                    "teacher_summary_calls": int(node.get("teacher_summary_calls", 0)),
                    "cached_teacher_hypotheses": [],
                    "submit_candidate": False,
                    "terminal_status": terminal_status_child,
                    "terminal_detail": terminal_detail_child,
                    "terminal_output": terminal_output,
                    "verification": verification,
                    "full_verified": False,
                    "syntax_ok": syntax_result.returncode == 0,
                    "cheap_verify_status": cheap_verify_status,
                    "verify_stage": verify_stage,
                    "repair_eligible_reason": repair_reason,
                    "oracle_scores": child_oracle_scores,
                    "patch_hash": child_checkpoint.patch_hash,
                    "changed_files": tuple(child_checkpoint.changed_files),
                    "summary_ids": [],
                    "is_root": False,
                    "source": "teacher" if hypothesis.source == "teacher" else str(node.get("source", "") or "student"),
                    "metadata": {
                        **dict(node.get("metadata", {}) or {}),
                        "parent_attempts_used": int(node.get("attempts_used", 0)),
                        "parent_hypothesis_id": hypothesis.hypothesis_id,
                    },
                }
                child_context = self._realization_context(
                    task=task,
                    workspace=workspace,
                    localization=child["localization"],
                    plan=child["plan"],
                    oracle=oracle,
                    step_index=0,
                    allowed_steps=self.max_steps,
                    last_feedback=child_last_feedback,
                )
                state_path = self._capture_step_state(
                    trajectory_id=node.get("trajectory_id", child["node_id"]),
                    instance_id=_sample_instance_id(
                        task.get("instance_id", ""),
                        int(node.get("localization_rank", 1)),
                        int(node.get("plan_rank", 1)),
                        int(node.get("root_round", 1)),
                    ),
                    base_instance_id=task.get("instance_id", ""),
                    step_index=len(node["state_paths"]),
                    tool_name=tool_name,
                    command=command_repr,
                    submit=False,
                    result=result,
                    workspace=workspace,
                    target_exists=target_exists,
                    span_valid=span_valid,
                    syntax_ok=bool(child["syntax_ok"]),
                    cheap_verify_status=cheap_verify_status,
                    verify_stage=verify_stage,
                    patch_hash=child_checkpoint.patch_hash,
                    repair_eligible_reason=repair_reason,
                    teacher_online_calls=int(node.get("teacher_summary_calls", 0)),
                    teacher_shaped=bool(child.get("teacher_shaped", False)),
                    hypothesis_id=hypothesis.hypothesis_id,
                    parent_hypothesis_id=hypothesis.parent_hypothesis_id,
                    branch_id=child["node_id"],
                    parent_branch_id=node["node_id"],
                    branch_source=str(child.get("source", "") or ""),
                    judge_score=float(node.get("value_mean", 0.0) or 0.0),
                    judge_stage="realization_summary",
                    judge_decision="expand",
                )
                child["state_paths"].append(state_path)
                if child_checkpoint.patch_hash in seen_patch_hashes:
                    child["terminal_status"] = "quality_fail"
                    child["terminal_detail"] = "duplicate_patch"
                else:
                    seen_patch_hashes.add(child_checkpoint.patch_hash)
                summary = self._teacher_summary_for_node(
                    task=task,
                    oracle=oracle,
                    rubric=rubric,
                    checkpoint=child_checkpoint,
                    span_catalog=list(child_context.get("span_catalog", []) or []),
                    node=child,
                )
                self._update_node_from_summary(
                    node=child,
                    summary=summary,
                    parent_visits=sum(int(item.get("visit_count", 0)) for item in live_nodes),
                )
                if not child.get("terminal_status"):
                    should_full_verify = (
                        (bool(child.get("submit_candidate", False)) or submit_requested)
                        and child_checkpoint.patch_hash not in verified_patch_hashes
                        and full_verify_used < self.full_verify_budget
                    )
                    if should_full_verify:
                        verification = verifier.verify(workspace=workspace)
                        full_cache[child_checkpoint.patch_hash] = verification
                        verified_patch_hashes.add(child_checkpoint.patch_hash)
                        full_verify_used += 1
                        child["verification"] = verification
                        child["full_verified"] = True
                        child["verify_stage"] = "full"
                        child["terminal_output"] = verification.output
                        if verification.verified:
                            child["terminal_status"] = "success"
                    elif cheap_verify_status == "verify_fail":
                        child["verification"] = VerificationOutcome(
                            verified=False,
                            status="verify_fail",
                            output=terminal_output,
                            passed_tests=(),
                            failed_tests=(),
                            changed_files=tuple(child_checkpoint.changed_files),
                        )
                self._update_node_value_vector(child)
                self._append_search_node_record(child)
                live_nodes.remove(node)
                self.hypothesis_children_total += 1
                if child.get("terminal_status") == "success":
                    emitted_nodes.append(child)
                else:
                    if len(live_nodes) < self.max_live_nodes:
                        live_nodes.append(child)
                    else:
                        worst = min(
                            live_nodes,
                            key=lambda item: (
                                int(item.get("selection_tier", 0) or 0),
                                float(item.get("selection_score", 0.0) or 0.0),
                            ),
                        )
                        if (
                            int(child.get("selection_tier", 0) or 0),
                            float(child.get("selection_score", 0.0) or 0.0),
                        ) > (
                            int(worst.get("selection_tier", 0) or 0),
                            float(worst.get("selection_score", 0.0) or 0.0),
                        ):
                            live_nodes.remove(worst)
                            worst["terminal_status"] = worst.get("terminal_status") or "quality_fail"
                            worst["terminal_detail"] = worst.get("terminal_detail") or "frontier_pruned"
                            emitted_nodes.append(worst)
                            live_nodes.append(child)
                        else:
                            child["terminal_status"] = child.get("terminal_status") or "quality_fail"
                            child["terminal_detail"] = child.get("terminal_detail") or "frontier_pruned"
                            emitted_nodes.append(child)
                if not self._root_race_active(live_nodes):
                    self._prune_root_race_frontier(live_nodes, emitted_nodes)

            if live_nodes and full_verify_used < self.full_verify_budget:
                candidates = [
                    node for node in live_nodes if bool(node.get("syntax_ok", False)) and node.get("patch_hash") and node["patch_hash"] not in verified_patch_hashes
                ]
                candidates.sort(
                    key=lambda item: (
                        int(item.get("selection_tier", 0) or 0),
                        float(item.get("selection_score", 0.0) or 0.0),
                    ),
                    reverse=True,
                )
                for node in candidates[: max(self.full_verify_budget - full_verify_used, 0)]:
                    checkpoint = checkpoints_by_id[node["checkpoint_id"]]
                    restore = workspace.restore_checkpoint(checkpoint)
                    if restore.returncode != 0:
                        node["terminal_status"] = "infra_fail"
                        node["terminal_detail"] = "restore_failed"
                        node["terminal_output"] = restore.output
                        continue
                    verification = verifier.verify(workspace=workspace)
                    verified_patch_hashes.add(checkpoint.patch_hash)
                    full_verify_used += 1
                    node["verification"] = verification
                    node["full_verified"] = True
                    node["verify_stage"] = "full"
                    node["terminal_output"] = verification.output
                    node["terminal_status"] = "success" if verification.verified else "verify_fail"
                    self._update_node_value_vector(node)
                    self._append_search_node_record(node)

            for node in [*emitted_nodes, *live_nodes]:
                if not node.get("terminal_status"):
                    node["terminal_status"] = "max_steps" if node.get("patch_hash") else "no_patch"
                    node["terminal_detail"] = node.get("terminal_detail") or ("budget_exhausted" if node.get("patch_hash") else "inspect_only")
                if not node.get("emitted", False):
                    trajectories.append(
                        self._finalize_search_node(
                            task=task,
                            oracle=oracle,
                            rubric=rubric if rubric_enabled else None,
                            node=node,
                            checkpoints_by_id=checkpoints_by_id,
                        )
                    )
            return trajectories
        finally:
            workspace.close()

    def _sample_one(
        self,
        *,
        task: dict,
        localization: SweLocalizationCandidateV1,
        localization_rank: int,
        plan: SwePatchPlanV1,
        plan_rank: int,
        oracle: SweIssueOracleV1,
        rubric: SweIssueRubricV1 | None,
        rubric_enabled: bool,
        rubric_degraded_reason: str,
        temperature: float,
    ) -> SweRawTrajectoryV1:
        base_instance_id = task.get("instance_id", "")
        instance_id = _sample_instance_id(base_instance_id, localization_rank, plan_rank, 1)
        trajectory_id = f"{instance_id}-{uuid.uuid4().hex[:8]}"
        workspace = self.runtime.create_workspace(task)
        verifier = SweTerminalVerifier(task)
        messages = self._realization_messages(task=task, localization=localization, plan=plan)
        state_paths: list[str] = []
        raw_log: list[str] = []
        terminal_output = ""
        status = "max_steps"
        terminal_detail = ""
        last_feedback = ""
        verify_passed = False
        passed_tests: tuple[str, ...] = ()
        failed_tests: tuple[str, ...] = ()
        near_miss = False
        trajectory_oracle_scores: dict[str, float] = {}
        syntax_ok = False
        cheap_verify_status = ""
        verify_stage = ""
        repair_eligible_reason = ""
        patch_hash = ""
        cheap_cache: dict[str, tuple[str, str]] = {}
        full_cache: dict[str, VerificationOutcome] = {}
        teacher_online_calls = 0
        current_branch_id = plan.plan_id or self._next_branch_id(base_instance_id=base_instance_id, stage="realize", seed="root")
        current_parent_branch_id = localization.candidate_id
        current_branch_source = str(plan.metadata.get("source", localization.metadata.get("source", "student")) or "student")
        trajectory_teacher_shaped = bool(plan.metadata.get("teacher_shaped", False) or localization.metadata.get("teacher_shaped", False))
        latest_judge_score = 0.0
        latest_judge_stage = ""
        latest_judge_decision = ""
        pending_teacher_actions: list[dict] = []
        verification = VerificationOutcome(
            verified=False,
            status="max_steps",
            output="",
            passed_tests=(),
            failed_tests=(),
            changed_files=(),
        )
        verified_once = False
        try:
            self._append_branch_node(
                base_instance_id=base_instance_id,
                trajectory_id=trajectory_id,
                branch_id=current_branch_id,
                parent_branch_id=current_parent_branch_id,
                stage="realization",
                source=current_branch_source,
                teacher_shaped=trajectory_teacher_shaped,
                current_score=plan.total_score,
                metadata={"localization_id": localization.candidate_id, "plan_id": plan.plan_id},
            )
            exhausted_steps = True
            allowed_steps = self.max_steps
            step_index = 0
            while step_index < allowed_steps:
                terminal_detail = ""
                realize_patch_action = getattr(self.student_session, "realize_patch_action", None)
                structured_mode = callable(realize_patch_action) and hasattr(workspace, "apply_patch_action")
                context = self._realization_context(
                    task=task,
                    workspace=workspace,
                    localization=localization,
                    plan=plan,
                    oracle=oracle,
                    step_index=step_index,
                    allowed_steps=allowed_steps,
                    last_feedback=last_feedback,
                )
                if structured_mode and pending_teacher_actions:
                    queued = pending_teacher_actions.pop(0)
                    current_branch_id = str(queued.get("branch_id", current_branch_id) or current_branch_id)
                    current_parent_branch_id = str(queued.get("parent_branch_id", current_parent_branch_id) or current_parent_branch_id)
                    current_branch_source = "teacher"
                    trajectory_teacher_shaped = True
                    turn = self._teacher_action_turn(queued["action"])
                elif structured_mode:
                    turn = realize_patch_action(
                        task=task,
                        context=context,
                        temperature=temperature,
                    )
                else:
                    turn = self.student_session.next_turn(task=task, messages=messages, temperature=temperature)
                messages.append(turn.assistant_message)
                raw_log.append(turn.assistant_message.get("content", ""))
                tool_name = getattr(turn, "tool_name", "shell")
                action = getattr(turn, "action", None)
                target_exists = False
                span_valid = False
                if structured_mode and tool_name == "apply_patch_action":
                    action_state = getattr(turn, "action_state", "") or "parse_fail"
                    if action_state == "no_action":
                        result = type("Result", (), {"stdout": "no_action", "stderr": "", "output": "no_action", "returncode": 0})()
                        command_repr = workspace.render_patch_action(action or {"edit_type": "no_action"})
                        terminal_detail = "no_action"
                        status = "no_patch" if not workspace.has_patch() else "quality_fail"
                        exhausted_steps = False
                    elif action_state != "ok" or not isinstance(action, dict):
                        result = type("Result", (), {"stdout": "", "stderr": action_state, "output": action_state, "returncode": 1})()
                        command_repr = workspace.render_patch_action(action or {})
                        terminal_detail = action_state
                        status = "no_patch" if not workspace.has_patch() else "quality_fail"
                        exhausted_steps = False
                    else:
                        resolved_action, target_exists, span_valid = self._resolve_patch_action(action=action, context=context)
                        violation = self._action_policy_violation(action=resolved_action, context=context) if target_exists and span_valid else ""
                        command_repr = workspace.render_patch_action(resolved_action)
                        if not target_exists:
                            result = type("Result", (), {"stdout": "", "stderr": "target_file does not exist", "output": "target_file does not exist", "returncode": 1})()
                            terminal_detail = "invalid_target"
                            status = "no_patch" if not workspace.has_patch() else "quality_fail"
                            exhausted_steps = False
                        elif not span_valid:
                            result = type("Result", (), {"stdout": "", "stderr": "invalid span", "output": "invalid span", "returncode": 1})()
                            terminal_detail = "invalid_span"
                            status = "no_patch" if not workspace.has_patch() else "quality_fail"
                            exhausted_steps = False
                        elif violation:
                            result = type("Result", (), {"stdout": "", "stderr": violation, "output": violation, "returncode": 1})()
                            terminal_detail = violation
                            status = "quality_fail"
                            exhausted_steps = False
                        else:
                            result = workspace.apply_patch_action(resolved_action, timeout=120)
                elif not turn.command.strip():
                    terminal_detail = getattr(turn, "action_state", "") or "no_action"
                    status = "no_patch" if not workspace.has_patch() else "verify_fail"
                    exhausted_steps = False
                    result = type("Result", (), {"stdout": "", "stderr": terminal_detail, "output": terminal_detail, "returncode": 1})()
                    command_repr = ""
                else:
                    command_repr = turn.command
                    result = workspace.exec(f"cd /app && {turn.command}", timeout=120)
                raw_log.append(result.output)
                messages.append(self.student_session.observation_message(turn=turn, output=result.output, returncode=result.returncode))
                patch_hash = workspace.patch_hash()
                if workspace.has_patch() and syntax_ok and step_index + 1 < max(self.max_steps, 6):
                    allowed_steps = max(allowed_steps, max(self.max_steps, 6))
                syntax_check = getattr(workspace, "syntax_check", None)
                if structured_mode and callable(syntax_check) and workspace.has_patch() and result.returncode == 0:
                    syntax_result = syntax_check(task.get("repo_language", ""), workspace.changed_files(), timeout=120)
                    raw_log.append(syntax_result.output)
                    if syntax_result.returncode != 0:
                        syntax_ok = False
                        terminal_output = syntax_result.output
                        terminal_detail = "syntax_fail"
                        status = "quality_fail"
                        last_feedback = f"Syntax check failed.\n{syntax_result.output}"
                        if step_index < allowed_steps - 1:
                            messages.append({"role": "user", "content": last_feedback})
                            step_index += 1
                            continue
                        exhausted_steps = False
                        break
                    if workspace.has_patch():
                        syntax_ok = True
                        patch_hash = workspace.patch_hash()
                        last_feedback = "Syntax check passed. Refine the current patch or submit it for verification."
                        repair_eligible_reason = self._repair_reason(
                            changed_files=tuple(workspace.changed_files()),
                            syntax_ok=syntax_ok,
                            oracle=oracle,
                            rubric=rubric,
                            plan=plan,
                        )
                        if step_index + 1 < max(self.max_steps, 6):
                            allowed_steps = max(allowed_steps, max(self.max_steps, 6))
                        if step_index < allowed_steps - 1:
                            messages.append({"role": "user", "content": last_feedback})
                elif not workspace.has_patch() and step_index < allowed_steps - 1:
                    last_feedback = "Budget is limited. Stop inspecting and make a concrete repository edit on the next turn."
                    messages.append({"role": "user", "content": last_feedback})
                if turn.submit:
                    patch_hash = workspace.patch_hash()
                    verification, cheap_verify_status, verify_stage = self._run_verify_funnel(
                        task=task,
                        oracle=oracle,
                        workspace=workspace,
                        verifier=verifier,
                        patch_hash=patch_hash,
                        cheap_cache=cheap_cache,
                        full_cache=full_cache,
                    )
                    verified_once = verify_stage == "full"
                    terminal_output = verification.output
                    verify_passed = verification.verified
                    status = verification.status
                    passed_tests = verification.passed_tests
                    failed_tests = verification.failed_tests
                    if verify_passed:
                        exhausted_steps = False
                    elif step_index < allowed_steps - 1:
                        last_feedback = f"Tests still failing.\n{verification.output}"
                        messages.append(self.student_session.verification_feedback(output=verification.output))
                teacher_decision = self._judge_realization_step(
                    task=task,
                    oracle=oracle,
                    rubric=rubric,
                    trajectory_id=trajectory_id,
                    branch_id=current_branch_id,
                    parent_branch_id=current_parent_branch_id,
                    teacher_shaped=trajectory_teacher_shaped,
                    branch_state={
                        "branch_id": current_branch_id,
                        "changed_files": list(workspace.changed_files()),
                        "patch_hash": patch_hash,
                        "syntax_ok": syntax_ok,
                        "cheap_verify_status": cheap_verify_status,
                        "verify_stage": verify_stage,
                        "repair_eligible_reason": repair_eligible_reason,
                    },
                    last_action={
                        "tool_name": tool_name,
                        "command": command_repr,
                        "submit": turn.submit,
                        "action": action or {},
                    },
                    runtime_feedback={
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "returncode": result.returncode,
                        "target_exists": target_exists,
                        "span_valid": span_valid,
                        "syntax_ok": syntax_ok,
                        "cheap_verify_status": cheap_verify_status,
                        "verify_stage": verify_stage,
                        "terminal_detail": terminal_detail,
                    },
                )
                stop_current = False
                if teacher_decision is not None:
                    teacher_online_calls += 1
                    latest_judge_score = teacher_decision.score
                    latest_judge_stage = teacher_decision.stage
                    latest_judge_decision = teacher_decision.decision
                    if structured_mode and self.branch_nodes_total < self.max_total_branches_per_issue:
                        for proposal_index, proposal in enumerate(teacher_decision.branch_proposals[: self.teacher_branch_fanout], start=1):
                            branch_id = self._next_branch_id(
                                base_instance_id=base_instance_id,
                                stage="realize",
                                seed=f"{step_index + 1}t{proposal_index}",
                            )
                            pending_teacher_actions.append(
                                {
                                    "branch_id": branch_id,
                                    "parent_branch_id": current_branch_id,
                                    "action": dict(proposal),
                                }
                            )
                            self._append_branch_node(
                                base_instance_id=base_instance_id,
                                trajectory_id=trajectory_id,
                                branch_id=branch_id,
                                parent_branch_id=current_branch_id,
                                stage="realization",
                                source="teacher",
                                teacher_shaped=True,
                                current_score=teacher_decision.score,
                                patch_hash=patch_hash,
                                changed_files=tuple(workspace.changed_files()),
                                metadata={"proposal": proposal},
                            )
                    if teacher_decision.decision == "submit_now" and workspace.has_patch():
                        patch_hash = workspace.patch_hash()
                        verification, cheap_verify_status, verify_stage = self._run_verify_funnel(
                            task=task,
                            oracle=oracle,
                            workspace=workspace,
                            verifier=verifier,
                            patch_hash=patch_hash,
                            cheap_cache=cheap_cache,
                            full_cache=full_cache,
                        )
                        terminal_output = verification.output
                        verify_passed = verification.verified
                        status = verification.status
                        passed_tests = verification.passed_tests
                        failed_tests = verification.failed_tests
                        verified_once = verify_stage == "full"
                    stop_current = teacher_decision.decision == "stop_current"
                state_paths.append(
                    self._capture_step_state(
                        trajectory_id=trajectory_id,
                        instance_id=instance_id,
                        base_instance_id=base_instance_id,
                        step_index=step_index,
                        tool_name=tool_name,
                        command=command_repr,
                        submit=turn.submit or (teacher_decision is not None and teacher_decision.decision == "submit_now"),
                        result=result,
                        workspace=workspace,
                        target_exists=target_exists,
                        span_valid=span_valid,
                        syntax_ok=syntax_ok,
                        cheap_verify_status=cheap_verify_status,
                        verify_stage=verify_stage,
                        patch_hash=patch_hash,
                        repair_eligible_reason=repair_eligible_reason,
                        teacher_online_calls=teacher_online_calls,
                        teacher_shaped=trajectory_teacher_shaped,
                        branch_id=current_branch_id,
                        parent_branch_id=current_parent_branch_id,
                        branch_source=current_branch_source,
                        judge_score=latest_judge_score,
                        judge_stage=latest_judge_stage,
                        judge_decision=latest_judge_decision,
                    )
                )
                if verify_passed:
                    exhausted_steps = False
                    break
                if terminal_detail in {"invalid_target", "invalid_span", "top_insert_forbidden", "skeleton_insert", "replacement_too_large"}:
                    if pending_teacher_actions and step_index < allowed_steps - 1:
                        last_feedback = "Teacher proposed an alternative branch. Execute the alternative minimal patch action now."
                        step_index += 1
                        continue
                    break
                if terminal_detail == "no_action" and workspace.has_patch():
                    if pending_teacher_actions and step_index < allowed_steps - 1:
                        last_feedback = "No more inspection budget. Execute the teacher-shaped patch revision next."
                        step_index += 1
                        continue
                    break
                if stop_current:
                    if pending_teacher_actions and step_index < allowed_steps - 1:
                        last_feedback = "Teacher stopped the current branch and proposed an alternative."
                        step_index += 1
                        continue
                    break
                step_index += 1
            if exhausted_steps:
                if not workspace.has_patch() and not terminal_detail:
                    terminal_detail = "inspect_only"
                    status = "max_steps"
                else:
                    status = "max_steps" if workspace.has_patch() or not terminal_detail else "no_patch"

            quality_status, trajectory_oracle_scores = self._quality_status(workspace=workspace, oracle=oracle, plan=plan)
            if workspace.has_patch() and syntax_ok and not verified_once:
                patch_hash = workspace.patch_hash()
                verification, cheap_verify_status, verify_stage = self._run_verify_funnel(
                    task=task,
                    oracle=oracle,
                    workspace=workspace,
                    verifier=verifier,
                    patch_hash=patch_hash,
                    cheap_cache=cheap_cache,
                    full_cache=full_cache,
                )
                terminal_output = verification.output
                verify_passed = verification.verified
                status = verification.status
                passed_tests = verification.passed_tests
                failed_tests = verification.failed_tests
                verified_once = verify_stage == "full"

            if quality_status == "quality_fail" and not verify_passed and status not in {"verify_fail", "success"}:
                status = "quality_fail"
                verification = VerificationOutcome(
                    verified=False,
                    status="quality_fail",
                    output=terminal_output,
                    passed_tests=passed_tests,
                    failed_tests=failed_tests,
                    changed_files=tuple(workspace.changed_files()),
                )
            repair_eligible_reason = repair_eligible_reason or self._repair_reason(
                changed_files=tuple(workspace.changed_files()),
                syntax_ok=syntax_ok,
                oracle=oracle,
                rubric=rubric,
                plan=plan,
            )
            near_miss = bool(workspace.has_patch()) and bool(repair_eligible_reason) and status in {"verify_fail", "quality_fail"} and not _is_collector_side_no_patch(terminal_detail)

            raw_log_path = self.exporter.write_raw_log(trajectory_id=trajectory_id, raw_log="\n".join(raw_log))
            trajectory = SweRawTrajectoryV1(
                trajectory_id=trajectory_id,
                run_id=self.run_id,
                instance_id=instance_id,
                base_instance_id=base_instance_id,
                repo=task.get("repo", ""),
                language=task.get("repo_language", ""),
                format=self.format,
                sampling_temperature=temperature,
                student_model=self.student_session.model,
                student_endpoint=self.student_session.endpoint,
                collector=self.collector_name,
                teacher_calls=(1 if rubric is not None else 0) + teacher_online_calls,
                repair_round=0,
                rubric_score=plan.rubric_score,
                oracle_scores=trajectory_oracle_scores,
                localization_id=localization.candidate_id,
                plan_id=plan.plan_id,
                messages=tuple(ConversationMessage.model_validate(message) for message in messages),
                state_paths=tuple(state_paths),
                final_patch=workspace.diff_patch(),
                terminal_status=status,
                terminal_detail=terminal_detail,
                verify_passed=verify_passed,
                patch_hash=patch_hash,
                syntax_ok=syntax_ok,
                cheap_verify_status=cheap_verify_status,
                verify_stage=verify_stage,
                repair_eligible_reason=repair_eligible_reason,
                teacher_online_calls=teacher_online_calls,
                teacher_shaped=trajectory_teacher_shaped,
                branch_id=current_branch_id,
                parent_branch_id=current_parent_branch_id,
                branch_source=current_branch_source,
                judge_score=latest_judge_score,
                judge_stage=latest_judge_stage,
                judge_decision=latest_judge_decision,
                terminal_output=terminal_output,
                assistant_turns=sum(1 for message in messages if message.get("role") == "assistant"),
                changed_files=tuple(workspace.changed_files()),
                rubric_enabled=rubric_enabled,
                rubric_degraded_reason=rubric_degraded_reason,
                task_metadata=_task_metadata(
                    task,
                    verification,
                    failed_tests=failed_tests,
                    passed_tests=passed_tests,
                    near_miss=near_miss,
                    rubric_enabled=rubric_enabled,
                    rubric_degraded_reason=rubric_degraded_reason,
                    terminal_detail=terminal_detail,
                    localization_id=localization.candidate_id,
                    plan_id=plan.plan_id,
                    rubric_id=rubric.rubric_id if rubric is not None else "",
                ),
                raw_log_path=raw_log_path,
            )
            self.exporter.append_raw_trajectory(trajectory)
            if trajectory.verify_passed and trajectory_teacher_shaped:
                self.teacher_shaped_successes += 1
            return trajectory
        finally:
            workspace.close()

    def run(self, *, task_range: str = "", task_file: str = "") -> CollectResult:
        if not self.resume:
            for path in (
                self.exporter.raw_path,
                self.exporter.oracle_path,
                self.exporter.rubric_path,
                self.exporter.localization_path,
                self.exporter.plan_path,
                self.exporter.branch_path,
                self.exporter.judge_decision_path,
                self.exporter.checkpoint_path,
                self.exporter.hypothesis_path,
                self.exporter.search_node_path,
                self.exporter.teacher_summary_path,
                self.exporter.run_manifest_path,
            ):
                if path.exists():
                    path.unlink()
        tasks = list(self.task_source.iter_tasks(task_range=task_range, task_file=task_file))
        self._probe_dependencies(tasks)
        existing = self._existing_base_ids()
        trajectories: list[SweRawTrajectoryV1] = []
        localization_count = 0
        plan_count = 0
        rubric_calls = 0
        realized_count = 0
        for task in tasks:
            if task.get("instance_id", "") in existing:
                continue
            oracle = self._append_hidden_oracle(task)
            rubric, rubric_reason = self._append_issue_rubric(task=task, oracle=oracle)
            task_rubric_enabled = rubric is not None
            task_rubric_reason = rubric_reason if not task_rubric_enabled else ""
            if rubric is not None:
                rubric_calls += 1
            elif self.teacher_session is not None and not self.rubric_degraded_reason:
                self.rubric_enabled = False
                self.rubric_degraded_reason = rubric_reason
            repo_files: set[str] = set()
            search_workspace = None
            try:
                search_workspace = self.runtime.create_workspace(task)
                repo_files = set(getattr(search_workspace, "list_repo_files", lambda: ())())
            finally:
                if search_workspace is not None:
                    search_workspace.close()
            localizations, generated_localizations = self._collect_localizations(task=task, oracle=oracle, rubric=rubric, repo_files=repo_files)
            localization_count += generated_localizations
            plans, generated_plans = self._collect_patch_plans(task=task, oracle=oracle, rubric=rubric, localizations=localizations, repo_files=repo_files)
            plan_count += generated_plans
            task_trajectories = self._sample_task_tree(
                task=task,
                localizations=localizations,
                plans=plans,
                oracle=oracle,
                rubric=rubric,
                rubric_enabled=task_rubric_enabled,
                rubric_degraded_reason=task_rubric_reason,
            )
            trajectories.extend(task_trajectories)
            realized_count += len(task_trajectories)

        success = sum(1 for trajectory in trajectories if trajectory.verify_passed)
        failed = len(trajectories) - success
        manifest = SweCollectionRunManifestV2(
            run_id=self.run_id,
            format=self.format,
            output_dir=str(self.exporter.output_dir),
            task_source=f"range={task_range}" if task_range else f"file={task_file}",
            student_model=self.student_session.model,
            student_endpoint=self.student_session.endpoint,
            teacher_model=self.teacher_model_name,
            teacher_endpoint=self.teacher_endpoint_name,
            student_probe_status=self.student_probe_status,
            teacher_probe_status=self.teacher_probe_status,
            docker_probe_status=self.docker_probe_status,
            rubric_enabled=self.rubric_enabled,
            rubric_degraded_reason=self.rubric_degraded_reason,
            raw_dir=str(self.exporter.raw_dir),
            states_dir=str(self.exporter.states_dir),
            relabel_dir=str(self.exporter.relabel_dir),
            bucket_dir=str(self.exporter.bucket_dir),
            canonical_path=str(self.exporter.canonical_path),
            verifier_dataset_path=str(self.exporter.verifier_dataset_path),
            log_dir=str(self.exporter.log_dir),
            stage_counts={
                "tasks_requested": len(tasks),
                "rubric_calls": rubric_calls,
                "localization_candidates": localization_count,
                "patch_plan_candidates": plan_count,
                "realized_trajectories": realized_count,
                "sampled_trajectories": len(trajectories),
                "successful_trajectories": success,
                "failed_trajectories": failed,
                "teacher_online_calls": self.teacher_online_calls_total,
                "branch_nodes_total": self.branch_nodes_total,
                "teacher_branches_total": self.teacher_branches_total,
                "teacher_shaped_successes": self.teacher_shaped_successes,
                "root_nodes_total": self.root_nodes_total,
                "root_race_rounds_run": self.root_race_rounds_run,
                "hypothesis_nodes_total": self.hypothesis_nodes_total,
                "hypothesis_children_total": self.hypothesis_children_total,
                "teacher_hypotheses_total": self.teacher_hypotheses_total,
                "near_miss_nodes_total": self.near_miss_nodes_total,
                "dead_end_nodes_total": self.dead_end_nodes_total,
            },
            notes={
                "sampling_temps": list(self.temps),
                "collector": self.collector_name,
                "teacher_online": self.teacher_online,
                "teacher_online_budget": self.teacher_online_budget,
                "teacher_branch_fanout": self.teacher_branch_fanout,
                "search_node_budget": self.search_node_budget,
                "attempts_per_node": self.attempts_per_node,
                "max_live_nodes": self.max_live_nodes,
                "full_verify_budget": self.full_verify_budget,
                "root_race_rounds": self.root_race_rounds,
                "root_race_keep": self.root_race_keep,
                "progressive_bias_beta": self.progressive_bias_beta,
                "localization_top_k": self.localization_top_k,
                "plan_samples_per_state": self.plan_samples_per_state,
                "max_realizations": self.max_realizations,
                "selection_tier_histogram": self.selection_tier_histogram,
            },
        )
        self.exporter.write_run_manifest(manifest)
        return CollectResult(
            output=str(self.exporter.raw_path),
            staging_path=str(self.exporter.raw_path),
            raw_path=str(self.exporter.raw_dir),
            records=len(trajectories),
            success=success,
            failed=failed,
            mode=self.collector_name,
            raw_files=[
                str(self.exporter.raw_path),
                str(self.exporter.oracle_path),
                str(self.exporter.rubric_path),
                str(self.exporter.localization_path),
                str(self.exporter.plan_path),
                str(self.exporter.branch_path),
                str(self.exporter.judge_decision_path),
                str(self.exporter.checkpoint_path),
                str(self.exporter.hypothesis_path),
                str(self.exporter.search_node_path),
                str(self.exporter.teacher_summary_path),
                str(self.exporter.run_manifest_path),
            ],
            reason=self.rubric_degraded_reason,
        )


def run_swe_sampling(
    *,
    fmt: str,
    task_range: str,
    task_file: str,
    output_dir: str,
    student_endpoint: str = "",
    student_model: str = "",
    student_api_key: str = "",
    teacher_endpoint: str = "",
    teacher_model: str = "",
    teacher_api_key: str = "",
    teacher_online: bool = True,
    teacher_online_budget: int = 12,
    teacher_branch_fanout: int = 2,
    cache_dir: str = "/tmp/orbit-swe-task-cache",
    max_steps: int = 4,
    resume: bool = False,
    temps: tuple[float, ...] = (0.3, 0.6, 0.9),
    localization_budget: int = 8,
    localization_top_k: int = 3,
    plan_samples_per_state: int = 2,
    max_realizations: int = 4,
    search_node_budget: int = 12,
    attempts_per_node: int = 3,
    max_live_nodes: int = 6,
    full_verify_budget: int = 2,
    root_race_rounds: int = 2,
    root_race_keep: int = 3,
    progressive_bias_beta: float = 0.30,
) -> CollectResult:
    from .runtime import SweDockerWorkspaceRuntime

    task_source = SweTaskSource(cache_dir=cache_dir)
    runtime = SweDockerWorkspaceRuntime()
    teacher_session = None
    if teacher_endpoint or teacher_model or teacher_api_key:
        teacher_session = TeacherJudgeSession(endpoint=teacher_endpoint, model=teacher_model, api_key=teacher_api_key)
    elif resolve_teacher_endpoint() and resolve_teacher_api_key():
        teacher_session = TeacherJudgeSession()
    if fmt == "codex":
        student_session = CodexStudentSession(endpoint=student_endpoint, model=student_model, api_key=student_api_key)
    else:
        student_session = MiniSweStudentSession(endpoint=student_endpoint, model=student_model, api_key=student_api_key)
    sampler = SweAutonomousSampler(
        fmt=fmt,
        task_source=task_source,
        runtime=runtime,
        student_session=student_session,
        output_dir=output_dir,
        teacher_session=teacher_session,
        teacher_online=teacher_online,
        teacher_online_budget=teacher_online_budget,
        teacher_branch_fanout=teacher_branch_fanout,
        max_steps=max_steps,
        temps=temps,
        resume=resume,
        localization_budget=localization_budget,
        localization_top_k=localization_top_k,
        plan_samples_per_state=plan_samples_per_state,
        max_realizations=max_realizations,
        search_node_budget=search_node_budget,
        attempts_per_node=attempts_per_node,
        max_live_nodes=max_live_nodes,
        full_verify_budget=full_verify_budget,
        root_race_rounds=root_race_rounds,
        root_race_keep=root_race_keep,
        progressive_bias_beta=progressive_bias_beta,
    )
    return sampler.run(task_range=task_range, task_file=task_file)


__all__ = ["SweAutonomousSampler", "parse_sampling_temps", "run_swe_sampling"]
