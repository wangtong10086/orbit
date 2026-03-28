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

from forge.foundation.contracts import EvaluationSpec


CommandExecutor = Callable[[list[str], dict[str, str]], tuple[int, str, str]]


def _default_command_executor(command: list[str], env: dict[str, str]) -> tuple[int, str, str]:
    proc = subprocess.run(command, capture_output=True, text=True, env=env)
    return proc.returncode, proc.stdout, proc.stderr


@dataclass
class ScriptEvaluationRunner:
    """Run evaluation by invoking the repository's real eval script."""

    script_path: str = "scripts/eval_envs.py"
    python_bin: str = sys.executable
    command_executor: CommandExecutor = _default_command_executor

    def run_evaluation(self, spec: EvaluationSpec):
        """Execute the eval script and return parsed per-environment summaries."""

        output_dir = spec.output_dir or tempfile.mkdtemp(prefix="forge-eval-")
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
            spec.affinetes_dir,
            "--envs",
            *spec.environments,
        ]
        if spec.skip_build:
            cmd.append("--skip-build")
        if spec.api_key:
            cmd.extend(["--api-key", spec.api_key])

        env = os.environ.copy()
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

        return {
            "output_dir": output_dir,
            "summary": json.loads(summary_path.read_text()),
            "stdout": stdout,
            "stderr": stderr,
        }
