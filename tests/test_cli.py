"""CLI smoke tests for command-family boundaries."""

import os
import sys

from click.testing import CliRunner

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from forge.cli import cli


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
