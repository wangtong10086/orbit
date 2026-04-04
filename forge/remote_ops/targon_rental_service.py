"""Reusable helpers for provisioning Targon rental machines with SSH access."""

from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import urlparse

import click
import httpx

from forge.compute.base import ProvisionRequest
from forge.compute.ssh import SshBackend
from forge.remote_ops.service import run_async


def require_targon_api_key(config) -> str:
    api_key = config.targon_api_key
    if not api_key:
        raise click.ClickException("TARGON_API_KEY not set")
    return api_key


def targon_http_request(config, method: str, path: str, *, query: dict[str, str] | None = None, body: dict | None = None):
    api_key = require_targon_api_key(config)
    url = path if path.startswith(("http://", "https://")) else f"https://api.targon.com/{path.lstrip('/')}"
    with httpx.Client(timeout=120.0, headers={"Authorization": f"Bearer {api_key}"}) as client:
        response = client.request(method.upper(), url, params=query or None, json=body)
    if response.status_code >= 400:
        raise click.ClickException(f"Targon API {method.upper()} {path} failed: HTTP {response.status_code}: {response.text}")
    content_type = response.headers.get("content-type", "")
    return response.json() if "application/json" in content_type else response.text


def require_targon_project_id(config, explicit: str = "") -> str:
    project_id = explicit or config.targon_project_id
    if not project_id:
        raise click.ClickException("TARGON_PROJECT_ID not set")
    return project_id


def list_targon_ssh_keys(config) -> list[dict]:
    payload = targon_http_request(config, "GET", "/tha/v2/ssh-keys")
    return payload.get("items", []) if isinstance(payload, dict) else []


def get_targon_ssh_key(config, uid: str) -> dict:
    for item in list_targon_ssh_keys(config):
        if isinstance(item, dict) and item.get("uid", "") == uid:
            return item
    raise click.ClickException(f"Targon SSH key not found: {uid}")


def resolve_targon_ssh_key_uid(config, explicit_uid: str = "", public_key_path: str = "~/.ssh/id_ed25519.pub") -> str:
    if explicit_uid:
        return explicit_uid
    if config.targon_ssh_key_uid:
        return config.targon_ssh_key_uid
    public_key = Path(public_key_path).expanduser().read_text(encoding="utf-8").strip()
    for item in list_targon_ssh_keys(config):
        if isinstance(item, dict) and item.get("public_key_raw", "").strip() == public_key:
            uid = item.get("uid", "")
            if uid:
                return uid
    raise click.ClickException(
        "No matching Targon SSH key UID found for the local public key. "
        "Pass --ssh-key-uid explicitly or set TARGON_SSH_KEY_UID."
    )


def extract_direct_host_port(state_payload: dict, port: int = 2222) -> tuple[str, int]:
    urls = state_payload.get("urls", []) if isinstance(state_payload, dict) else []
    for item in urls:
        if not isinstance(item, dict):
            continue
        if int(item.get("port", 0) or 0) != int(port):
            continue
        raw = item.get("url", "")
        if not raw:
            continue
        parsed = urlparse(raw)
        if parsed.hostname and parsed.port:
            return parsed.hostname, parsed.port
    raise click.ClickException(f"No direct URL found for SSH port {port}")


def default_rental_init_command(public_key_raw: str, *, ssh_port: int = 2222) -> str:
    packages = [
        "dropbear-bin",
        "openssh-client",
        "openssh-sftp-server",
        "rsync",
        "screen",
        "git",
        "curl",
        "python3",
        "python3-pip",
        "python3-venv",
        "jq",
    ]
    joined_packages = " ".join(packages)
    quoted_key = public_key_raw.replace("'", "'\"'\"'")
    return (
        "apt-get update && "
        f"DEBIAN_FRONTEND=noninteractive apt-get install -y {joined_packages} && "
        "mkdir -p /root/.ssh /etc/dropbear && chmod 700 /root/.ssh && "
        f"printf '%s\\n' '{quoted_key}' > /root/.ssh/authorized_keys && "
        "chmod 600 /root/.ssh/authorized_keys && echo auth_keys_written && "
        f"dropbear -R -F -E -p {int(ssh_port)} -s"
    )


def default_rental_keepalive_command() -> str:
    return "while true; do sleep 3600; done"


def wait_for_ssh_ready(backend: SshBackend, instance, *, timeout_seconds: int = 180, poll_seconds: int = 5) -> None:
    deadline = time.time() + timeout_seconds
    last_error = "ssh not yet reachable"
    while time.time() < deadline:
        try:
            rc, out, err = run_async(backend.exec(instance, "echo affine_ssh_ready", timeout=30))
            if rc == 0 and "affine_ssh_ready" in out:
                return
            last_error = (err or out or f"rc={rc}").strip() or last_error
        except Exception as exc:  # pragma: no cover - exercised by real SSH flows
            last_error = str(exc)
        time.sleep(max(poll_seconds, 1))
    raise click.ClickException(f"Timed out waiting for SSH readiness on {instance.id}: {last_error}")


def provision_targon_rental_ssh(
    config,
    *,
    name: str,
    resource: str,
    image: str = "",
    project_id: str = "",
    ssh_key_uid: str = "",
    public_key: str = "~/.ssh/id_ed25519.pub",
    ssh_port: int = 2222,
    machine_name: str = "",
    use_ssh_daemon: bool = True,
    wait: bool = True,
    timeout_seconds: int = 900,
    poll_seconds: int = 10,
) -> dict:
    project_uid = require_targon_project_id(config, project_id)
    ssh_uid = resolve_targon_ssh_key_uid(config, ssh_key_uid, public_key)
    ssh_key_item = get_targon_ssh_key(config, ssh_uid)
    image_name = image or config.default_exec_image
    create_payload = {
        "name": name,
        "image": image_name,
        "resource_name": resource,
        "type": "RENTAL",
        "project_id": project_uid,
        "ports": [{"port": int(ssh_port), "protocol": "TCP", "routing": "DIRECT"}],
        "ssh_keys": [ssh_uid],
        "commands": ["/bin/bash", "-lc"],
        "args": [
            default_rental_init_command(ssh_key_item.get("public_key_raw", ""), ssh_port=ssh_port)
            if use_ssh_daemon
            else default_rental_keepalive_command()
        ],
    }
    created = targon_http_request(config, "POST", "/tha/v2/workloads", body=create_payload)
    workload_uid = created.get("uid", "") if isinstance(created, dict) else ""
    if not workload_uid:
        raise click.ClickException("Targon create workload response missing uid")
    deployed = targon_http_request(config, "POST", f"/tha/v2/workloads/{workload_uid}/deploy")
    payload = {
        "create": created,
        "deploy": deployed,
        "registered_machine": None,
        "ssh_key_uid": ssh_uid,
    }
    if not wait:
        return payload

    deadline = time.time() + timeout_seconds
    last_state = None
    while time.time() < deadline:
        last_state = targon_http_request(config, "GET", f"/tha/v2/workloads/{workload_uid}/state")
        status = str(last_state.get("status", "")).lower() if isinstance(last_state, dict) else ""
        if status in {"running", "failed", "error", "deleted", "terminated"}:
            break
        time.sleep(max(poll_seconds, 1))

    payload["state"] = last_state
    if isinstance(last_state, dict) and str(last_state.get("status", "")).lower() == "running":
        host, port = extract_direct_host_port(last_state, ssh_port)
        if machine_name:
            backend = SshBackend(str(config.machines_file))
            inst = run_async(
                backend.provision(
                    ProvisionRequest(
                        backend="ssh",
                        gpu_type="unknown",
                        name=machine_name,
                        host=host,
                        port=port,
                        user="root",
                        key=public_key.removesuffix(".pub"),
                    )
                )
            )
            wait_for_ssh_ready(
                backend,
                inst,
                timeout_seconds=max(min(timeout_seconds, 300), 60),
                poll_seconds=min(max(poll_seconds, 1), 10),
            )
            payload["registered_machine"] = {
                "id": inst.id,
                "host": inst.host,
                "port": inst.port,
                "user": inst.user,
            }
            payload["ssh_ready"] = True
    return payload


__all__ = [
    "default_rental_init_command",
    "default_rental_keepalive_command",
    "extract_direct_host_port",
    "get_targon_ssh_key",
    "list_targon_ssh_keys",
    "provision_targon_rental_ssh",
    "require_targon_api_key",
    "require_targon_project_id",
    "resolve_targon_ssh_key_uid",
    "targon_http_request",
    "wait_for_ssh_ready",
]
