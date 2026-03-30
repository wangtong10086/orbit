"""Direct Targon API / CLI access for development and debugging.

This sidecar is intentionally separate from the execution-plane runtime path.
Use it to provision, inspect, and debug Targon directly when the SDK/runtime
abstractions are too limiting, without redefining production task semantics.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess as sp
import tarfile
import tempfile
import time
import shlex

import click
import httpx

from forge.config import ForgeConfig
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


def _targon_url(path: str, base_url: str = "https://api.targon.com") -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _targon_request(config, method: str, path: str, *, json_body: dict | None = None) -> httpx.Response:
    api_key = _require_targon_api_key(config)
    with httpx.Client(timeout=120.0, headers={"Authorization": f"Bearer {api_key}"}) as client:
        return client.request(method.upper(), _targon_url(path), json=json_body)


def _require_hf_token(config) -> str:
    token = config.hf_token or os.environ.get("HF_TOKEN", "")
    if not token:
        raise click.ClickException("HF_TOKEN not set")
    return token


def _run_targon_cli(config, *args: str) -> sp.CompletedProcess[str]:
    env = os.environ.copy()
    env["TARGON_API_KEY"] = _require_targon_api_key(config)
    return sp.run(
        ["uv", "run", "targon", *args],
        cwd=str(config.project_root),
        env=env,
        capture_output=True,
        text=True,
    )


def _targon_http_request(config, method: str, path: str, *, query: dict[str, str] | None = None, body: dict | None = None):
    api_key = _require_targon_api_key(config)
    url = path if path.startswith("http://") or path.startswith("https://") else f"https://api.targon.com/{path.lstrip('/')}"
    with httpx.Client(timeout=120.0, headers={"Authorization": f"Bearer {api_key}"}) as client:
        response = client.request(method.upper(), url, params=query or None, json=body)
    if response.status_code >= 400:
        raise click.ClickException(f"Targon API {method.upper()} {path} failed: HTTP {response.status_code}: {response.text}")
    content_type = response.headers.get("content-type", "")
    return response.json() if "application/json" in content_type else response.text


def _find_registered_serverless_workload(config, workload_name: str) -> dict | None:
    payload = _targon_http_request(config, "GET", "/tha/v2/workloads", query={"type": "SERVERLESS"})
    items = payload.get("items", []) if isinstance(payload, dict) else []
    for item in items:
        if isinstance(item, dict) and item.get("name") == workload_name:
            return item
    return None


def _game_debug_include_paths(config: ForgeConfig) -> list[tuple[Path, str]]:
    root = config.project_root
    return [
        (root / "forge" / "__init__.py", "forge/__init__.py"),
        (root / "forge" / "data" / "__init__.py", "forge/data/__init__.py"),
        (root / "forge" / "data" / "game_gen.py", "forge/data/game_gen.py"),
        (
            root / "forge" / "data" / "game_trajectory_generators.py",
            "forge/data/game_trajectory_generators.py",
        ),
        (root / "forge" / "data" / "game_generators", "forge/data/game_generators"),
        (root / "forge" / "foundation" / "__init__.py", "forge/foundation/__init__.py"),
        (root / "forge" / "foundation" / "schema.py", "forge/foundation/schema.py"),
        (root / "scripts" / "game", "scripts/game"),
    ]


def _tar_filter(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
    name = info.name
    skipped = ("/.git/", "/__pycache__/", "/.pytest_cache/", "/.ruff_cache/")
    if any(token in f"/{name}/" for token in skipped):
        return None
    if name.endswith((".pyc", ".pyo")):
        return None
    return info


def _create_game_debug_snapshot(config: ForgeConfig, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output_path, "w:gz") as tar:
        for source_path, arcname in _game_debug_include_paths(config):
            if source_path.exists():
                tar.add(source_path, arcname=arcname, filter=_tar_filter)
    return output_path


def _upload_game_debug_snapshot(config: ForgeConfig, local_path: Path, repo_id: str, path_in_repo: str) -> dict:
    try:
        from huggingface_hub import HfApi
        from huggingface_hub.errors import HfHubHTTPError
    except ImportError as exc:
        raise click.ClickException("huggingface_hub not installed") from exc

    token = _require_hf_token(config)
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            api = HfApi(token=token)
            api.upload_file(
                path_or_fileobj=str(local_path),
                path_in_repo=path_in_repo,
                repo_id=repo_id,
                repo_type="dataset",
                commit_message=f"debug: update {path_in_repo}",
            )
            break
        except HfHubHTTPError as exc:
            last_error = exc
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code in {409, 412} and attempt < 3:
                time.sleep(attempt * 2)
                continue
            if status_code is not None and status_code >= 500 and attempt < 3:
                time.sleep(attempt * 2)
                continue
            raise
    if last_error is not None and attempt >= 3:
        raise last_error
    return {"repo_id": repo_id, "path_in_repo": path_in_repo, "local_path": str(local_path)}


def _build_game_smoke_script(
    *,
    game_name: str,
    repo_id: str,
    path_in_repo: str,
    sample_count: int,
    start_seed: int,
    attempt_multiplier: int,
    build_policy: bool,
    policy_iterations: int,
    search_sim: int,
    search_roll: int,
) -> str:
    download_url = f"https://huggingface.co/datasets/{repo_id}/resolve/main/{path_in_repo}"
    build_flag = "1" if build_policy else "0"
    quoted_url = shlex.quote(download_url)
    parts = [
        "set -euo pipefail",
        "python -m http.server 8012 >/tmp/http.log 2>&1 &",
        "cd /tmp",
        f'curl -L -H "Authorization: Bearer $HF_TOKEN" -o game_debug.tar.gz {quoted_url}',
        "rm -rf /tmp/affine-swarm",
        "mkdir -p /tmp/affine-swarm",
        "tar -xzf game_debug.tar.gz -C /tmp/affine-swarm",
        "cd /tmp/affine-swarm",
        "export PYTHONPATH=/tmp/affine-swarm:${PYTHONPATH:-}",
        "uv pip install open_spiel >/tmp/open_spiel.log 2>&1",
        f"export AFFINE_GAME_NAME={shlex.quote(game_name)}",
        f"export AFFINE_GAME_SAMPLE_COUNT={sample_count}",
        f"export AFFINE_GAME_START_SEED={start_seed}",
        f"export AFFINE_GAME_ATTEMPT_MULTIPLIER={attempt_multiplier}",
        f"export AFFINE_GAME_BUILD_POLICY={build_flag}",
        f"export AFFINE_GAME_POLICY_ITERATIONS={policy_iterations}",
        f"export AFFINE_GAME_SEARCH_SIM={search_sim}",
        f"export AFFINE_GAME_SEARCH_ROLL={search_roll}",
        "python scripts/game/targon_game_smoke.py",
    ]
    return " && ".join(parts)


def _parse_game_smoke_logs(text: str) -> dict:
    parsed: dict[str, object] = {"build": None, "policy": None, "generate": None, "preview": []}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("BUILD::"):
            parsed["build"] = json.loads(line.removeprefix("BUILD::"))
        elif line.startswith("POLICY::"):
            parsed["policy"] = json.loads(line.removeprefix("POLICY::"))
        elif line.startswith("GENERATE::"):
            parsed["generate"] = json.loads(line.removeprefix("GENERATE::"))
        elif line.startswith("PREVIEW::"):
            previews = list(parsed.get("preview", []))
            previews.append(line.removeprefix("PREVIEW::"))
            parsed["preview"] = previews
    return parsed


def _is_terminal_status(status: str) -> bool:
    return status.lower() in {
        "succeeded",
        "failed",
        "deleted",
        "terminated",
        "stopped",
        "completed",
    }


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


@targon_debug.command(name="game-smoke")
@click.option("--game", "game_name", required=True, help="GAME environment name to validate")
@click.option("--sample-count", default=2, show_default=True, type=int, help="Target samples")
@click.option("--start-seed", default=100000, show_default=True, type=int, help="Starting seed")
@click.option("--attempt-multiplier", default=4, show_default=True, type=int, help="Retry budget multiplier")
@click.option("--policy-iterations", default=0, show_default=True, type=int, help="Override policy build iterations")
@click.option("--build-policy/--skip-policy-build", default=None, help="Build policy snapshots before generate")
@click.option("--search-sim", default=0, show_default=True, type=int, help="Override search simulations for search-family games")
@click.option("--search-roll", default=0, show_default=True, type=int, help="Override search rollouts for search-family games")
@click.option("--resource", default="h200-small", show_default=True, help="Targon resource name")
@click.option("--image", default="", help="Override container image")
@click.option("--repo", "repo_id", default="", help="HF dataset repo for source tarball")
@click.option("--path-in-repo", default="", help="HF path for source tarball")
@click.option("--wait/--no-wait", default=True, show_default=True, help="Poll workload to completion")
@click.option("--timeout-seconds", default=1800, show_default=True, type=int, help="Wait timeout")
@click.option("--poll-seconds", default=15, show_default=True, type=int, help="Polling interval")
@click.option("--cleanup/--keep", default=True, show_default=True, help="Delete workload after logs are captured")
@click.option("--log-file", default="", help="Optional local log file path")
@click.pass_context
def game_smoke(
    ctx,
    game_name,
    sample_count,
    start_seed,
    attempt_multiplier,
    policy_iterations,
    build_policy,
    search_sim,
    search_roll,
    resource,
    image,
    repo_id,
    path_in_repo,
    wait,
    timeout_seconds,
    poll_seconds,
    cleanup,
    log_file,
):
    """Package current GAME code, upload it, and run a real Targon serverless smoke."""

    from forge.data.game_trajectory_generators import resolve_game_trajectory_generator

    config = ctx.obj["config"]
    api_key = _require_targon_api_key(config)
    repo_id = repo_id or config.hf_dataset_repo or os.environ.get("HF_DATASET_REPO", "")
    if not repo_id:
        raise click.ClickException("HF dataset repo not configured")

    spec = resolve_game_trajectory_generator(game_name)
    should_build_policy = build_policy
    if should_build_policy is None:
        should_build_policy = spec.family in {"cfr", "mccfr", "deep_cfr"}

    image_name = image or config.default_exec_image
    safe_game = "".join(ch.lower() if ch.isalnum() else "-" for ch in game_name).strip("-")
    workload_name = f"affine-game-{safe_game}-{int(time.time())}"[:63]
    if not path_in_repo:
        path_in_repo = f"debug/game_debug/{safe_game}-{int(time.time())}.tar.gz"

    with tempfile.TemporaryDirectory(prefix="affine-game-smoke-") as tmpdir:
        tarball = _create_game_debug_snapshot(config, Path(tmpdir) / "game_debug.tar.gz")
        upload = _upload_game_debug_snapshot(config, tarball, repo_id, path_in_repo)

        script = _build_game_smoke_script(
            game_name=game_name,
            repo_id=repo_id,
            path_in_repo=path_in_repo,
            sample_count=sample_count,
            start_seed=start_seed,
            attempt_multiplier=attempt_multiplier,
            build_policy=bool(should_build_policy),
            policy_iterations=policy_iterations,
            search_sim=search_sim,
            search_roll=search_roll,
        )

        create_payload = {
            "type": "SERVERLESS",
            "name": workload_name,
            "image": image_name,
            "resource_name": resource,
            "envs": [
                {"name": "HF_TOKEN", "value": _require_hf_token(config)},
                {"name": "HF_DATASET_REPO", "value": repo_id},
            ],
            "commands": ["bash", "-lc"],
            "args": [script],
            "ports": [{"port": 8012, "protocol": "TCP", "routing": "PROXIED"}],
            "serverless_config": {
                "visibility": "external",
                "min_replicas": 1,
                "max_replicas": 1,
                "container_concurrency": 1,
                "target_concurrency": 1,
            },
        }

        create_response = _targon_http_request(config, "POST", "/tha/v2/workloads", body=create_payload)
        workload_uid = create_response.get("uid", "") if isinstance(create_response, dict) else ""
        if not workload_uid:
            raise click.ClickException("Targon create workload response missing uid")

        deploy_result: dict[str, object] = {"status": "unknown", "error": ""}
        try:
            deploy_payload = _targon_http_request(
                config,
                "POST",
                f"/tha/v2/workloads/{workload_uid}/deploy",
            )
            deploy_state = deploy_payload.get("state", {}) if isinstance(deploy_payload, dict) else {}
            deploy_urls = deploy_state.get("urls", []) if isinstance(deploy_state, dict) else []
            first_url = ""
            if isinstance(deploy_urls, list):
                for item in deploy_urls:
                    if isinstance(item, dict) and item.get("url"):
                        first_url = item["url"]
                        break
            workload_view = {
                "uid": workload_uid,
                "name": deploy_payload.get("name", workload_name) if isinstance(deploy_payload, dict) else workload_name,
                "url": first_url,
                "status": deploy_state.get("status", "") if isinstance(deploy_state, dict) else "",
                "message": deploy_state.get("message", "") if isinstance(deploy_state, dict) else "",
            }
            deploy_result = {"status": "success", "error": ""}
        except click.ClickException as exc:
            registered = _find_registered_serverless_workload(config, workload_name) or {}
            state = registered.get("state", {}) if isinstance(registered, dict) else {}
            workload_view = {
                "uid": workload_uid,
                "name": registered.get("name", workload_name) if isinstance(registered, dict) else workload_name,
                "url": "",
                "status": state.get("status", "") if isinstance(state, dict) else "",
                "message": state.get("message", "") if isinstance(state, dict) else "",
            }
            deploy_result = {"status": "error", "error": str(exc)}
        payload: dict[str, object] = {
            "upload": upload,
            "workload": workload_view,
            "deploy": deploy_result,
            "game": game_name,
            "generator": spec.model_dump(mode="json"),
            "resource": resource,
            "image": image_name,
            "waited": False,
            "state": {},
            "logs_path": "",
            "parsed": {},
        }

        if not wait:
            click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
            return

        if deploy_result["status"] != "success":
            click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
            return

        deadline = time.time() + timeout_seconds
        last_state = None
        while time.time() < deadline:
            last_state = _targon_http_request(config, "GET", f"/tha/v2/workloads/{workload_uid}/state")
            payload["state"] = {
                "uid": last_state.get("uid", ""),
                "status": last_state.get("status", ""),
                "message": last_state.get("message", ""),
                "ready_replicas": last_state.get("ready_replicas", 0),
                "total_replicas": last_state.get("total_replicas", 0),
                "updated_at": last_state.get("updated_at", ""),
                "urls": last_state.get("urls", []),
            }
            if _is_terminal_status(payload["state"]["status"]):
                break
            time.sleep(max(poll_seconds, 1))

        payload["waited"] = True
        cli_logs = _run_targon_cli(config, "logs", workload_uid)
        logs_text = cli_logs.stdout.rstrip()
        if log_file:
            target = Path(log_file)
        else:
            target = (
                Path(config.project_root)
                / "logs"
                / "real-tests"
                / time.strftime("%Y-%m-%d")
                / "targon-game-smokes"
                / f"{workload_uid}-{safe_game}.log"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(logs_text + ("\n" if logs_text else ""), encoding="utf-8")
        payload["logs_path"] = str(target)
        payload["parsed"] = _parse_game_smoke_logs(logs_text)

        if cleanup:
            try:
                _targon_http_request(config, "DELETE", f"/tha/v2/workloads/{workload_uid}")
                payload["cleanup"] = {"status": "requested"}
            except Exception as exc:  # pragma: no cover - cleanup failure is non-fatal
                payload["cleanup"] = {"status": "error", "reason": str(exc)}

        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
