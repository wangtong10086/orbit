"""Cascade sampler for staged SWE collection."""

from __future__ import annotations

import json
import uuid
from urllib.error import HTTPError, URLError

from orbit.foundation.data_contracts import (
    CollectResult,
    ConversationMessage,
    SweCollectionRunManifestV2,
    SweIssueOracleV1,
    SweIssueRubricV1,
    SweLocalizationCandidateV1,
    SwePatchPlanV1,
    SweRawTrajectoryV1,
    SweStepStateV1,
)

from .exporter import SweCollectionExporter
from .judge import SweTerminalVerifier, VerificationOutcome
from .oracle import aggregate_oracle_scores, build_hidden_oracle, score_rubric_alignment
from .sessions import (
    CodexStudentSession,
    FailureCritiqueSession,
    MiniSweStudentSession,
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
        max_steps: int = 24,
        temps: tuple[float, ...] = (0.3, 0.6, 0.9),
        resume: bool = False,
        localization_budget: int = 16,
        localization_top_k: int = 4,
        plan_samples_per_state: int = 2,
        max_realizations: int = 4,
    ):
        self.format = fmt
        self.task_source = task_source
        self.runtime = runtime
        self.student_session = student_session
        self.output_dir = output_dir
        self.teacher_session = teacher_session
        self.teacher_model_name = teacher_session.model if teacher_session is not None else ""
        self.teacher_endpoint_name = teacher_session.endpoint if teacher_session is not None else ""
        self.max_steps = max_steps
        self.temps = temps
        self.resume = resume
        self.localization_budget = localization_budget
        self.localization_top_k = localization_top_k
        self.plan_samples_per_state = plan_samples_per_state
        self.max_realizations = max_realizations
        self.exporter = SweCollectionExporter(output_dir=output_dir)
        self.run_id = uuid.uuid4().hex
        self.student_probe_status = "unprobed"
        self.teacher_probe_status = "disabled"
        self.docker_probe_status = "unprobed"
        self.rubric_enabled = teacher_session is not None
        self.rubric_degraded_reason = ""

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

    def _collect_localizations(
        self,
        *,
        task: dict,
        oracle: SweIssueOracleV1,
        rubric: SweIssueRubricV1 | None,
    ) -> tuple[list[SweLocalizationCandidateV1], int]:
        candidates: list[SweLocalizationCandidateV1] = []
        rubric_dict = rubric.model_dump(mode="json") if rubric else None
        for index in range(self.localization_budget):
            temperature = self.temps[index % len(self.temps)]
            proposal = self.student_session.propose_localization(task=task, temperature=temperature)
            oracle_scores = aggregate_oracle_scores(
                files=proposal.candidate_files,
                symbols=proposal.candidate_symbols,
                edit_type=proposal.edit_type,
                oracle=oracle,
            )
            rubric_score = score_rubric_alignment(
                files=proposal.candidate_files,
                symbols=proposal.candidate_symbols,
                hypothesis=proposal.hypothesis,
                rubric=rubric_dict,
            )
            total_score = oracle_scores["total"] * 0.75 + rubric_score * 0.25
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
            )
            self.exporter.append_localization(candidate)
            candidates.append(candidate)
        candidates.sort(key=lambda item: item.total_score, reverse=True)
        return candidates[: self.localization_top_k], len(candidates)

    def _collect_patch_plans(
        self,
        *,
        task: dict,
        oracle: SweIssueOracleV1,
        rubric: SweIssueRubricV1 | None,
        localizations: list[SweLocalizationCandidateV1],
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
                patch_line_count = _line_count_from_patch(proposal.diff_sketch)
                oracle_scores = aggregate_oracle_scores(
                    files=proposal.target_files,
                    symbols=proposal.target_symbols or localization.candidate_symbols,
                    edit_type=proposal.edit_type,
                    patch_line_count=patch_line_count,
                    oracle=oracle,
                )
                rubric_score = score_rubric_alignment(
                    files=proposal.target_files,
                    symbols=proposal.target_symbols,
                    hypothesis=proposal.diff_sketch,
                    rubric=rubric_dict,
                )
                total_score = oracle_scores["total"] * 0.7 + rubric_score * 0.2
                if set(proposal.target_files) & set(localization.candidate_files):
                    total_score += 0.1
                plan = SwePatchPlanV1(
                    plan_id=f"{oracle.base_instance_id}-plan-{loc_rank}-{plan_index + 1}",
                    base_instance_id=oracle.base_instance_id,
                    format=self.format,
                    localization_id=localization.candidate_id,
                    target_files=proposal.target_files,
                    target_symbols=proposal.target_symbols,
                    plan_steps=proposal.plan_steps,
                    diff_sketch=proposal.diff_sketch,
                    edit_type=proposal.edit_type,
                    oracle_scores=oracle_scores,
                    rubric_score=rubric_score,
                    total_score=min(1.0, total_score),
                    raw_response=proposal.raw_response,
                )
                self.exporter.append_patch_plan(plan)
                plans.append(plan)
        plans.sort(key=lambda item: item.total_score, reverse=True)
        return plans[: self.max_realizations], len(plans)

    def _capture_step_state(
        self,
        *,
        trajectory_id: str,
        instance_id: str,
        base_instance_id: str,
        step_index: int,
        command: str,
        submit: bool,
        result,
        workspace,
    ) -> str:
        state = SweStepStateV1(
            state_id=f"{trajectory_id}-s{step_index}",
            trajectory_id=trajectory_id,
            instance_id=instance_id,
            base_instance_id=base_instance_id,
            format=self.format,
            step_index=step_index,
            command=command,
            submit=submit,
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
            git_status_short=workspace.git_status_short() if hasattr(workspace, "git_status_short") else "",
            changed_files=tuple(workspace.changed_files()),
            diff_excerpt=(workspace.diff_patch() or "")[:4000],
        )
        return self.exporter.write_step_state(state)

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
        if scores["file_overlap"] < 0.2:
            return "quality_fail", scores
        return "", scores

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
        verify_passed = False
        passed_tests: tuple[str, ...] = ()
        failed_tests: tuple[str, ...] = ()
        near_miss = False
        trajectory_oracle_scores: dict[str, float] = {}
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
            exhausted_steps = True
            for step_index in range(self.max_steps):
                turn = self.student_session.next_turn(task=task, messages=messages, temperature=temperature)
                messages.append(turn.assistant_message)
                raw_log.append(turn.assistant_message.get("content", ""))
                if not turn.command.strip():
                    terminal_detail = getattr(turn, "action_state", "") or "no_action"
                    status = "no_patch" if not workspace.has_patch() else "verify_fail"
                    exhausted_steps = False
                    break
                result = workspace.exec(f"cd /app && {turn.command}", timeout=120)
                raw_log.append(result.output)
                messages.append(self.student_session.observation_message(turn=turn, output=result.output, returncode=result.returncode))
                state_paths.append(
                    self._capture_step_state(
                        trajectory_id=trajectory_id,
                        instance_id=instance_id,
                        base_instance_id=base_instance_id,
                        step_index=step_index,
                        command=turn.command,
                        submit=turn.submit,
                        result=result,
                        workspace=workspace,
                    )
                )
                if not workspace.has_patch() and step_index < self.max_steps - 1:
                    messages.append(
                        {
                            "role": "user",
                            "content": "Budget is limited. Stop inspecting and make a concrete repository edit on the next turn.",
                        }
                    )
                if turn.submit:
                    verification = verifier.verify(workspace=workspace)
                    verified_once = True
                    terminal_output = verification.output
                    verify_passed = verification.verified
                    status = verification.status
                    passed_tests = verification.passed_tests
                    failed_tests = verification.failed_tests
                    if verify_passed:
                        exhausted_steps = False
                        break
                    if step_index < self.max_steps - 1:
                        messages.append(self.student_session.verification_feedback(output=verification.output))
            if exhausted_steps:
                status = "max_steps"

            quality_status, trajectory_oracle_scores = self._quality_status(workspace=workspace, oracle=oracle, plan=plan)
            if quality_status == "quality_fail" and not verify_passed:
                status = "quality_fail"
                verification = VerificationOutcome(
                    verified=False,
                    status="quality_fail",
                    output=terminal_output,
                    passed_tests=passed_tests,
                    failed_tests=failed_tests,
                    changed_files=tuple(workspace.changed_files()),
                )

            if not verify_passed and status != "quality_fail" and workspace.has_patch() and not verified_once:
                verification = verifier.verify(workspace=workspace)
                terminal_output = verification.output
                verify_passed = verification.verified
                status = verification.status if verification.status != "success" else "success"
                passed_tests = verification.passed_tests
                failed_tests = verification.failed_tests

            near_miss = bool(workspace.has_patch()) and (
                trajectory_oracle_scores.get("file_overlap", 0.0) >= 0.4
                or localization.total_score >= 0.5
            ) and status in {"verify_fail", "quality_fail"} and not _is_collector_side_no_patch(terminal_detail)

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
                teacher_calls=1 if rubric is not None else 0,
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
            localizations, generated_localizations = self._collect_localizations(task=task, oracle=oracle, rubric=rubric)
            localization_count += generated_localizations
            plans, generated_plans = self._collect_patch_plans(task=task, oracle=oracle, rubric=rubric, localizations=localizations)
            plan_count += generated_plans
            localization_by_id = {candidate.candidate_id: candidate for candidate in localizations}
            for plan_rank, plan in enumerate(plans, start=1):
                localization = localization_by_id.get(plan.localization_id)
                if localization is None:
                    continue
                loc_rank = localizations.index(localization) + 1
                temperature = self.temps[(plan_rank - 1) % len(self.temps)]
                trajectories.append(
                    self._sample_one(
                        task=task,
                        localization=localization,
                        localization_rank=loc_rank,
                        plan=plan,
                        plan_rank=plan_rank,
                        oracle=oracle,
                        rubric=rubric,
                        rubric_enabled=task_rubric_enabled,
                        rubric_degraded_reason=task_rubric_reason,
                        temperature=temperature,
                    )
                )
                realized_count += 1

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
            },
            notes={
                "sampling_temps": list(self.temps),
                "collector": self.collector_name,
                "localization_top_k": self.localization_top_k,
                "plan_samples_per_state": self.plan_samples_per_state,
                "max_realizations": self.max_realizations,
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
    cache_dir: str = "/tmp/orbit-swe-task-cache",
    max_steps: int = 24,
    resume: bool = False,
    temps: tuple[float, ...] = (0.3, 0.6, 0.9),
    localization_budget: int = 16,
    localization_top_k: int = 4,
    plan_samples_per_state: int = 2,
    max_realizations: int = 4,
) -> CollectResult:
    from .runtime import SweDockerWorkspaceRuntime

    task_source = SweTaskSource(cache_dir=cache_dir)
    runtime = SweDockerWorkspaceRuntime()
    teacher_session = None
    if teacher_endpoint or teacher_model or teacher_api_key:
        teacher_session = FailureCritiqueSession(endpoint=teacher_endpoint, model=teacher_model, api_key=teacher_api_key)
    elif resolve_teacher_endpoint() and resolve_teacher_api_key():
        teacher_session = FailureCritiqueSession()
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
        max_steps=max_steps,
        temps=temps,
        resume=resume,
        localization_budget=localization_budget,
        localization_top_k=localization_top_k,
        plan_samples_per_state=plan_samples_per_state,
        max_realizations=max_realizations,
    )
    return sampler.run(task_range=task_range, task_file=task_file)


__all__ = ["SweAutonomousSampler", "parse_sampling_temps", "run_swe_sampling"]
