"""Remote-ops CLI family."""

import click

from forge.domain_jobs.game import game
from forge.remote_ops.service import run_async


@click.group()
def remote():
    """Remote operations and deployment sidecar."""
    pass


@click.group()
@click.pass_context
def compute(ctx):
    """Compute lifecycle commands."""
    ctx.ensure_object(dict)


@compute.command()
@click.pass_context
def capacity(ctx):
    """Show available GPU capacity on Targon."""
    from forge.compute.targon import TargonBackend

    config = ctx.obj["config"]
    if not config.targon_api_key:
        raise click.ClickException("TARGON_API_KEY not set")

    async def _run():
        backend = TargonBackend(config.targon_api_key)
        caps = await backend.capacity()
        click.echo(f"\n{'Resource':20} {'Available':>10}")
        click.echo("-" * 32)
        for c in caps:
            available = c.get("available", c.get("count", 0))
            if available > 0:
                click.echo(f"{c['name']:20} {available:>10}")

    run_async(_run())


@compute.command(name="list")
@click.pass_context
def list_instances(ctx):
    """List active compute instances."""
    from forge.compute.manager import ComputeManager

    config = ctx.obj["config"]
    cm = ComputeManager(config)

    async def _run():
        instances = await cm.list_all()
        if not instances:
            click.echo("No active instances")
            return
        click.echo(f"\n{'ID':40} {'Backend':8} {'GPU':8} {'Status':12} {'URL/Host'}")
        click.echo("-" * 100)
        for inst in instances:
            loc = inst.url or inst.host or "-"
            click.echo(f"{inst.id:40} {inst.backend:8} {inst.gpu_type:8} {inst.status:12} {loc}")

    run_async(_run())


@compute.command()
@click.option("--gpu", default="H200", help="GPU type")
@click.option("--name", default="affine-train", help="Instance name")
@click.pass_context
def provision(ctx, gpu, name):
    """Provision a new Targon container."""
    from forge.compute.targon import TargonBackend

    config = ctx.obj["config"]
    if not config.targon_api_key:
        raise click.ClickException("TARGON_API_KEY not set")

    async def _run():
        backend = TargonBackend(config.targon_api_key)
        inst = await backend.provision(gpu_type=gpu, name=name)
        click.echo(f"Provisioned {gpu} instance:")
        click.echo(f"  ID: {inst.id}")
        click.echo(f"  URL: {inst.url}")
        click.echo(f"  Status: {inst.status}")

    run_async(_run())


@compute.command()
@click.argument("instance_id")
@click.pass_context
def terminate(ctx, instance_id):
    """Terminate a Targon container."""
    from forge.compute.base import GpuInstance
    from forge.compute.targon import TargonBackend

    config = ctx.obj["config"]
    if not config.targon_api_key:
        raise click.ClickException("TARGON_API_KEY not set")

    async def _run():
        backend = TargonBackend(config.targon_api_key)
        await backend.terminate(GpuInstance(id=instance_id, backend="targon", gpu_type="unknown", status="running"))
        click.echo(f"Terminated: {instance_id}")

    run_async(_run())


@compute.command()
@click.argument("instance_id")
@click.option("--tail", default=0, type=int, help="Show last N lines")
@click.pass_context
def logs(ctx, instance_id, tail):
    """Stream or snapshot container logs."""
    from forge.compute.targon import TargonBackend

    config = ctx.obj["config"]
    if not config.targon_api_key:
        raise click.ClickException("TARGON_API_KEY not set")

    async def _run():
        backend = TargonBackend(config.targon_api_key)
        if tail:
            for line in await backend.logs_snapshot(instance_id, tail=tail):
                click.echo(line)
        else:
            async for line in backend.logs(instance_id, follow=True):
                click.echo(line)

    run_async(_run())


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


from forge.cli_rental import rental as machine

machine.add_command(game)
remote.add_command(machine, name="machine")
remote.add_command(compute)
remote.add_command(deploy)
