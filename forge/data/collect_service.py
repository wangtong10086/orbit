"""Shared collect service and spec builder for worker/control/data entrypoints."""

from __future__ import annotations

from pathlib import Path

from forge.data.collect_adapters import collect_memorygym_split, run_collect_from_config
from forge.execution.contracts import (
    CollectPublishConfig,
    CollectTaskSpec,
    GameCollectConfig,
    LivewebCollectConfig,
    MemorygymCollectConfig,
    NavworldCollectConfig,
    SweCollectConfig,
)
from forge.foundation.data_contracts import (
    CollectPipelineReport,
    CollectResult,
    CollectSyncResult,
    CollectedRawArtifact,
    IngestReport,
    MemorygymRawRequest,
    PublishReport,
    SweSyncRequest,
)


def build_collect_spec(
    *,
    env_name: str,
    output_filename: str,
    hf_repo: str,
    source: str,
    num: int,
    model: str,
    start_id: int,
    concurrency: int,
    problem_type: str | None,
    phase1: bool,
    seeds: str,
    subtasks: str,
    plugins: str,
    cache_dir: str,
    timeout: int,
    game_name: str | None,
    all_games: bool,
    attempt_multiplier: int,
    templates: tuple[str, ...],
    tier: str,
    tier_mix: bool,
    jobs: int,
    split_target: int,
    balance: bool,
    shuffle_seed: int,
    machine: str,
) -> CollectTaskSpec:
    env_name = env_name.upper()
    publish = CollectPublishConfig(hf_repo=hf_repo, source=source or "")
    if env_name == "NAVWORLD":
        config = NavworldCollectConfig(
            num=num,
            model=model,
            start_id=start_id,
            concurrency=concurrency,
            problem_type=problem_type,
            phase1=phase1,
        )
        collector = "navworld-gen"
    elif env_name == "LIVEWEB":
        config = LivewebCollectConfig(
            seeds=seeds,
            subtasks=tuple(int(item.strip()) for item in subtasks.split(",") if item.strip()),
            plugins=tuple(item.strip() for item in plugins.split(",") if item.strip()),
            concurrency=concurrency,
            cache_dir=cache_dir,
            timeout=timeout,
        )
        collector = "liveweb-gen"
    elif env_name == "GAME":
        config = GameCollectConfig(
            game_name=game_name or "goofspiel",
            all_games=all_games,
            num=num,
            start_seed=start_id,
            attempt_multiplier=attempt_multiplier,
        )
        collector = "game-gen"
    elif env_name == "MEMORYGYM":
        config = MemorygymCollectConfig(
            seeds=num,
            templates=templates,
            tier=tier,
            tier_mix=tier_mix,
            jobs=jobs,
            target=split_target,
            balance=balance,
            shuffle_seed=shuffle_seed,
        )
        collector = "memorygym-gen"
    elif env_name == "SWE-INFINITE":
        config = SweCollectConfig(machine=machine)
        collector = "swe-sync"
    else:
        raise ValueError(f"Unsupported collect env: {env_name}")

    return CollectTaskSpec(
        env=env_name,
        collector=collector,
        output_filename=output_filename,
        config=config,
        publish=publish,
    )


def run_local_collect(spec: CollectTaskSpec, *, staging_path: str, canonical_dir: str = "data/canonical") -> CollectResult:
    raw_dir = str(Path(staging_path).parent / "raw" / spec.env.lower().replace("-", "_"))
    Path(raw_dir).mkdir(parents=True, exist_ok=True)
    return run_collect_from_config(
        spec.config,
        staging_path=staging_path,
        raw_dir=raw_dir,
        canonical_dir=canonical_dir,
    )


def run_memorygym_split_local(
    *,
    input_path: str,
    output_path: str,
    target: int,
    balance: bool,
    shuffle_seed: int,
) -> CollectResult:
    return collect_memorygym_split(
        input_path=input_path,
        output_path=output_path,
        target=target,
        balance=balance,
        shuffle_seed=shuffle_seed,
    )


def run_memorygym_raw(request: MemorygymRawRequest) -> CollectResult:
    from forge.data.memorygym_gen import generate_dataset, require_memorygym_repo

    require_memorygym_repo()
    result = generate_dataset(
        output=request.output,
        templates=list(request.templates) or None,
        seeds=request.seeds,
        tier=request.tier,
        tier_mix=request.tier_mix,
        workers=request.jobs,
    )
    return CollectResult(
        output=result.get("output", request.output),
        raw_path=result.get("output", request.output),
        trajectories=result.get("trajectories", 0),
        records=result.get("trajectories", 0),
        success=result.get("trajectories", 0),
    )


def ingest_collect_output(
    *,
    env: str,
    staging_path: str,
    source: str,
    normalize: bool = True,
    upload: bool,
    dry_run: bool,
    canonical_dir: str = "data/canonical",
    repo_id: str | None = None,
) -> IngestReport:
    from forge.data.canonical_ops import ingest_staging

    return ingest_staging(
        staging_path=staging_path,
        env=env,
        source=source,
        normalize=normalize,
        upload=upload,
        dry_run=dry_run,
        canonical_dir=canonical_dir,
        repo_id=repo_id,
    )


def local_collect_pipeline(
    spec: CollectTaskSpec,
    *,
    staging_path: str,
    ingest: bool = False,
    canonical_dir: str = "data/canonical",
    repo_id: str | None = None,
) -> CollectPipelineReport:
    collect_result = run_local_collect(spec, staging_path=staging_path, canonical_dir=canonical_dir)
    ingest_result = IngestReport()
    if ingest:
        ingest_result = ingest_collect_output(
            env=spec.env,
            staging_path=staging_path,
            source=spec.publish.source or spec.collector,
            upload=True,
            dry_run=False,
            canonical_dir=canonical_dir,
            repo_id=repo_id or spec.publish.hf_repo or None,
        )
    return CollectPipelineReport(
        repo_id=repo_id or spec.publish.hf_repo,
        env=spec.env,
        source=spec.publish.source or spec.collector,
        collect=collect_result,
        ingest=ingest_result,
    )


def swe_sync_pipeline(request: SweSyncRequest) -> CollectPipelineReport:
    from forge.data.canonical_ops import upload_to_hf
    from forge.data.swe_ops import sync_new_trajectories

    kwargs = {"dry_run": request.dry_run}
    if request.machine:
        kwargs["machine"] = request.machine
    raw_result = sync_new_trajectories(**kwargs)
    result = CollectResult.model_validate({**raw_result, "blocked_reason": raw_result.get("blocked_reason") or ""})
    if result.blocked_reason:
        return CollectPipelineReport(
            status="blocked",
            repo_id=request.repo_id,
            env="SWE-INFINITE",
            source="swe-sync",
            sync=[
                CollectSyncResult(
                    status="blocked",
                    env="SWE-INFINITE",
                    path="",
                    repo_id=request.repo_id,
                    reason=result.blocked_reason,
                )
            ],
            collect=result,
            ingest=IngestReport(status="blocked", reason=result.blocked_reason),
            mixed=PublishReport(status="skipped"),
        )

    ingest = IngestReport(
        status="success",
        appended=result.new_count,
        duplicates_skipped=result.skipped_dup,
        new_total=result.total,
    )
    if not request.dry_run and request.upload and result.new_count > 0:
        ingest = ingest.model_copy(
            update={
                "hf_upload": upload_to_hf("SWE-INFINITE", repo_id=request.repo_id or None)
            }
        )
    return CollectPipelineReport(
        status="success",
        repo_id=request.repo_id,
        env="SWE-INFINITE",
        source="swe-sync",
        sync=[CollectSyncResult(status="success", env="SWE-INFINITE", path="", repo_id=request.repo_id)],
        collect=result,
        ingest=ingest,
        mixed=PublishReport(status="skipped"),
    )
