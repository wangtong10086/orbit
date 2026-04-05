"""Concrete evaluation runners for the foundation layer."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from orbit.foundation.contracts import EvaluationSpec


CommandExecutor = Callable[[list[str], dict[str, str]], tuple[int, str, str]]
_PROXY_ENV_NAMES = ("http_proxy", "https_proxy", "all_proxy", "no_proxy")


def _default_command_executor(command: list[str], env: dict[str, str]) -> tuple[int, str, str]:
    proc = subprocess.run(command, capture_output=True, text=True, env=env)
    return proc.returncode, proc.stdout, proc.stderr


def _resolve_affinetes_dir(requested_path: str) -> str:
    candidate = Path(requested_path)
    try:
        if candidate.exists():
            return str(candidate)
    except OSError:
        pass

    repo_sibling = Path(__file__).resolve().parents[2].parent / "affinetes"
    try:
        if repo_sibling.exists():
            return str(repo_sibling)
    except OSError:
        pass
    return requested_path


def _with_proxy_aliases(env: dict[str, str]) -> dict[str, str]:
    """Mirror proxy settings across lower/upper-case env names for child tools."""

    normalized = env.copy()
    for lower_name in _PROXY_ENV_NAMES:
        upper_name = lower_name.upper()
        value = normalized.get(lower_name) or normalized.get(upper_name)
        if value:
            normalized[lower_name] = value
            normalized[upper_name] = value
    return normalized


@dataclass
class ScriptEvaluationRunner:
    """Run evaluation by invoking the repository's real eval script."""

    script_path: str = "scripts/eval_envs.py"
    python_bin: str = sys.executable
    command_executor: CommandExecutor = _default_command_executor

    def run_evaluation(self, spec: EvaluationSpec):
        """Execute the eval script and return parsed per-environment summaries."""

        output_dir = spec.output_dir or tempfile.mkdtemp(prefix="orbit-eval-")
        affinetes_dir = _resolve_affinetes_dir(spec.affinetes_dir)
        cmd = [
            self.python_bin,
            self.script_path,
            "--base-url",
            spec.base_url,
            "--model",
            spec.model_path,
            "--samples",
            str(spec.samples_per_env),
            "--concurrency",
            str(spec.concurrency),
            "--seed",
            str(spec.seed),
            "--output-dir",
            output_dir,
            "--affinetes-dir",
            affinetes_dir,
            "--envs",
            *spec.environments,
        ]
        if spec.skip_build:
            cmd.append("--skip-build")
        if spec.api_key:
            cmd.extend(["--api-key", spec.api_key])

        env = _with_proxy_aliases(os.environ.copy())
        if affinetes_dir:
            existing_pythonpath = env.get("PYTHONPATH", "")
            pythonpath_parts = [affinetes_dir]
            if existing_pythonpath:
                pythonpath_parts.append(existing_pythonpath)
            env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
        if spec.api_key:
            env["CHUTES_API_KEY"] = spec.api_key

        rc, stdout, stderr = self.command_executor(cmd, env)
        if rc != 0:
            raise RuntimeError(
                f"Evaluation script failed with exit code {rc}: {stderr or stdout}"
            )

        summary_path = Path(output_dir) / "eval_summary.json"
        if not summary_path.exists():
            raise FileNotFoundError(f"Evaluation summary not found: {summary_path}")
        summary = json.loads(summary_path.read_text())
        for env_name in spec.environments:
            env_result = summary.get("results", {}).get(env_name)
            if env_result is None:
                raise FileNotFoundError(f"Evaluation summary missing result for {env_name}: {summary_path}")
            if env_result.get("error"):
                raise RuntimeError(f"Evaluation for {env_name} failed: {env_result['error']}")

        return {
            "output_dir": output_dir,
            "summary": summary,
            "stdout": stdout,
            "stderr": stderr,
        }
