"""Remote-ops CLI family."""

from __future__ import annotations

import click


class RemoteCli(click.Group):
    """Lazy-loading remote command family.

    Avoid importing optional Targon/httpx dependencies when unrelated command
    families such as `orbit data ...` are invoked from a minimal install.
    """

    _COMMANDS = ("deploy", "machine", "targon")

    def list_commands(self, ctx):
        return list(self._COMMANDS)

    def get_command(self, ctx, cmd_name):
        if cmd_name == "machine":
            from orbit.remote_ops.machine import machine

            return machine
        if cmd_name == "targon":
            from orbit.remote_ops.targon_debug import targon_debug

            return targon_debug
        if cmd_name == "deploy":
            return deploy
        return None


@click.group(cls=RemoteCli)
def remote():
    """Remote operations and deployment sidecar."""
    pass


@click.group()
@click.pass_context
def deploy(ctx):
    """Deployment-related remote operations."""
    ctx.ensure_object(dict)


@deploy.command()
@click.argument("adapter_source")
@click.option("--deploy-repo", required=True, help="Target HF repo for merged model")
@click.option("--base-model", default="Qwen/Qwen3-32B", help="Base model")
@click.pass_context
def merge(ctx, adapter_source, deploy_repo, base_model):
    """Merge LoRA adapter and upload to HF."""
    from orbit.deploy import DeployPipeline

    config = ctx.obj["config"]
    revision = DeployPipeline(config).merge_and_upload(adapter_source, deploy_repo, base_model)
    click.echo(f"\nRevision: {revision}")


@deploy.command()
@click.argument("hf_repo")
@click.option("--revision", default="main", help="HF repo revision")
@click.pass_context
def chutes_config(ctx, hf_repo, revision):
    """Generate Chutes deployment config."""
    from orbit.deploy import DeployPipeline

    DeployPipeline(ctx.obj["config"]).generate_deploy_script(hf_repo, revision)


@deploy.command(name="plan")
@click.option("--adapter", default="", help="LoRA adapter source HF repo")
@click.option("--deploy-repo", default="", help="Target HF repo for merged model")
@click.option("--base-model", default="Qwen/Qwen3-32B", help="Base model")
@click.pass_context
def deploy_plan(ctx, adapter, deploy_repo, base_model):
    """Show deployment plan."""
    from orbit.deploy import DeployPipeline

    DeployPipeline(ctx.obj["config"]).full_deploy_plan(adapter, deploy_repo, base_model)
