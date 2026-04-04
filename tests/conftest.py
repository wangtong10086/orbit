from __future__ import annotations

import sys
from pathlib import Path

from click.testing import CliRunner
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def config_factory():
    from forge.config import ForgeConfig

    def _make(project_root: Path) -> ForgeConfig:
        return ForgeConfig(
            project_root=project_root,
            data_dir=project_root / "data",
            machines_file=project_root / "machines.json",
        )

    return _make


@pytest.fixture(autouse=True)
def _load_all_cli_plugins():
    from forge.cli import cli
    from forge.cli_control import control
    from forge.cli_data import data
    from forge.cli_worker import worker
    from forge.monitoring.cli import monitor
    from forge.remote_ops.cli import remote

    original_loader = getattr(cli, "_command_loader", None)
    cli._command_loader = lambda: [control, data, worker, remote, monitor]
    cli._commands_loaded = False
    cli.commands.clear()
    yield
    cli.commands.clear()
    cli._commands_loaded = False
    if original_loader is not None:
        cli._command_loader = original_loader
