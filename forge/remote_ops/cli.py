"""Remote-ops CLI family."""

import click

from forge.remote_ops.machine import machine


@click.group()
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
    from forge.deploy import DeployPipeline

    config = ctx.obj["config"]
    revision = DeployPipeline(config).merge_and_upload(adapter_source, deploy_repo, base_model)
    click.echo(f"\nRevision: {revision}")


@deploy.command()
@click.argument("hf_repo")
@click.option("--revision", default="main", help="HF repo revision")
@click.pass_context
def chutes_config(ctx, hf_repo, revision):
    """Generate Chutes deployment config."""
    from forge.deploy import DeployPipeline

    DeployPipeline(ctx.obj["config"]).generate_deploy_script(hf_repo, revision)


@deploy.command(name="plan")
@click.option("--adapter", default="", help="LoRA adapter source HF repo")
@click.option("--deploy-repo", default="", help="Target HF repo for merged model")
@click.option("--base-model", default="Qwen/Qwen3-32B", help="Base model")
@click.pass_context
def deploy_plan(ctx, adapter, deploy_repo, base_model):
    """Show deployment plan."""
    from forge.deploy import DeployPipeline

    DeployPipeline(ctx.obj["config"]).full_deploy_plan(adapter, deploy_repo, base_model)

remote.add_command(machine, name="machine")
remote.add_command(deploy)
