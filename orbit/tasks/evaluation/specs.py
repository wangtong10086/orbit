"""Evaluation task specs."""

from __future__ import annotations

from orbit.foundation.schema import FrozenModel


class EvalTaskSpec(FrozenModel):
    model: str
    environments: tuple[str, ...]
    samples: int = 100
    task_source_path: str = ""
    max_new_tokens: int = 64
    temperature: float = 0.0
    base_url: str = "http://172.17.0.1:30000/v1"
    concurrency: int = 5
    seed: int = 42
    affinetes_dir: str = "/root/affinetes"
    api_key: str = ""
    skip_build: bool = True
    output_subdir: str = "eval"


__all__ = ["EvalTaskSpec"]
