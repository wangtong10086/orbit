"""Setup and bootstrap commands for remote machines."""

from __future__ import annotations

import os
import subprocess as sp
from pathlib import Path

import click

from forge.remote_ops.service import get_rental, run_async


def _machine_selector(ctx) -> str | None:
    return ctx.parent.params.get("machine")


def _proxy_requires_host_network(value: str) -> bool:
    return "127.0.0.1" in value or "localhost" in value


@click.command(name="register")
@click.argument("name")
@click.argument("host")
@click.option("--port", default=22, type=int, help="SSH port")
@click.option("--user", default="root", help="SSH user")
@click.option("--key", default="~/.ssh/affine_rental", help="SSH private key path")
@click.option("--gpu-type", default="unknown", help="Optional GPU label for bookkeeping")
@click.pass_context
def register_machine(ctx, name, host, port, user, key, gpu_type):
    """Register an isolated SSH machine in machines.json."""

    from forge.compute.ssh import SshBackend

    config = ctx.obj["config"]
    backend = SshBackend(str(config.machines_file))

    async def _run():
        from forge.compute.base import ProvisionRequest

        inst = await backend.provision(
            ProvisionRequest(
                backend="ssh",
                gpu_type=gpu_type,
                name=name,
                host=host,
                port=port,
                user=user,
                key=key,
            )
        )
        click.echo(f"Registered machine: {inst.id}")
        click.echo(f"  Host: {inst.host}")
        click.echo(f"  User: {inst.user}")
        click.echo(f"  Port: {inst.port}")
        if key:
            click.echo(f"  Key: {key}")

    run_async(_run())


@click.command(name="setup")
@click.pass_context
def setup(ctx):
    """Run the full remote setup script on the machine."""

    from forge.training.templates import load_template

    config = ctx.obj["config"]
    backend, inst = get_rental(config, _machine_selector(ctx))

    async def _run():
        setup_script = load_template("rental_setup.sh")
        click.echo("Running full setup script on remote machine...")
        rc, out, err = await backend.exec(inst, setup_script, timeout=1800)
        if out:
            click.echo(out.strip())
        if rc != 0:
            click.echo(f"Setup had errors (rc={rc})")
            if err:
                click.echo(err[:500])
            return
        click.echo("Next: forge remote machine clone-eval <source_machine>")

    run_async(_run())


@click.command(name="clone-eval")
@click.argument("source_machine")
@click.pass_context
def clone_eval(ctx, source_machine):
    """Copy eval infra and images from another machine."""

    import tempfile

    config = ctx.obj["config"]
    backend, src_inst = get_rental(config, source_machine)
    _, dst_inst = get_rental(config, _machine_selector(ctx))

    async def _run():
        with tempfile.TemporaryDirectory() as tmp:
            for path in ["/root/affinetes/", "/root/scripts/", "/root/.env"]:
                click.echo(f"Syncing {path}...")
                try:
                    await backend.download(src_inst, path, f"{tmp}/")
                    await backend.upload(dst_inst, f"{tmp}/{os.path.basename(path.rstrip('/'))}", path)
                except Exception as exc:
                    click.echo(f"  WARNING: {path} failed: {exc}")

        for image in ["openspiel:eval", "qqr:eval"]:
            click.echo(f"Transferring Docker image {image}...")
            src_addr = f"{src_inst.user}@{src_inst.host}"
            dst_addr = f"{dst_inst.user}@{dst_inst.host}"
            ssh_opts = "-o StrictHostKeyChecking=no -o ConnectTimeout=10"
            result = sp.run(
                f"ssh {ssh_opts} {src_addr} 'docker save {image} | gzip' | "
                f"ssh {ssh_opts} {dst_addr} 'gunzip | docker load'",
                shell=True,
                capture_output=True,
                text=True,
                timeout=600,
            )
            if result.returncode != 0:
                click.echo(f"  WARNING: {image} failed")

        click.echo("Done!")

    run_async(_run())


@click.command(name="bootstrap")
@click.option("--training-only", is_flag=True, help="Skip dev tools")
@click.option("--check", is_flag=True, help="Verify installation only")
@click.pass_context
def bootstrap(ctx, training_only, check):
    """Bootstrap a Targon machine with training stack and optional dev tools."""

    config = ctx.obj["config"]
    backend, inst = get_rental(config, _machine_selector(ctx))
    setup_dir = config.project_root / "forge" / "setup"
    bootstrap_script = setup_dir / "bootstrap.sh"
    requirements_file = config.project_root / "docker" / "requirements-exec.txt"
    if not bootstrap_script.exists():
        raise click.ClickException(f"Bootstrap script not found: {bootstrap_script}")

    async def _run():
        click.echo("Uploading bootstrap files...")
        await backend.exec(inst, "mkdir -p /tmp/affine-setup", timeout=30)
        await backend.upload(inst, str(bootstrap_script), "/tmp/affine-setup/bootstrap.sh")
        if requirements_file.exists():
            await backend.upload(inst, str(requirements_file), "/tmp/affine-setup/requirements.txt")
        await backend.exec(inst, "chmod +x /tmp/affine-setup/bootstrap.sh", timeout=30)

        args = ""
        if training_only:
            args += " --training"
        if check:
            args += " --check"

        click.echo(f"Running bootstrap on {inst.id}...")
        click.echo("=" * 60)
        rc, out, err = await backend.exec(inst, f"bash /tmp/affine-setup/bootstrap.sh{args}", timeout=1800)
        if out:
            click.echo(out.rstrip())
        if err and rc != 0:
            click.echo(err.rstrip(), err=True)
        click.echo("=" * 60)
        if rc != 0:
            raise click.ClickException(f"Bootstrap failed with exit code {rc}")
        click.echo("Bootstrap complete! SSH in and run: source /data/.affine/activate.sh")

    run_async(_run())


@click.command(name="docker-build")
@click.argument("tag", default="wangtong123/affine-forge:latest")
@click.option("--push/--no-push", default=False, help="Push to registry after build")
@click.pass_context
def docker_build(ctx, tag, push):
    """Build the Affine training Docker image."""

    config = ctx.obj["config"]
    project_root = config.project_root
    dockerfile = project_root / "Dockerfile"
    if not dockerfile.exists():
        raise click.ClickException(f"Dockerfile not found: {dockerfile}")

    build_cmd = ["docker", "build", "-t", tag, "-f", str(dockerfile)]
    needs_host_network = False
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy"):
        value = os.environ.get(key)
        if value:
            build_cmd.extend(["--build-arg", f"{key}={value}"])
            if key.lower() in {"http_proxy", "https_proxy"} and _proxy_requires_host_network(value):
                needs_host_network = True
    if needs_host_network:
        build_cmd.extend(["--network", "host"])
    build_cmd.append(str(project_root))

    click.echo(f"Building {tag} from {dockerfile}...")
    result = sp.run(build_cmd, timeout=3600)
    if result.returncode != 0:
        raise click.ClickException("Docker build failed")
    click.echo(f"Built: {tag}")

    if not push:
        return
    click.echo(f"Pushing {tag}...")
    result = sp.run(["docker", "push", tag], timeout=3600)
    if result.returncode != 0:
        raise click.ClickException("Docker push failed")
    click.echo(f"Pushed: {tag}")
