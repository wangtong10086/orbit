"""Subprocess entrypoint that invokes upstream affinetes SWE-INFINITE."""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import sys
from pathlib import Path
from typing import Any


def _normalize(value: Any):
    if dataclasses.is_dataclass(value):
        return {key: _normalize(val) for key, val in dataclasses.asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _normalize(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if hasattr(value, "model_dump"):
        return _normalize(value.model_dump(mode="json"))
    return value


def _load_actor(repo_root: Path):
    env_dir = repo_root / "environments" / "SWE-INFINITE"
    sys.path.insert(0, str(env_dir))
    sys.path.insert(0, str(repo_root))
    from env import Actor  # type: ignore

    return Actor


async def _run(request: dict) -> dict:
    repo_root = Path(str(request["repo_root"])).resolve()
    Actor = _load_actor(repo_root)
    actor = Actor(
        api_key=request.get("api_key") or None,
        cache_dir=request.get("cache_dir") or "/tmp/swe-infinite-cache",
    )
    mode = str(request.get("mode") or "")
    if mode != "evaluate":
        raise RuntimeError(f"Unsupported invoke mode: {mode}")
    result = await actor.evaluate(
        task_id=request["task_id"],
        model=request["model"],
        base_url=request.get("api_base") or "https://llm.chutes.ai/v1",
        api_key=request.get("api_key") or None,
        timeout=int(request.get("timeout") or 1800),
        temperature=0.0,
        seed=None,
        agent=request["agent"],
        max_iterations=100,
        collect_logprobs=bool(request.get("collect_logprobs", False)),
    )
    return _normalize(result)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Invoke upstream affinetes SWE-INFINITE in a subprocess")
    parser.add_argument("--request-file", required=True)
    parser.add_argument("--result-file", required=True)
    args = parser.parse_args(argv)

    request_path = Path(args.request_file)
    result_path = Path(args.result_file)
    request = json.loads(request_path.read_text(encoding="utf-8"))
    payload = asyncio.run(_run(request))
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
