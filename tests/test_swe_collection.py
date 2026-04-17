"""Tests for the staged SWE collection subsystem."""

from __future__ import annotations

import json

from click.testing import CliRunner

from orbit.cli import cli
from orbit.data.swe_collection import (
    SweAutonomousSampler,
    SweBucketBuilder,
    SweCollectionExporter,
    SweFailureRelabeler,
    SweTaskSource,
    run_swe_train_verifier_dataset,
)
from orbit.data.swe_collection.sessions import CodexStudentSession, MiniSweStudentSession
from orbit.foundation.data_contracts import (
    CollectResult,
    ConversationMessage,
    SweBucketSampleV1,
    SweCritiqueRecordV1,
    SweFailurePointV1,
    SweRawTrajectoryV1,
)
from orbit.foundation.schema import FrozenModel


class FakeExecResult(FrozenModel):
    stdout: str = ""
    stderr: str = ""
    output: str = ""
    returncode: int = 0


class FakeWorkspace:
    def __init__(self, *, command_result: str = "edited", test_output: str = "ok", test_rc: int = 0, changed_files: list[str] | None = None):
        self.command_result = command_result
        self.test_output = test_output
        self.test_rc = test_rc
        self._changed_files = list(changed_files or [])
        self.commands: list[str] = []

    def exec(self, command: str, *, timeout: int = 120):
        self.commands.append(command)
        if "pytest" in command:
            return FakeExecResult(stdout=self.test_output, output=self.test_output, returncode=self.test_rc)
        return FakeExecResult(stdout=self.command_result, output=self.command_result, returncode=0)

    def changed_files(self) -> list[str]:
        return list(self._changed_files)

    def diff_patch(self) -> str:
        if not self._changed_files:
            return ""
        return "".join(f"diff --git a/{path} b/{path}\n" for path in self._changed_files)

    def git_status_short(self) -> str:
        return "\n".join(f"M {path}" for path in self._changed_files)

    def has_patch(self) -> bool:
        return bool(self._changed_files)

    def close(self) -> None:
        return None


class CountingWorkspace(FakeWorkspace):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.pytest_calls = 0

    def exec(self, command: str, *, timeout: int = 120):
        if "pytest" in command:
            self.pytest_calls += 1
        return super().exec(command, timeout=timeout)


class FakeRuntime:
    def __init__(self, workspace: FakeWorkspace):
        self.workspace = workspace

    def create_workspace(self, task: dict) -> FakeWorkspace:
        return self.workspace

    def probe_workspace(self, task: dict):
        return True, "ok"


class FakeMiniSession:
    format = "miniswe"
    endpoint = "https://student.example/v1"
    model = "student-mini"

    def __init__(self, turns: list[dict]):
        self.turns = list(turns)
        self.index = 0

    def initial_messages(self, task: dict) -> list[dict]:
        return [{"role": "system", "content": "solve"}, {"role": "user", "content": task["problem_statement"]}]

    def propose_localization(self, *, task: dict, temperature: float):
        return type(
            "LocalizationProposal",
            (),
            {
                "candidate_files": ("app.py",) if "app.py" in task.get("problem_statement", "") else ("target.py",),
                "candidate_symbols": ("fix_bug",),
                "hypothesis": "The failing logic lives in the selected file.",
                "edit_type": "guard",
                "raw_response": "{}",
            },
        )()

    def propose_patch_plan(self, *, task: dict, localization: dict, temperature: float):
        return type(
            "PatchPlanProposal",
            (),
            {
                "target_files": tuple(localization.get("candidate_files", []) or ("app.py",)),
                "target_symbols": tuple(localization.get("candidate_symbols", []) or ("fix_bug",)),
                "diff_sketch": "--- plan ---\n+ add guard\n",
                "plan_steps": ("edit target file", "run tests"),
                "edit_type": localization.get("edit_type", "guard"),
                "raw_response": "{}",
            },
        )()

    def next_turn(self, *, task: dict, messages: list[dict], temperature: float):
        if self.index >= len(self.turns):
            payload = {
                "assistant_message": {"role": "assistant", "content": "THOUGHT: stop\n```bash\n\n```"},
                "command": "",
                "submit": False,
            }
        else:
            payload = self.turns[self.index]
            self.index += 1
        return type(
            "StudentTurn",
            (),
            {
                "assistant_message": payload["assistant_message"],
                "command": payload["command"],
                "submit": payload.get("submit", False),
            },
        )()

    def observation_message(self, *, turn, output: str, returncode: int) -> dict:
        return {"role": "user", "content": f"<returncode>{returncode}</returncode><output>{output}</output>"}

    def verification_feedback(self, *, output: str) -> dict:
        return {"role": "user", "content": f"Tests still failing.\n{output}"}


class FakeCodexSession(FakeMiniSession):
    format = "codex"
    endpoint = "https://student.example/v1"
    model = "student-codex"

    def observation_message(self, *, turn, output: str, returncode: int) -> dict:
        tool_call_id = turn.assistant_message["tool_calls"][0]["id"]
        return {"role": "tool", "tool_call_id": tool_call_id, "content": json.dumps({"output": output, "metadata": {"exit_code": returncode}})}


class FakeCritiqueSession:
    endpoint = "https://teacher.example/v1"
    model = "teacher-critic"

    def __init__(self):
        self.calls: list[dict] = []

    def build_issue_rubric(self, *, task: dict, oracle: dict, temperature: float = 0.2):
        return type(
            "IssueRubricTurn",
            (),
            {
                "likely_modules": tuple(oracle.get("touched_files", [])),
                "required_constraints": ("keep tests green",),
                "common_pseudo_solutions": ("editing unrelated files",),
                "forbidden_patterns": ("massive refactor",),
                "raw_response": "{}",
            },
        )()

    def probe(self):
        return True, "ok"

    def critique_failure(self, *, task: dict, trajectory: dict, failure_point: dict, window: list[dict], rubric=None, localization=None, plan=None, temperature: float = 0.2):
        self.calls.append(
            {
                "task": task,
                "trajectory_id": trajectory["trajectory_id"],
                "failure_point": failure_point,
                "window": window,
                "rubric": rubric,
                "localization": localization,
                "plan": plan,
            }
        )
        return type(
            "CritiqueTurn",
            (),
            {
                "critique": "The patch changed the wrong file.",
                "revised_action": "sed -i 's/bad/good/' target.py",
                "raw_response": '{"critique":"The patch changed the wrong file.","revised_action":"sed -i \\"s/bad/good/\\" target.py"}',
            },
        )()


class FailingRubricSession(FakeCritiqueSession):
    def build_issue_rubric(self, *, task: dict, oracle: dict, temperature: float = 0.2):
        raise TimeoutError("teacher timeout")


class TestSweTaskSource:
    def test_parse_task_range_supports_multiple_spans(self):
        from orbit.data.swe_collection.task_source import parse_task_range

        assert parse_task_range("1-3,8,10-11") == [1, 2, 3, 8, 10, 11]

    def test_load_task_prefers_cache_and_normalizes_fields(self, tmp_path):
        source = SweTaskSource(cache_dir=str(tmp_path / "cache"))
        cached = source.cache_path_for(42)
        cached.write_text('{"instance_id":"i-42","repo":"org/repo"}\n', encoding="utf-8")

        task = source.load_task(42)

        assert task["instance_id"] == "i-42"
        assert task["repo"] == "org/repo"
        assert task["task_id"] == 42
        assert "base_commit" in task


class TestSweSessions:
    def test_miniswe_next_turn_accepts_unterminated_bash_fence(self):
        class StubClient:
            def complete(self, *, messages, temperature):
                return {
                    "content": (
                        "<think>\n\n</think>\n\n"
                        "THOUGHT: edit file\n\n"
                        "```bash\n"
                        "sed -i 's/fail/pass/' app.py && echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\n"
                    )
                }

        session = MiniSweStudentSession(client=StubClient())

        turn = session.next_turn(task={}, messages=[], temperature=0.2)

        assert turn.command == "sed -i 's/fail/pass/' app.py && echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"
        assert turn.submit is True

    def test_codex_next_turn_accepts_content_tool_call_fallback(self):
        class StubClient:
            def __init__(self):
                self.calls = 0

            def complete(self, *, messages, temperature):
                self.calls += 1
                if self.calls == 1:
                    return {
                        "content": (
                            "<think>\n\n</think>\n\n"
                            '<tool_call>{"name":"shell","arguments":{"command":"python -m py_compile app.py"}}</tool_call>'
                        ),
                        "tool_calls": [],
                    }
                return {"content": "", "tool_calls": []}

        session = CodexStudentSession(client=StubClient())

        turn = session.next_turn(task={}, messages=[], temperature=0.2)

        assert turn.command == "python -m py_compile app.py"
        assert turn.assistant_message["tool_calls"][0]["function"]["name"] == "shell"


class TestSweSample:
    def test_miniswe_sample_writes_raw_trajectory_and_states(self, tmp_path):
        task = {
            "task_id": 1,
            "instance_id": "i-1",
            "problem_statement": "fix app.py",
            "patch": "+++ b/app.py\n@@\n-fail\n+pass\n",
            "repo": "org/repo",
            "repo_language": "python",
            "test_command": "pytest -q",
            "fail_to_pass": ["test_app.py::test_fix"],
        }
        source = type("Source", (), {"iter_tasks": lambda self, **kwargs: [task]})()
        sampler = SweAutonomousSampler(
            fmt="miniswe",
            task_source=source,
            runtime=FakeRuntime(FakeWorkspace(changed_files=["app.py"], test_output="PASSED test_app.py::test_fix", test_rc=0)),
            student_session=FakeMiniSession(
                turns=[
                    {
                        "assistant_message": {
                            "role": "assistant",
                            "content": "THOUGHT: edit\n```bash\nsed -i 's/fail/pass/' app.py && echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\n```",
                        },
                        "command": "sed -i 's/fail/pass/' app.py && echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT",
                        "submit": True,
                    }
                ]
            ),
            output_dir=str(tmp_path),
            teacher_session=FakeCritiqueSession(),
            max_steps=3,
            temps=(0.3,),
            localization_budget=1,
            localization_top_k=1,
            plan_samples_per_state=1,
            max_realizations=1,
        )

        result = sampler.run(task_range="1-1")

        assert result.records == 1
        exporter = SweCollectionExporter(output_dir=str(tmp_path))
        rows = exporter.load_raw_trajectories()
        assert len(rows) == 1
        assert rows[0]["verify_passed"] is True
        assert rows[0]["terminal_status"] == "success"
        assert rows[0]["collector"] == "student_cascade_v1"
        assert rows[0]["base_instance_id"] == "i-1"
        assert rows[0]["instance_id"].startswith("i-1::loc1::patch1::r1")
        state_rows = exporter.load_step_states(rows[0]["state_paths"])
        assert len(state_rows) == 1
        assert state_rows[0]["changed_files"] == ["app.py"]
        assert len(exporter.load_issue_oracles()) == 1
        assert len(exporter.load_issue_rubrics()) == 1
        assert len(exporter.load_localizations()) == 1
        assert len(exporter.load_patch_plans()) == 1

    def test_sample_degrades_when_rubric_request_fails(self, tmp_path):
        task = {
            "task_id": 11,
            "instance_id": "i-11",
            "problem_statement": "fix app.py",
            "patch": "+++ b/app.py\n@@\n-fail\n+pass\n",
            "repo": "org/repo",
            "repo_language": "python",
            "test_command": "pytest -q",
            "fail_to_pass": ["test_app.py::test_fix"],
        }
        source = type("Source", (), {"iter_tasks": lambda self, **kwargs: [task]})()
        sampler = SweAutonomousSampler(
            fmt="miniswe",
            task_source=source,
            runtime=FakeRuntime(FakeWorkspace(changed_files=["app.py"], test_output="FAILED test_app.py::test_fix", test_rc=1)),
            student_session=FakeMiniSession(
                turns=[
                    {
                        "assistant_message": {
                            "role": "assistant",
                            "content": "THOUGHT: edit\n```bash\nsed -i 's/fail/pass/' app.py && echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\n```",
                        },
                        "command": "sed -i 's/fail/pass/' app.py && echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT",
                        "submit": True,
                    }
                ]
            ),
            output_dir=str(tmp_path),
            teacher_session=FailingRubricSession(),
            max_steps=3,
            temps=(0.3,),
            localization_budget=1,
            localization_top_k=1,
            plan_samples_per_state=1,
            max_realizations=1,
        )

        result = sampler.run(task_range="11-11")

        assert result.records == 1
        exporter = SweCollectionExporter(output_dir=str(tmp_path))
        row = exporter.load_raw_trajectories()[0]
        manifest = json.loads(exporter.run_manifest_path.read_text())
        assert row["rubric_enabled"] is False
        assert "teacher timeout" in row["rubric_degraded_reason"]
        assert manifest["rubric_enabled"] is False
        assert "teacher timeout" in manifest["rubric_degraded_reason"]
        assert manifest["teacher_probe_status"] == "ok"
        assert "teacher timeout" in result.reason

    def test_manifest_counts_actual_generated_candidates(self, tmp_path):
        task = {
            "task_id": 12,
            "instance_id": "i-12",
            "problem_statement": "fix app.py",
            "patch": "+++ b/app.py\n@@\n-fail\n+pass\n",
            "repo": "org/repo",
            "repo_language": "python",
            "test_command": "pytest -q",
            "fail_to_pass": ["test_app.py::test_fix"],
        }
        source = type("Source", (), {"iter_tasks": lambda self, **kwargs: [task]})()
        sampler = SweAutonomousSampler(
            fmt="miniswe",
            task_source=source,
            runtime=FakeRuntime(FakeWorkspace(changed_files=["app.py"], test_output="FAILED test_app.py::test_fix", test_rc=1)),
            student_session=FakeMiniSession(
                turns=[
                    {
                        "assistant_message": {
                            "role": "assistant",
                            "content": "THOUGHT: edit\n```bash\nsed -i 's/fail/pass/' app.py && echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\n```",
                        },
                        "command": "sed -i 's/fail/pass/' app.py && echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT",
                        "submit": True,
                    }
                ]
            ),
            output_dir=str(tmp_path),
            teacher_session=FakeCritiqueSession(),
            max_steps=3,
            temps=(0.3,),
            localization_budget=3,
            localization_top_k=1,
            plan_samples_per_state=2,
            max_realizations=1,
        )

        sampler.run(task_range="12-12")

        manifest = json.loads(SweCollectionExporter(output_dir=str(tmp_path)).run_manifest_path.read_text())
        assert manifest["stage_counts"]["localization_candidates"] == 3
        assert manifest["stage_counts"]["patch_plan_candidates"] == 2

    def test_codex_sample_keeps_assistant_tool_pairs(self, tmp_path):
        task = {
            "task_id": 2,
            "instance_id": "i-2",
            "problem_statement": "fix app.py",
            "patch": "+++ b/app.py\n@@\n-fail\n+pass\n",
            "repo": "org/repo",
            "repo_language": "python",
            "test_command": "pytest -q",
            "fail_to_pass": ["test_app.py::test_fix"],
        }
        source = type("Source", (), {"iter_tasks": lambda self, **kwargs: [task]})()
        session = FakeCodexSession(
            turns=[
                {
                    "assistant_message": {
                        "role": "assistant",
                        "content": "run shell COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "function": {"name": "shell", "arguments": {"command": "python -m fix app.py"}},
                            }
                        ],
                    },
                    "command": "python -m fix app.py",
                    "submit": True,
                }
            ]
        )
        sampler = SweAutonomousSampler(
            fmt="codex",
            task_source=source,
            runtime=FakeRuntime(FakeWorkspace(changed_files=["app.py"], test_output="PASSED test_app.py::test_fix", test_rc=0)),
            student_session=session,
            output_dir=str(tmp_path),
            teacher_session=FakeCritiqueSession(),
            max_steps=3,
            temps=(0.3,),
            localization_budget=1,
            localization_top_k=1,
            plan_samples_per_state=1,
            max_realizations=1,
        )

        sampler.run(task_range="2-2")

        row = SweCollectionExporter(output_dir=str(tmp_path)).load_raw_trajectories()[0]
        assert row["messages"][3]["tool_calls"][0]["function"]["name"] == "shell"
        assert row["messages"][4]["role"] == "tool"
        assert row["messages"][4]["tool_call_id"] == "call_1"

    def test_submit_verifies_once(self, tmp_path):
        task = {
            "task_id": 13,
            "instance_id": "i-13",
            "problem_statement": "fix app.py",
            "patch": "+++ b/app.py\n@@\n-fail\n+pass\n",
            "repo": "org/repo",
            "repo_language": "python",
            "test_command": "pytest -q",
            "fail_to_pass": ["test_app.py::test_fix"],
        }
        workspace = CountingWorkspace(changed_files=["app.py"], test_output="FAILED test_app.py::test_fix", test_rc=1)
        source = type("Source", (), {"iter_tasks": lambda self, **kwargs: [task]})()
        sampler = SweAutonomousSampler(
            fmt="miniswe",
            task_source=source,
            runtime=FakeRuntime(workspace),
            student_session=FakeMiniSession(
                turns=[
                    {
                        "assistant_message": {
                            "role": "assistant",
                            "content": "THOUGHT: edit\n```bash\nsed -i 's/fail/pass/' app.py && echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\n```",
                        },
                        "command": "sed -i 's/fail/pass/' app.py && echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT",
                        "submit": True,
                    }
                ]
            ),
            output_dir=str(tmp_path),
            teacher_session=FakeCritiqueSession(),
            max_steps=1,
            temps=(0.3,),
            localization_budget=1,
            localization_top_k=1,
            plan_samples_per_state=1,
            max_realizations=1,
        )

        sampler.run(task_range="13-13")

        assert workspace.pytest_calls == 1


class TestSweRelabel:
    def test_relabel_localizes_failure_and_writes_critique(self, tmp_path):
        task = {
            "task_id": 3,
            "instance_id": "i-3",
            "problem_statement": "fix target.py",
            "patch": "+++ b/target.py\n@@\n-bad\n+good\n",
            "repo": "org/repo",
            "repo_language": "python",
            "test_command": "pytest -q",
            "fail_to_pass": ["test_target.py::test_fix"],
        }
        source = type("Source", (), {"iter_tasks": lambda self, **kwargs: [task]})()
        sampler = SweAutonomousSampler(
            fmt="miniswe",
            task_source=source,
            runtime=FakeRuntime(FakeWorkspace(changed_files=["other.py"], test_output="FAILED test_target.py::test_fix", test_rc=1)),
            student_session=FakeMiniSession(
                turns=[
                    {
                        "assistant_message": {
                            "role": "assistant",
                            "content": "THOUGHT: edit\n```bash\nsed -i 's/bad/good/' other.py && echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\n```",
                        },
                        "command": "sed -i 's/bad/good/' other.py && echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT",
                        "submit": True,
                    }
                ]
            ),
            output_dir=str(tmp_path),
            teacher_session=FakeCritiqueSession(),
            max_steps=2,
            temps=(0.3,),
            localization_budget=1,
            localization_top_k=1,
            plan_samples_per_state=1,
            max_realizations=1,
        )
        sampler.run(task_range="3-3")

        critique_session = FakeCritiqueSession()
        relabeler = SweFailureRelabeler(
            output_dir=str(tmp_path),
            task_source=type("TaskSource", (), {"load_task": lambda self, task_id: task})(),
            critique_session=critique_session,
            window_radius=1,
            max_repairs=2,
        )

        result = relabeler.run()

        assert result.records == 1
        exporter = SweCollectionExporter(output_dir=str(tmp_path))
        failure_points = exporter.load_failure_points()
        critiques = exporter.load_critiques()
        assert failure_points[0]["failure_kind"] == "wrong_patch"
        assert "ref_files" in failure_points[0]["offline_hints_used"]
        assert critiques[0]["revised_action"] == "sed -i 's/bad/good/' target.py"
        assert len(critique_session.calls) == 1
        assert len(critique_session.calls[0]["window"]) == 1
        assert critique_session.calls[0]["rubric"]["likely_modules"] == ["target.py"]

    def test_relabel_skips_collector_side_failures(self, tmp_path):
        task = {
            "task_id": 31,
            "instance_id": "i-31",
            "problem_statement": "fix target.py",
            "patch": "+++ b/target.py\n@@\n-bad\n+good\n",
            "repo": "org/repo",
            "repo_language": "python",
            "test_command": "pytest -q",
        }
        exporter = SweCollectionExporter(output_dir=str(tmp_path))
        exporter.append_raw_trajectory(
            SweRawTrajectoryV1(
                trajectory_id="traj-collector-failure",
                run_id="run-x",
                instance_id="i-31::loc1::patch1::r1",
                base_instance_id="i-31",
                repo="org/repo",
                language="python",
                format="miniswe",
                sampling_temperature=0.3,
                student_model="student",
                student_endpoint="https://student.example/v1",
                collector="student_cascade_v1",
                teacher_calls=0,
                repair_round=0,
                rubric_score=0.0,
                oracle_scores={},
                localization_id="loc-1",
                plan_id="plan-1",
                messages=(ConversationMessage(role="assistant", content="THOUGHT only"),),
                state_paths=(),
                final_patch="",
                terminal_status="no_patch",
                terminal_detail="truncated_action",
                verify_passed=False,
                terminal_output="",
                assistant_turns=1,
                changed_files=(),
                rubric_enabled=False,
                rubric_degraded_reason="",
                task_metadata={"task_id": 31, "near_miss": False},
                raw_log_path="",
            )
        )
        relabeler = SweFailureRelabeler(
            output_dir=str(tmp_path),
            task_source=type("TaskSource", (), {"load_task": lambda self, task_id: task})(),
            critique_session=FakeCritiqueSession(),
            max_repairs=2,
        )

        result = relabeler.run()

        assert result.records == 0
        assert exporter.load_failure_points() == []

    def test_relabel_caps_repairs_at_max_repairs(self, tmp_path):
        task = {
            "task_id": 4,
            "instance_id": "i-4",
            "problem_statement": "fix app.py",
            "patch": "+++ b/app.py\n@@\n-fail\n+pass\n",
            "repo": "org/repo",
            "repo_language": "python",
            "test_command": "pytest -q",
            "fail_to_pass": ["test_app.py::test_fix"],
        }
        exporter = SweCollectionExporter(output_dir=str(tmp_path))
        for idx in range(3):
            exporter.append_raw_trajectory(
                SweRawTrajectoryV1(
                    trajectory_id=f"traj-{idx}",
                    run_id="run",
                    instance_id=f"i-4::loc{idx+1}::patch1::r1",
                    base_instance_id="i-4",
                    repo="org/repo",
                    language="python",
                    format="miniswe",
                    sampling_temperature=0.3,
                    student_model="student",
                    student_endpoint="https://student.example/v1",
                    collector="student_cascade_v1",
                    teacher_calls=1,
                    repair_round=0,
                    rubric_score=0.7 - idx * 0.1,
                    oracle_scores={"total": 0.8 - idx * 0.1},
                    localization_id=f"loc-{idx}",
                    plan_id=f"plan-{idx}",
                    messages=(
                        ConversationMessage(role="system", content="solve"),
                        ConversationMessage(role="user", content="fix"),
                        ConversationMessage(role="assistant", content="THOUGHT\n```bash\nsed -i 's/fail/pass/' app.py\n```"),
                        ConversationMessage(role="user", content="<returncode>1</returncode><output>fail</output>"),
                    ),
                    state_paths=(),
                    final_patch="diff --git a/app.py b/app.py\n",
                    terminal_status="verify_fail",
                    verify_passed=False,
                    terminal_output="FAILED test_app.py::test_fix",
                    assistant_turns=1,
                    changed_files=("app.py",),
                    task_metadata={"task_id": 4, "near_miss": True},
                    raw_log_path="",
                )
            )
        exporter.append_issue_rubric(
            __import__("orbit.foundation.data_contracts", fromlist=["SweIssueRubricV1"]).SweIssueRubricV1(
                rubric_id="i-4-rubric",
                base_instance_id="i-4",
                likely_modules=("app.py",),
            )
        )
        critique_session = FakeCritiqueSession()
        relabeler = SweFailureRelabeler(
            output_dir=str(tmp_path),
            task_source=type("TaskSource", (), {"load_task": lambda self, task_id: task})(),
            critique_session=critique_session,
            max_repairs=2,
        )

        result = relabeler.run()

        assert result.success == 2
        critiques = exporter.load_critiques()
        assert len(critiques) == 2


class TestSweBuckets:
    def test_bucket_builder_generates_a_b_c_v_and_canonical(self, tmp_path):
        exporter = SweCollectionExporter(output_dir=str(tmp_path))
        success = SweRawTrajectoryV1(
            trajectory_id="traj-success",
            run_id="run-a",
            instance_id="i-success::loc1::patch1::r1",
            base_instance_id="i-success",
            repo="org/repo",
            language="python",
            format="miniswe",
            sampling_temperature=0.3,
            student_model="student-mini",
            student_endpoint="https://student.example/v1",
            collector="student_cascade_v1",
            teacher_calls=1,
            repair_round=0,
            rubric_score=0.8,
            oracle_scores={"file_overlap": 1.0, "total": 1.0},
            localization_id="loc-1",
            plan_id="plan-1",
            messages=(
                ConversationMessage(role="system", content="solve"),
                ConversationMessage(role="user", content="fix"),
                ConversationMessage(role="assistant", content="THOUGHT\n```bash\nsed -i 's/x/y/' app.py\n```"),
                ConversationMessage(role="user", content="<returncode>0</returncode><output>ok</output>"),
            ),
            state_paths=(),
            final_patch="diff --git a/app.py b/app.py\n",
            terminal_status="success",
            verify_passed=True,
            terminal_output="PASSED test_ok",
            assistant_turns=1,
            changed_files=("app.py",),
            task_metadata={"task_id": 1},
            raw_log_path=str(tmp_path / "logs" / "traj-success.log"),
        )
        failure = SweRawTrajectoryV1(
            trajectory_id="traj-failure",
            run_id="run-b",
            instance_id="i-failure::loc1::patch1::r1",
            base_instance_id="i-failure",
            repo="org/repo",
            language="python",
            format="codex",
            sampling_temperature=0.3,
            student_model="student-codex",
            student_endpoint="https://student.example/v1",
            collector="student_cascade_v1",
            teacher_calls=1,
            repair_round=0,
            rubric_score=0.6,
            oracle_scores={"file_overlap": 0.7, "total": 0.65},
            localization_id="loc-2",
            plan_id="plan-2",
            messages=(
                ConversationMessage(role="system", content="solve", tools=[]),
                ConversationMessage(role="user", content="fix"),
                ConversationMessage(
                    role="assistant",
                    content="inspect",
                    tool_calls=[{"id": "call_1", "function": {"name": "shell", "arguments": {"command": "ls"}}}],
                ),
                ConversationMessage(role="tool", tool_call_id="call_1", content='{"output":"ok"}'),
            ),
            state_paths=(),
            final_patch="diff --git a/other.py b/other.py\n",
            terminal_status="verify_fail",
            verify_passed=False,
            terminal_output="FAILED test_target",
            assistant_turns=1,
            changed_files=("other.py",),
            task_metadata={"task_id": 2},
            raw_log_path=str(tmp_path / "logs" / "traj-failure.log"),
        )
        exporter.append_raw_trajectory(success)
        exporter.append_raw_trajectory(failure)
        exporter.append_failure_point(
            SweFailurePointV1(
                failure_id="traj-failure-failure",
                trajectory_id="traj-failure",
                instance_id="i-failure::loc1::patch1::r1",
                base_instance_id="i-failure",
                format="codex",
                step_index=0,
                failure_kind="wrong_patch",
                localization_evidence="last state touching wrong file",
                offline_hints_used=("ref_files",),
            )
        )
        exporter.append_critique(
            SweCritiqueRecordV1(
                critique_id="traj-failure-failure-critique",
                trajectory_id="traj-failure",
                failure_id="traj-failure-failure",
                instance_id="i-failure::loc1::patch1::r1",
                base_instance_id="i-failure",
                format="codex",
                teacher_model="teacher-critic",
                teacher_endpoint="https://teacher.example/v1",
                repair_round=1,
                near_miss=True,
                rubric_score=0.6,
                oracle_scores={"file_overlap": 0.7, "total": 0.65},
                localization_id="loc-2",
                plan_id="plan-2",
                critique="The patch changed the wrong file.",
                revised_action="sed -i 's/bad/good/' target.py",
                raw_response="{}",
            )
        )

        result = SweBucketBuilder(output_dir=str(tmp_path)).run()

        assert result.distribution == {"A": 1, "B": 1, "C": 1, "V": 2}
        assert len(exporter.load_bucket_samples("A")) == 1
        assert len(exporter.load_bucket_samples("B")) == 1
        assert len(exporter.load_bucket_samples("C")) == 1
        assert len(exporter.load_bucket_samples("V")) == 2
        canonical_rows = [json.loads(line) for line in (tmp_path / "canonical" / "swe_infinite.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(canonical_rows) == 1
        assert canonical_rows[0]["instance_id"] == "i-success::loc1::patch1::r1"
        assert canonical_rows[0]["base_instance_id"] == "i-success"
        assert canonical_rows[0]["messages"][-1]["role"] == "assistant"

    def test_train_verifier_dataset_emits_verifier_rows(self, tmp_path):
        exporter = SweCollectionExporter(output_dir=str(tmp_path))
        exporter.append_bucket_sample(
            SweBucketSampleV1(
                sample_id="traj-v",
                bucket="V",
                instance_id="i-v",
                trajectory_id="traj-v",
                format="miniswe",
                terminal_success=False,
                first_error_index=1,
                process_weights=(0.5, -1.0),
                metadata={"verifier_result": {"success": False, "first_error_index": 1}},
            )
        )

        result = run_swe_train_verifier_dataset(input_dir=str(tmp_path))

        assert result.records == 1
        rows = [json.loads(line) for line in (tmp_path / "buckets" / "verifier_train.jsonl").read_text(encoding="utf-8").splitlines()]
        assert rows[0]["first_error_index"] == 1
        assert rows[0]["verifier_result"]["success"] is False


class TestSweCollectCli:
    def test_cli_wires_sample_subcommand(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "orbit.cli_data._run_swe_sampling",
            lambda **kwargs: CollectResult(
                output=str(tmp_path / "raw" / "trajectories.jsonl"),
                staging_path=str(tmp_path / "raw" / "trajectories.jsonl"),
                raw_path=str(tmp_path / "raw"),
                records=2,
                success=1,
                failed=1,
            ),
        )

        result = CliRunner().invoke(
            cli,
            [
                "data",
                "swe-collect",
                "sample",
                "--task-range",
                "1-2",
                "--format",
                "codex",
                "--output-dir",
                str(tmp_path / "run"),
            ],
        )

        assert result.exit_code == 0
        assert "Profile: codex_student_cascade_v1" in result.output
