"""Direct Targon API / CLI access for development and debugging.

This sidecar is intentionally separate from the execution-plane runtime path.
Use it to provision, inspect, and debug Targon directly when the SDK/runtime
abstractions are too limiting, without redefining production task semantics.
"""

from __future__ import annotations

import json
import os
import subprocess as sp

import click
import httpx

from forge.remote_ops.service import run_async


def _require_targon_api_key(config) -> str:
    api_key = config.targon_api_key or os.environ.get("TARGON_API_KEY", "")
    if not api_key:
        raise click.ClickException("TARGON_API_KEY not set")
    return api_key


def _parse_key_values(items: tuple[str, ...]) -> dict[str, str]:
    payload: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise click.ClickException(f"Expected key=value item, got: {item}")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise click.ClickException(f"Empty key in item: {item}")
        payload[key] = value
    return payload


@click.group(name="targon")
def targon_debug():
    """Direct Targon API / CLI access for development and debugging."""


@targon_debug.command(name="inventory")
@click.option("--type", "inventory_type", default="serverless", help="Inventory type filter")
@click.option("--gpu/--all", default=True, help="Filter to GPU inventory entries")
@click.pass_context
def inventory(ctx, inventory_type, gpu):
    """Query raw Targon inventory directly through the SDK."""

    from targon import Client

    config = ctx.obj["config"]
    api_key = _require_targon_api_key(config)
    client = Client(api_key)

    async def _run():
        async with client:
            items = await client.async_inventory.capacity(
                inventory_type=inventory_type or None,
                gpu=True if gpu else None,
            )
            return [
                {
                    "name": item.name,
                    "display_name": item.display_name,
                    "type": item.type,
                    "gpu": item.gpu,
                    "available": item.available,
                    "cost_per_hour": item.cost_per_hour,
                    "spec": {
                        "gpu_type": item.spec.gpu_type,
                        "gpu_count": item.spec.gpu_count,
                        "vcpu": item.spec.vcpu,
                        "memory": item.spec.memory,
                        "storage": item.spec.storage,
                    },
                }
                for item in items
            ]

    result = run_async(_run())
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))


@targon_debug.command(name="apps")
@click.pass_context
def apps(ctx):
    """List Targon apps directly through the SDK."""

    from targon import Client

    config = ctx.obj["config"]
    api_key = _require_targon_api_key(config)
    client = Client(api_key)

    async def _run():
        async with client:
            result = await client.async_app.list_apps()
            return [
                {
                    "uid": app.uid,
                    "name": app.name,
                    "project_id": app.project_id,
                    "created_at": app.created_at,
                    "updated_at": app.updated_at,
                }
                for app in result.apps
            ]

    payload = run_async(_run())
    click.echo(json.dumps(payload, indent=2, ensure_ascii=False))


@targon_debug.command(
    name="api",
    context_settings={"ignore_unknown_options": True},
)
@click.argument("method")
@click.argument("path")
@click.option("--query", "query_items", multiple=True, help="Query params as key=value")
@click.option("--json-body", default="", help="Raw JSON request body")
@click.option("--base-url", default="https://api.targon.com", help="Override API base URL")
@click.pass_context
def raw_api(ctx, method, path, query_items, json_body, base_url):
    """Call the raw Targon HTTP API directly for debugging."""

    config = ctx.obj["config"]
    api_key = _require_targon_api_key(config)
    query = _parse_key_values(query_items)
    body = json.loads(json_body) if json_body else None

    url = path if path.startswith("http://") or path.startswith("https://") else f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    with httpx.Client(timeout=60.0, headers={"Authorization": f"Bearer {api_key}"}) as client:
        response = client.request(method.upper(), url, params=query or None, json=body)

    content_type = response.headers.get("content-type", "")
    if response.status_code >= 400:
        raise click.ClickException(f"HTTP {response.status_code}: {response.text}")

    if "application/json" in content_type:
        click.echo(json.dumps(response.json(), indent=2, ensure_ascii=False))
    else:
        click.echo(response.text)


@targon_debug.command(
    name="cli",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def raw_cli(ctx, args):
    """Pass through directly to the Targon CLI."""

    config = ctx.obj["config"]
    api_key = _require_targon_api_key(config)
    env = os.environ.copy()
    env["TARGON_API_KEY"] = api_key
    cmd = ["uv", "run", "targon", *args]
    result = sp.run(cmd, cwd=str(config.project_root), env=env, capture_output=True, text=True)
    if result.stdout:
        click.echo(result.stdout.rstrip())
    if result.stderr:
        click.echo(result.stderr.rstrip(), err=result.returncode != 0)
    if result.returncode != 0:
        raise click.ClickException(f"Targon CLI exited with status {result.returncode}")
