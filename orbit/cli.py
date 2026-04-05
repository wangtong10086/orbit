"""CLI entry point host for ORBIT."""

from __future__ import annotations

from importlib import metadata

import click

from orbit.config import OrbitConfig

CLI_ENTRYPOINT_GROUP = "orbit.cli_commands"
INSTALL_GUIDANCE = """\
Install command families with extras:
  uv pip install -e .[control]
  uv pip install -e .[exec]
  uv pip install -e .[all]
"""


def _load_installed_commands() -> list[click.Command]:
    commands: list[click.Command] = []
    seen: set[str] = set()
    for entry_point in sorted(metadata.entry_points(group=CLI_ENTRYPOINT_GROUP), key=lambda item: item.name):
        try:
            command = entry_point.load()
        except Exception as exc:
            click.echo(f"Warning: failed to load CLI command {entry_point.name!r}: {exc}", err=True)
            continue
        if not isinstance(command, click.core.BaseCommand):
            click.echo(f"Warning: CLI entry point {entry_point.name!r} is not a click command, skipping", err=True)
            continue
        if command.name in seen:
            continue  # silently skip duplicates from plugin packages
        seen.add(command.name)
        commands.append(command)
    return commands


class OrbitCli(click.Group):
    """CLI group that loads installed command families lazily."""

    def __init__(self, *args, command_loader=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._command_loader = command_loader or _load_installed_commands
        self._commands_loaded = False

    def _ensure_commands_loaded(self) -> None:
        if self._commands_loaded:
            return
        for command in self._command_loader():
            self.add_command(command)
        self._commands_loaded = True

    def list_commands(self, ctx):
        self._ensure_commands_loaded()
        return super().list_commands(ctx)

    def get_command(self, ctx, cmd_name):
        self._ensure_commands_loaded()
        return super().get_command(ctx, cmd_name)


def build_cli(command_loader=None) -> OrbitCli:
    @click.group(
        cls=OrbitCli,
        command_loader=command_loader,
        epilog=INSTALL_GUIDANCE,
    )
    @click.pass_context
    def root(ctx):
        """ORBIT - Orchestrated Research, Benchmarking, and Iterative Training"""
        ctx.ensure_object(dict)
        ctx.obj["config"] = OrbitConfig.load()

    return root


cli = build_cli()


def main():
    cli(obj={})
