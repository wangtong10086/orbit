"""CLI tests for command-family boundaries and active command paths."""

import json
import os
import sys
from types import SimpleNamespace

from click.testing import CliRunner

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from forge.cli import cli
from forge.compute.base import GpuInstance
from forge.config import ForgeConfig


def _config_for(tmp_path):
    return ForgeConfig(
        project_root=tmp_path,
        data_dir=tmp_path / "data",
        machines_file=tmp_path / "machines.json",
    )


class TestRootCliFamilies:
    def test_root_help_lists_family_commands(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        for command in ["data", "train", "eval", "exp", "remote", "monitor"]:
            assert command in result.output

    def test_remote_help_lists_sidecar_subgroups(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["remote", "--help"])
        assert result.exit_code == 0
        for command in ["machine", "compute", "deploy"]:
            assert command in result.output

    def test_monitor_help_lists_leaderboard_commands(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["monitor", "--help"])
        assert result.exit_code == 0
        for command in ["leaderboard", "weaknesses"]:
            assert command in result.output

    def test_exp_list_respects_experiments_dir(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(cli, ["exp", "--dir", str(tmp_path), "list"])
        assert result.exit_code == 0

    def test_eval_run_executes_pipeline_command(self, monkeypatch, tmp_path):
        captured = {}

        class FakePipeline:
            def __init__(self, envs):
                captured["envs"] = envs

            def run(self, **kwargs):
                captured["kwargs"] = kwargs
                return SimpleNamespace(
                    model_path=kwargs["model_path"],
                    geo_mean=42.0,
                    results={
                        "GAME": SimpleNamespace(mean_score=55.0, sample_count=12, completeness=1.0),
                    },
                )

        monkeypatch.setattr("forge.cli.ForgeConfig.load", lambda: _config_for(tmp_path))
        monkeypatch.setattr("forge.cli_eval.EvaluationPipeline", FakePipeline)

        runner = CliRunner()
        result = runner.invoke(cli, ["eval", "run", "--model", "/tmp/model", "--envs", "GAME,NAVWORLD", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert captured["envs"] == ["GAME", "NAVWORLD"]
        assert captured["kwargs"]["model_path"] == "/tmp/model"
        assert payload["geo_mean"] == 42.0
        assert payload["results"]["GAME"]["sample_count"] == 12

    def test_remote_machine_exec_runs_sidecar_command(self, monkeypatch, tmp_path):
        backend_calls = []

        class FakeBackend:
            async def exec(self, inst, command, timeout=60):
                backend_calls.append((inst.id, command, timeout))
                return 0, "remote-ok\n", ""

        instance = GpuInstance(id="m1", backend="ssh", gpu_type="H200", status="ready", host="localhost")

        monkeypatch.setattr("forge.cli.ForgeConfig.load", lambda: _config_for(tmp_path))
        monkeypatch.setattr("forge.remote_ops.machine_runtime.get_rental", lambda config, machine_selector=None: (FakeBackend(), instance))

        runner = CliRunner()
        result = runner.invoke(cli, ["remote", "machine", "exec", "echo ok"])
        assert result.exit_code == 0
        assert "remote-ok" in result.output
        assert backend_calls == [("m1", "echo ok", 60)]

    def test_data_status_reads_repo_root_synth_config(self, monkeypatch, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        output_file = data_dir / "game.jsonl"
        output_file.write_text('{"messages":[]}\n{"messages":[]}\n')
        synth_config = {
            "status": "active",
            "environments": {
                "GAME": {
                    "enabled": True,
                    "priority": 1,
                    "current_count": 2,
                    "target_count": 4,
                    "output": "data/game.jsonl",
                }
            },
        }
        (tmp_path / "synth_config.json").write_text(json.dumps(synth_config))

        monkeypatch.setattr("forge.cli.ForgeConfig.load", lambda: _config_for(tmp_path))

        runner = CliRunner()
        result = runner.invoke(cli, ["data", "status"])
        assert result.exit_code == 0
        assert "GAME" in result.output
        assert "need 2" in result.output
