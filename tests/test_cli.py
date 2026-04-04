"""CLI tests for current command-family boundaries and active command paths."""

import json
import tomllib
from pathlib import Path

from forge.cli import build_cli, cli


def _has_command(output: str, command: str) -> bool:
    return (
        f"\n  {command} " in output
        or f"\n  {command}\n" in output
        or output.rstrip().endswith(f"\n  {command}")
    )


class TestRootCliFamilies:
    def test_pyproject_exposes_forge_console_script(self):
        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text())
        assert data["project"]["scripts"]["forge"] == "forge.cli:main"
        extras = data["project"]["optional-dependencies"]
        assert {"control", "exec", "all"} <= set(extras)
        assert "aiohttp>=3,<4" in extras["control"]
        assert "docker" in extras["exec"]
        assert extras["all"] == ["affine-forge[control,exec]"]

    def test_root_help_without_plugins_shows_install_guidance(self, cli_runner):
        empty_cli = build_cli(command_loader=lambda: [])
        result = cli_runner.invoke(empty_cli, ["--help"])
        assert result.exit_code == 0
        assert "uv pip install -e .[control]" in result.output
        assert not _has_command(result.output, "control")

    def test_root_help_lists_family_commands(self, cli_runner):
        result = cli_runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        for command in ["data", "control", "worker", "remote", "monitor"]:
            assert _has_command(result.output, command)

    def test_control_help_lists_new_groups(self, cli_runner):
        result = cli_runner.invoke(cli, ["control", "--help"])
        assert result.exit_code == 0
        for command in ["template", "experiment", "prepare", "launch", "submit", "run"]:
            assert _has_command(result.output, command)

    def test_control_launch_help_lists_train(self, cli_runner):
        result = cli_runner.invoke(cli, ["control", "launch", "--help"])
        assert result.exit_code == 0
        assert _has_command(result.output, "train")

    def test_worker_help_lists_execution_only_commands(self, cli_runner):
        result = cli_runner.invoke(cli, ["worker", "--help"])
        assert result.exit_code == 0
        for command in ["run", "status", "logs", "collect", "terminate", "validate-bundle"]:
            assert _has_command(result.output, command)
        assert "render" not in result.output


class TestControlCli:
    def test_template_list_and_show(self, cli_runner):
        listed = cli_runner.invoke(cli, ["control", "template", "list"])
        assert listed.exit_code == 0
        assert "local-host" in listed.output
        shown = cli_runner.invoke(cli, ["control", "template", "show", "local-host"])
        assert shown.exit_code == 0
        payload = json.loads(shown.output)
        assert payload["id"] == "local-host"

    def test_experiment_create_and_show(self, cli_runner, tmp_path):
        create = cli_runner.invoke(
            cli,
            [
                "control",
                "--dir",
                str(tmp_path),
                "experiment",
                "create",
                "--id",
                "v-test",
                "--variable",
                "improve_navworld",
                "--hypothesis",
                "more data helps",
                "--train-config",
                '{"model":"Qwen/Qwen3-32B","learning_rate":0.0001,"lora_rank":64,"max_length":4096,"num_train_epochs":1,"output_dir":"/tmp/checkpoints"}',
                "--data-config",
                '{"GAME":{"count":100}}',
            ],
        )
        assert create.exit_code == 0
        show = cli_runner.invoke(cli, ["control", "--dir", str(tmp_path), "experiment", "show", "v-test", "--json"])
        assert show.exit_code == 0
        payload = json.loads(show.output)
        assert payload["id"] == "v-test"
        assert payload["variable"] == "improve_navworld"

    def test_prepare_train_creates_bundle(self, cli_runner, tmp_path):
        dataset = tmp_path / "train.jsonl"
        dataset.write_text('{"messages":[]}\n')
        cli_runner.invoke(
            cli,
            [
                "control",
                "--dir",
                str(tmp_path / "experiments"),
                "experiment",
                "create",
                "--id",
                "v-test",
                "--variable",
                "improve_navworld",
                "--hypothesis",
                "more data helps",
                "--train-config",
                '{"model":"Qwen/Qwen3-32B","learning_rate":0.0001,"lora_rank":64,"max_length":4096,"num_train_epochs":1,"output_dir":"/tmp/checkpoints"}',
                "--data-config",
                '{"GAME":{"count":100}}',
            ],
        )
        bundle_dir = tmp_path / "bundle"
        result = cli_runner.invoke(
            cli,
            [
                "control",
                "--dir",
                str(tmp_path / "experiments"),
                "prepare",
                "train",
                "v-test",
                str(dataset),
                "--bundle-dir",
                str(bundle_dir),
            ],
        )
        assert result.exit_code == 0
        assert bundle_dir.exists()
        assert (bundle_dir / "job.json").exists()
