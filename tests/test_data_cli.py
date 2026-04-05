"""Tests for LIVEWEB and MEMORYGYM data synthesis commands."""

import json
from pathlib import Path
from random import Random

from click.testing import CliRunner
import pytest

from orbit.cli import cli
from orbit.config import OrbitConfig
from orbit.data.aggregate import build_from_canonical
from orbit.data.memorygym_split import balance_samples, split_trajectory
from orbit.foundation.data_contracts import (
    CanonicalSyncReport,
    CollectedRawArtifact,
    IngestReport,
    PublishReport,
    RepoSyncReport,
)


def _config_for(tmp_path: Path):
    return OrbitConfig(
        project_root=tmp_path,
        data_dir=tmp_path / "data",
        machines_file=tmp_path / "machines.json",
    )

class TestLivewebCli:
    def test_liveweb_gen_dry_run_reports_plan(self, monkeypatch, tmp_path):
        monkeypatch.setattr("orbit.cli.OrbitConfig.load", lambda: _config_for(tmp_path))
        result = CliRunner().invoke(cli, ["data", "liveweb-gen", "--seeds", "1-10", "--dry-run"])
        assert result.exit_code == 0
        assert "Seeds: 1-10 (10)" in result.output
        assert "(dry-run" in result.output

    def test_liveweb_gen_remote_routes_through_control_kernel(self, monkeypatch, tmp_path):
        calls = {}

        def fake_remote_collect(*, config, spec, machine, output_path):
            calls.update(
                {
                    "config": config,
                    "spec": spec,
                    "machine": machine,
                    "output_path": output_path,
                }
            )
            Path(output_path).write_text(
                '{"messages":[{"role":"system","content":"x"},{"role":"user","content":"y"},{"role":"assistant","content":"z"}],"env":"LIVEWEB","score":1.0}\n',
                encoding="utf-8",
            )

        monkeypatch.setattr("orbit.cli.OrbitConfig.load", lambda: _config_for(tmp_path))
        monkeypatch.setattr("orbit.cli_data._run_remote_collect_via_control", fake_remote_collect)
        monkeypatch.setattr("orbit.data.liveweb_teacher_gen.require_liveweb_repo", lambda: tmp_path / "repos" / "liveweb-arena")
        monkeypatch.setattr("orbit.data.liveweb_teacher_gen.require_cache_dir", lambda path: Path(path))

        result = CliRunner().invoke(
            cli,
            [
                "data",
                "liveweb-gen",
                "--seeds",
                "1-10",
                "--cache-dir",
                str(tmp_path / "cache"),
                "-m",
                "m1",
            ],
        )

        assert result.exit_code == 0
        assert calls["machine"] == "m1"
        assert calls["spec"].env == "LIVEWEB"
        assert calls["spec"].collector == "liveweb-gen"
        assert Path(calls["output_path"]).name == "liveweb_teacher.jsonl"

    def test_liveweb_gen_local_ingest_uses_pipeline_ingest_report(self, monkeypatch, tmp_path):
        output_path = tmp_path / "lw.jsonl"
        calls = {"ingest": []}

        async def fake_generate(**kwargs):
            output_path.write_text('{"messages":[{"role":"system","content":"x"},{"role":"user","content":"y"},{"role":"assistant","content":"z"}],"env":"LIVEWEB","score":1.0}\n', encoding="utf-8")
            return {"records": 1, "errors": 0, "output": str(output_path)}

        monkeypatch.setattr("orbit.cli.OrbitConfig.load", lambda: _config_for(tmp_path))
        monkeypatch.setattr("orbit.data.liveweb_teacher_gen.require_liveweb_repo", lambda: tmp_path / "repos" / "liveweb-arena")
        monkeypatch.setattr("orbit.data.liveweb_teacher_gen.teacher_pipeline_ready", lambda path: (True, "ready"))
        monkeypatch.setattr("orbit.data.liveweb_teacher_gen.generate_liveweb_teacher_data", fake_generate)
        monkeypatch.setattr(
            "orbit.data.canonical_ops.ingest_staging",
            lambda **kwargs: calls["ingest"].append(kwargs)
            or IngestReport(
                status="success",
                appended=1,
                duplicates_skipped=0,
                new_total=1,
                hf_upload=CollectedRawArtifact(
                    status="success",
                    file="canonical/liveweb.jsonl",
                ),
            ),
        )

        result = CliRunner().invoke(
            cli,
            [
                "data",
                "liveweb-gen",
                "--seeds",
                "42",
                "--cache-dir",
                str(tmp_path / "cache"),
                "-o",
                str(output_path),
                "--ingest",
            ],
        )

        assert result.exit_code == 0
        assert calls["ingest"][0]["env"] == "LIVEWEB"


class TestGameCli:
    def test_game_gen_wires_into_generator_and_ingest(self, monkeypatch, tmp_path):
        calls = {"gen": [], "ingest": []}
        monkeypatch.setattr("orbit.cli.OrbitConfig.load", lambda: _config_for(tmp_path))
        monkeypatch.setattr(
            "orbit.data.game_gen.generate_game_data",
            lambda **kwargs: calls["gen"].append(kwargs) or {
                "records": 2,
                "per_game": {"goofspiel": 2},
                "output": kwargs["output_path"],
            },
        )
        monkeypatch.setattr(
            "orbit.data.canonical_ops.ingest_staging",
            lambda **kwargs: calls["ingest"].append(kwargs) or {
                "status": "success",
                "appended": 2,
                "duplicates_skipped": 0,
                "new_total": 2,
                "hf_upload": {"status": "success", "file": "canonical/game.jsonl"},
            },
        )

        result = CliRunner().invoke(
            cli,
            ["data", "game-gen", "--game", "goofspiel", "-n", "2", "-o", str(tmp_path / "game.jsonl"), "--ingest"],
        )

        assert result.exit_code == 0
        assert calls["gen"][0]["game_name"] == "goofspiel"
        assert calls["ingest"][0]["env"] == "GAME"

    def test_game_build_policy_uses_registry_defaults(self, monkeypatch, tmp_path):
        calls = []
        monkeypatch.setattr("orbit.cli.OrbitConfig.load", lambda: _config_for(tmp_path))
        monkeypatch.setattr(
            "orbit.data.game_generators.policy_generators.build_policy_snapshot",
            lambda **kwargs: calls.append(kwargs)
            or type(
                "Report",
                (),
                {"model_dump": lambda self, mode="json": {"game": "leduc_poker", "output": kwargs["output_path"]}},
            )(),
        )

        result = CliRunner().invoke(cli, ["data", "game-build-policy", "--game", "leduc_poker"])

        assert result.exit_code == 0
        assert calls[0]["game_name"] == "leduc_poker"
        assert calls[0]["family"] == "cfr"
        assert "leduc_poker" in calls[0]["output_path"]

    def test_game_policy_status_reports_snapshot_presence(self, monkeypatch, tmp_path):
        monkeypatch.setattr("orbit.cli.OrbitConfig.load", lambda: _config_for(tmp_path))
        monkeypatch.setattr(
            "orbit.data.game_generators.policy_generators.policy_status",
            lambda **kwargs: type(
                "Status",
                (),
                {"model_dump": lambda self, mode="json": {"game": kwargs["game_name"], "exists": False}},
            )(),
        )

        result = CliRunner().invoke(cli, ["data", "game-policy-status", "--game", "goofspiel"])

        assert result.exit_code == 0
        assert '"game": "goofspiel"' in result.output
        assert '"exists": false' in result.output

    def test_game_build_expert_dataset_calls_builder(self, monkeypatch, tmp_path):
        calls = []
        monkeypatch.setattr("orbit.cli.OrbitConfig.load", lambda: _config_for(tmp_path))
        monkeypatch.setattr(
            "orbit.data.game_policy_models.build_expert_dataset",
            lambda **kwargs: calls.append(kwargs)
            or type(
                "Report",
                (),
                {"model_dump": lambda self, mode="json": {"game": kwargs["game_name"], "samples": kwargs["trajectory_target"]}},
            )(),
        )

        result = CliRunner().invoke(
            cli,
            ["data", "game-build-expert-dataset", "--game", "leduc_poker", "--samples", "12"],
        )

        assert result.exit_code == 0
        assert calls[0]["game_name"] == "leduc_poker"
        assert calls[0]["trajectory_target"] == 12
        assert '"game": "leduc_poker"' in result.output

    def test_game_train_policy_model_calls_torch_trainer(self, monkeypatch, tmp_path):
        calls = []
        monkeypatch.setattr("orbit.cli.OrbitConfig.load", lambda: _config_for(tmp_path))
        monkeypatch.setattr(
            "orbit.data.game_policy_models.train_policy_model",
            lambda **kwargs: calls.append(kwargs)
            or type(
                "Report",
                (),
                {"model_dump": lambda self, mode="json": {"game": kwargs["game_name"], "checkpoint_path": "model.pt"}},
            )(),
        )

        result = CliRunner().invoke(
            cli,
            [
                "data",
                "game-train-policy-model",
                "--game",
                "goofspiel",
                "--dataset",
                str(tmp_path / "expert_dataset.npz"),
                "--epochs",
                "3",
            ],
        )

        assert result.exit_code == 0
        assert calls[0]["game_name"] == "goofspiel"
        assert calls[0]["epochs"] == 3
        assert '"checkpoint_path": "model.pt"' in result.output

    def test_game_policy_model_status_reports_artifact_presence(self, monkeypatch, tmp_path):
        monkeypatch.setattr("orbit.cli.OrbitConfig.load", lambda: _config_for(tmp_path))
        monkeypatch.setattr(
            "orbit.data.game_policy_models.policy_model_status",
            lambda **kwargs: type(
                "Status",
                (),
                {"model_dump": lambda self, mode="json": {"game": kwargs["game_name"], "exists": True}},
            )(),
        )

        result = CliRunner().invoke(cli, ["data", "game-policy-model-status", "--game", "goofspiel"])

        assert result.exit_code == 0
        assert '"game": "goofspiel"' in result.output
        assert '"exists": true' in result.output

    def test_game_selfplay_train_calls_selfplay_trainer(self, monkeypatch, tmp_path):
        calls = []
        monkeypatch.setattr("orbit.cli.OrbitConfig.load", lambda: _config_for(tmp_path))
        monkeypatch.setattr(
            "orbit.data.game_policy_models.train_selfplay_policy_model",
            lambda **kwargs: calls.append(kwargs)
            or type(
                "Report",
                (),
                {
                    "model_dump": lambda self, mode="json": {
                        "game": kwargs["game_name"],
                        "latest_checkpoint": "latest/model.pt",
                        "teacher_pass_streak": 1,
                    }
                },
            )(),
        )

        result = CliRunner().invoke(
            cli,
            [
                "data",
                "game-selfplay-train",
                "--game",
                "othello",
                "--episodes",
                "16",
                "--epochs",
                "2",
                "--repo",
                "user/private-policy",
            ],
        )

        assert result.exit_code == 0
        assert calls[0]["game_name"] == "othello"
        assert calls[0]["selfplay_episodes"] == 16
        assert calls[0]["epochs"] == 2
        assert calls[0]["repo_id"] == "user/private-policy"

    def test_game_selfplay_status_uses_status_helper(self, monkeypatch, tmp_path):
        monkeypatch.setattr("orbit.cli.OrbitConfig.load", lambda: _config_for(tmp_path))
        monkeypatch.setattr(
            "orbit.data.game_policy_models.selfplay_status",
            lambda **kwargs: type(
                "Status",
                (),
                {"model_dump": lambda self, mode="json": {"game": kwargs["game_name"], "best_exists": True}},
            )(),
        )

        result = CliRunner().invoke(cli, ["data", "game-selfplay-status", "--game", "goofspiel"])

        assert result.exit_code == 0
        assert '"game": "goofspiel"' in result.output
        assert '"best_exists": true' in result.output

    def test_game_selfplay_eval_calls_eval_helper(self, monkeypatch, tmp_path):
        calls = []
        monkeypatch.setattr("orbit.cli.OrbitConfig.load", lambda: _config_for(tmp_path))
        monkeypatch.setattr(
            "orbit.data.game_policy_models.evaluate_selfplay_policy_model",
            lambda **kwargs: calls.append(kwargs)
            or type(
                "Report",
                (),
                {"model_dump": lambda self, mode="json": {"game": kwargs["game_name"], "win_rate": 0.61}},
            )(),
        )

        result = CliRunner().invoke(
            cli,
            ["data", "game-selfplay-eval", "--game", "liars_dice", "--opponent", "teacher", "--games", "200"],
        )

        assert result.exit_code == 0
        assert calls[0]["opponent"] == "teacher"
        assert calls[0]["games"] == 200

    def test_game_selfplay_resume_calls_resume_helper(self, monkeypatch, tmp_path):
        calls = []
        monkeypatch.setattr("orbit.cli.OrbitConfig.load", lambda: _config_for(tmp_path))
        monkeypatch.setattr(
            "orbit.data.game_policy_models.resume_selfplay_policy_model",
            lambda **kwargs: calls.append(kwargs)
            or type(
                "Report",
                (),
                {"model_dump": lambda self, mode="json": {"game": kwargs["game_name"], "promoted": False}},
            )(),
        )

        result = CliRunner().invoke(
            cli,
            ["data", "game-selfplay-resume", "--game", "gin_rummy", "--episodes", "32", "--repo", "user/private-policy"],
        )

        assert result.exit_code == 0
        assert calls[0]["game_name"] == "gin_rummy"
        assert calls[0]["selfplay_episodes"] == 32
        assert calls[0]["repo_id"] == "user/private-policy"

    def test_game_upload_teacher_uses_registry_snapshot(self, monkeypatch, tmp_path):
        calls = []
        monkeypatch.setattr("orbit.cli.OrbitConfig.load", lambda: _config_for(tmp_path))
        monkeypatch.setattr(
            "orbit.data.game_teacher_repo.upload_teacher_snapshot",
            lambda **kwargs: calls.append(kwargs)
            or type(
                "Report",
                (),
                {"status": "success", "reason": "", "model_dump": lambda self, mode="json": {"repo_id": "user/private-teachers", "game": kwargs["game_name"]}},
            )(),
        )

        result = CliRunner().invoke(
            cli,
            ["data", "game-upload-teacher", "--game", "leduc_poker", "--repo", "user/private-teachers"],
        )

        assert result.exit_code == 0
        assert calls[0]["game_name"] == "leduc_poker"
        assert calls[0]["family"] == "cfr"
        assert "leduc_poker" in calls[0]["policy_path"]
        assert '"repo_id": "user/private-teachers"' in result.output

class TestMemorygymCli:
    def test_memorygym_gen_passes_tier_mix_and_templates(self, monkeypatch, tmp_path):
        calls = []
        monkeypatch.setattr("orbit.cli.OrbitConfig.load", lambda: _config_for(tmp_path))
        monkeypatch.setattr("orbit.data.memorygym_gen.require_memorygym_repo", lambda: tmp_path / "repos" / "MemoryGym")
        monkeypatch.setattr(
            "orbit.data.memorygym_gen.generate_dataset",
            lambda **kwargs: calls.append(kwargs)
            or {"output": kwargs["output"], "trajectories": 10},
        )

        result = CliRunner().invoke(
            cli,
            [
                "data",
                "memorygym-gen",
                "--seeds",
                "10",
                "--template",
                "company",
                "--tier-mix",
                "-j",
                "4",
                "-o",
                str(tmp_path / "mg_raw.jsonl"),
            ],
        )

        assert result.exit_code == 0
        assert calls[0]["templates"] == ["company"]
        assert calls[0]["tier_mix"] is True
        assert calls[0]["workers"] == 4
        assert '"trajectories": 10' in result.output

    def test_memorygym_split_ingest_wires_into_canonical(self, monkeypatch, tmp_path):
        calls = {"split": [], "ingest": []}
        monkeypatch.setattr("orbit.cli.OrbitConfig.load", lambda: _config_for(tmp_path))
        monkeypatch.setattr("orbit.data.memorygym_split.split_dataset", lambda **kwargs: calls["split"].append(kwargs) or {"samples": 2})
        monkeypatch.setattr(
            "orbit.data.canonical_ops.ingest_staging",
            lambda **kwargs: calls["ingest"].append(kwargs) or {
                "status": "success",
                "appended": 2,
                "duplicates_skipped": 0,
                "new_total": 2,
                "hf_upload": {"status": "success", "file": "canonical/memorygym.jsonl"},
            },
        )

        result = CliRunner().invoke(
            cli,
            [
                "data",
                "memorygym-split",
                "-i",
                str(tmp_path / "mg_raw.jsonl"),
                "-o",
                str(tmp_path / "memorygym.jsonl"),
                "--target",
                "5000",
                "--balance",
                "--ingest",
            ],
        )

        assert result.exit_code == 0
        assert calls["split"][0]["target"] == 5000
        assert calls["split"][0]["balance"] is True
        assert calls["ingest"][0]["env"] == "MEMORYGYM"


class TestSweCli:
    def test_swe_status_and_sync_forward_machine_selector(self, monkeypatch, tmp_path):
        status_calls = []
        sync_calls = []
        monkeypatch.setattr("orbit.cli.OrbitConfig.load", lambda: _config_for(tmp_path))
        monkeypatch.setattr(
            "orbit.data.swe_ops.distill_status",
            lambda machine=None: status_calls.append(machine) or {
                "running": False,
                "processes": [],
                "output_files": [],
                "containers": 0,
                "infra_error": None,
            },
        )
        monkeypatch.setattr("orbit.data.swe_ops.distill_log", lambda **kwargs: "(no log output)")
        monkeypatch.setattr(
            "orbit.data.swe_ops.sync_new_trajectories",
            lambda dry_run=False, machine=None: sync_calls.append((dry_run, machine)) or {
                "new_count": 0,
                "skipped_dup": 0,
                "skipped_invalid": 0,
                "total": 0,
                "blocked_reason": None,
            },
        )

        status_result = CliRunner().invoke(cli, ["data", "swe-status", "-m", "m1"])
        sync_result = CliRunner().invoke(cli, ["data", "swe-sync", "-m", "m1", "--dry-run"])

        assert status_result.exit_code == 0
        assert sync_result.exit_code == 0
        assert status_calls == ["m1"]
        assert sync_calls == [(True, "m1")]


class TestDatasetPublishCli:
    def test_canonical_sync_and_publish_mixed_use_helpers(self, monkeypatch, tmp_path):
        calls = {"sync": [], "publish": []}
        monkeypatch.setattr("orbit.cli.OrbitConfig.load", lambda: _config_for(tmp_path))
        monkeypatch.setattr(
            "orbit.data.canonical_ops.download_from_hf",
            lambda env, repo_id=None: calls["sync"].append((env, repo_id))
            or CanonicalSyncReport(status="success", env=env, path=f"/tmp/{env.lower()}.jsonl", repo_id=repo_id or ""),
        )
        monkeypatch.setattr(
            "orbit.data.canonical_ops.publish_mixed",
            lambda **kwargs: calls["publish"].append(kwargs)
            or PublishReport(status="success", repo_id=kwargs.get("repo_id", ""), rows=3),
        )
        monkeypatch.setattr(
            "orbit.data.canonical_ops.hf_sync_repo",
            lambda **kwargs: RepoSyncReport(status="success", repo_id=kwargs.get("repo_id", ""), downloaded=[]),
        )

        runner = CliRunner()
        sync_result = runner.invoke(cli, ["data", "canonical-sync", "--env", "GAME", "--repo", "user/repo"])
        publish_result = runner.invoke(
            cli,
            ["data", "publish-mixed", "--repo", "user/repo", "--canonical-dir", str(tmp_path / "canonical"), "--output-dir", str(tmp_path / "mixed")],
        )

        assert sync_result.exit_code == 0
        assert publish_result.exit_code == 0
        assert calls["sync"] == [("GAME", "user/repo")]
        assert calls["publish"][0]["repo_id"] == "user/repo"


class TestMemorygymSplit:
    def test_split_trajectory_marks_event_types_and_uppercase_env(self):
        entry = {
            "messages": [
                {"role": "system", "content": "budget"},
                {"role": "user", "content": "[DOCUMENTS] doc batch"},
                {"role": "assistant", "content": "<tool_call>{}</tool_call>"},
                {"role": "user", "content": "Your memory contains Alice"},
                {"role": "assistant", "content": "OK."},
                {"role": "user", "content": "[QUESTION] What is Alice's title?"},
                {"role": "assistant", "content": "<tool_call>{}</tool_call>"},
            ],
            "source": "hybrid",
            "template": "company",
            "seed": 7,
        }
        samples = split_trajectory(entry)
        assert samples
        assert samples[0]["env"] == "MEMORYGYM"
        assert samples[0]["event_type"] == "ingest"

    def test_balance_samples_respects_target_count(self):
        samples = []
        for event_type in ("ingest", "correction", "question", "noise"):
            for idx in range(10):
                samples.append(
                    {
                        "messages": [{"role": "system", "content": "x"}, {"role": "assistant", "content": "y"}],
                        "event_type": event_type,
                        "event_idx": idx,
                    }
                )
        balanced = balance_samples(samples, 20, Random(42))
        assert len(balanced) == 20


class TestMemorygymCanonicalIntegration:
    def test_build_from_canonical_includes_memorygym(self, tmp_path):
        canonical_dir = tmp_path / "canonical"
        canonical_dir.mkdir()
        (canonical_dir / "memorygym.jsonl").write_text(
            '{"env":"MEMORYGYM","score":1.0,"messages":[{"role":"system","content":"budget"},{"role":"user","content":"question"},{"role":"assistant","content":"answer"}]}\n',
            encoding="utf-8",
        )

        report = build_from_canonical(output_path=str(tmp_path / "train.jsonl"), canonical_dir=str(canonical_dir))
        assert report["by_env"]["MEMORYGYM"] == 1
