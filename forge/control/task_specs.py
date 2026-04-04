"""Task-layer specs that sit above the execution plane."""

from __future__ import annotations

from pydantic import Field

from forge.execution.contracts import EnvKey
from forge.foundation.schema import FrozenModel


class EvalTaskSpec(FrozenModel):
    model: str
    environments: tuple[str, ...]
    samples: int = 100
    base_url: str = "http://172.17.0.1:30000/v1"
    concurrency: int = 5
    seed: int = 42
    affinetes_dir: str = "/root/affinetes"
    api_key: str = ""
    skip_build: bool = True
    output_subdir: str = "eval"


class NavworldCollectConfig(FrozenModel):
    num: int = 10
    model: str = "qwen3-max"
    start_id: int = 0
    concurrency: int = 3
    problem_type: str | None = None
    phase1: bool = False


class LivewebCollectConfig(FrozenModel):
    seeds: str = "1-10"
    subtasks: tuple[int, ...] = (1,)
    plugins: tuple[str, ...] = ("openmeteo",)
    concurrency: int = 1
    cache_dir: str = ""
    min_score: float = 0.0
    timeout: int = 240


class GameCollectConfig(FrozenModel):
    game_name: str = "goofspiel"
    all_games: bool = False
    num: int = 10
    start_seed: int = 100000
    attempt_multiplier: int = 4
    generator_source: str = "default"


class MemorygymCollectConfig(FrozenModel):
    seeds: int = 10
    templates: tuple[str, ...] = ()
    tier: str = "lite"
    tier_mix: bool = False
    jobs: int = 1
    target: int = 5000
    balance: bool = True
    shuffle_seed: int = 42


class SweCollectConfig(FrozenModel):
    machine: str = ""


class CollectPublishConfig(FrozenModel):
    preserve_raw: bool = True
    update_canonical: bool = True
    update_mixed: bool = True
    hf_repo: str = ""
    dataset_config: str = "mixed"
    split: str = "train"
    source: str = ""
    sync_before_ingest: bool = True


class CollectTaskSpec(FrozenModel):
    env: EnvKey = "NAVWORLD"
    collector: str = "navworld-gen"
    output_filename: str
    config: NavworldCollectConfig | LivewebCollectConfig | GameCollectConfig | MemorygymCollectConfig | SweCollectConfig = Field(default_factory=NavworldCollectConfig)
    publish: CollectPublishConfig = Field(default_factory=CollectPublishConfig)
