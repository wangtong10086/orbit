"""Helpers for evaluation pipeline tests."""

from __future__ import annotations

import json
from pathlib import Path

from forge.foundation.evaluation import ScriptEvaluationRunner


def make_script_runner(tmp_path: Path, env_scores: dict[str, list[float]]) -> ScriptEvaluationRunner:
    """Create a ScriptEvaluationRunner whose executor writes fake eval outputs."""

    output_dir = tmp_path / "eval_output"
    output_dir.mkdir(parents=True, exist_ok=True)

    def executor(command: list[str], env: dict[str, str]):
        del env
        out_idx = command.index("--output-dir") + 1
        actual_output_dir = Path(command[out_idx])
        actual_output_dir.mkdir(parents=True, exist_ok=True)

        results_summary = {}
        for env_name, scores in env_scores.items():
            results = [
                {
                    "index": idx,
                    "task_id": idx + 1,
                    "seed": 42 + idx,
                    "score": score,
                    "error": None,
                    "elapsed": 0.1,
                    "raw": {"score": score},
                }
                for idx, score in enumerate(scores)
            ]
            mean_score = sum(scores) / len(scores) if scores else 0.0
            env_payload = {
                "env": env_name,
                "model": "test-model",
                "samples": len(scores),
                "errors": 0,
                "mean_score": mean_score,
                "valid_count": len(scores),
                "valid_mean": mean_score,
                "results": results,
                "timestamp": "2026-03-29T00:00:00Z",
            }
            (actual_output_dir / f"eval_{env_name.lower().replace('-', '_')}.json").write_text(
                json.dumps(env_payload)
            )
            results_summary[env_name] = {
                "mean_score": mean_score,
                "errors": 0,
                "samples": len(scores),
            }

        summary = {
            "model": "test-model",
            "base_url": "http://localhost:30000/v1",
            "timestamp": "2026-03-29T00:00:00Z",
            "results": results_summary,
        }
        (actual_output_dir / "eval_summary.json").write_text(json.dumps(summary))
        return 0, "", ""

    return ScriptEvaluationRunner(command_executor=executor)
