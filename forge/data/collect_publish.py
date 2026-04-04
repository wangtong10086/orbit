"""Execution-plane collect + publish orchestrator."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from forge.data.collect_adapters import collect_from_config
from forge.data.aggregate import dataset_repo_id
from forge.data.canonical_ops import (
    CATALOG,
    download_from_hf,
    ingest_staging,
    publish_mixed,
    upload_raw_file,
)
from forge.control.task_specs import CollectTaskSpec
from forge.foundation.data_contracts import (
    CollectPipelineReport,
    CollectResult,
    CollectSyncResult,
    CollectedRawArtifact,
    IngestReport,
    PublishReport,
)

MIXED_ENVS = ["GAME", "NAVWORLD", "LIVEWEB", "MEMORYGYM"]


def _env_slug(env: str) -> str:
    return env.lower().replace("-", "_")


def _read_spec(path: str) -> CollectTaskSpec:
    with open(path, encoding="utf-8") as handle:
        return CollectTaskSpec.model_validate(json.load(handle))


def _job_id_from_bundle(bundle_root: Path) -> str:
    with (bundle_root / "job.json").open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload.get("job_id", f"collect-{int(time.time())}")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _sync_canonical_workspace(spec: CollectTaskSpec, canonical_dir: Path) -> list[dict]:
    synced = []
    envs = MIXED_ENVS if spec.publish.update_mixed else [spec.env]
    for env in envs:
        synced.append(
            download_from_hf(
                env,
                repo_id=spec.publish.hf_repo or None,
                token=None,
                canonical_dir=str(canonical_dir),
            )
        )
    return synced


def _as_collect_sync_result(item) -> CollectSyncResult:
    if isinstance(item, CollectSyncResult):
        return item
    if hasattr(item, "model_dump"):
        return CollectSyncResult(**item.model_dump(mode="json"))
    return CollectSyncResult.model_validate(item)


async def run_collect_pipeline(spec: CollectTaskSpec, bundle_root: str) -> dict:
    bundle = Path(bundle_root)
    job_id = _job_id_from_bundle(bundle)
    artifacts = bundle / "artifacts"
    raw_dir = artifacts / "raw" / _env_slug(spec.env)
    staging_dir = artifacts / "staging"
    canonical_dir = artifacts / "canonical"
    mixed_dir = artifacts / "mixed"
    publish_result_path = artifacts / "publish_result.json"
    staging_path = staging_dir / spec.output_filename
    repo_id = dataset_repo_id(spec.publish.hf_repo or None)
    source = spec.publish.source or job_id

    raw_dir.mkdir(parents=True, exist_ok=True)
    staging_dir.mkdir(parents=True, exist_ok=True)
    canonical_dir.mkdir(parents=True, exist_ok=True)
    mixed_dir.mkdir(parents=True, exist_ok=True)

    sync_results = _sync_canonical_workspace(spec, canonical_dir)

    collect_result = CollectResult()
    preserved_raw: list[str] = []
    collect_result = await collect_from_config(
        spec.config,
        staging_path=str(staging_path),
        raw_dir=str(raw_dir),
        canonical_dir=str(canonical_dir),
    )
    if collect_result.raw_path:
        preserved_raw.append(collect_result.raw_path)
    elif spec.env != "SWE-INFINITE":
        preserved_raw.append(str(staging_path))
    if collect_result.raw_files:
        preserved_raw.extend(collect_result.raw_files)

    raw_uploads = []
    if spec.publish.preserve_raw:
        for raw_file in preserved_raw:
            raw_uploads.append(CollectedRawArtifact.model_validate(
                upload_raw_file(
                    raw_file,
                    spec.env,
                    repo_id=repo_id,
                    remote_name=f"{source}-{Path(raw_file).name}",
                )
            ))

    ingest_result = IngestReport()
    if spec.publish.update_canonical and spec.env != "SWE-INFINITE":
        ingest_result = ingest_staging(
            str(staging_path),
            env=spec.env,
            source=source,
            normalize=True,
            upload=True,
            dry_run=False,
            canonical_dir=str(canonical_dir),
            repo_id=repo_id,
        )
    elif spec.publish.update_canonical:
        ingest_result = IngestReport(
            status="success",
            appended=collect_result.new_count,
            duplicates_skipped=collect_result.skipped_dup,
            new_total=collect_result.total,
            hf_upload=CollectedRawArtifact(status="success", file=f"canonical/{spec.env.lower().replace('-', '_')}.jsonl"),
        )
        if collect_result.new_count > 0:
            from forge.data.canonical_ops import upload_to_hf

            ingest_result = ingest_result.model_copy(update={"hf_upload": upload_to_hf(
                spec.env,
                repo_id=repo_id,
                canonical_dir=str(canonical_dir),
            )})

    mixed_result = PublishReport()
    if spec.publish.update_mixed:
        mixed_result = publish_mixed(
            repo_id=repo_id,
            canonical_dir=str(canonical_dir),
            output_dir=str(mixed_dir),
            config_name=spec.publish.dataset_config,
            split=spec.publish.split,
            envs=MIXED_ENVS,
        )

    publish_result = CollectPipelineReport(
        status="success",
        repo_id=repo_id,
        env=spec.env,
        source=source,
        sync=[_as_collect_sync_result(item) for item in sync_results],
        collect=collect_result,
        raw_uploads=raw_uploads,
        ingest=ingest_result,
        mixed=mixed_result,
    )
    _write_json(publish_result_path, publish_result.model_dump(mode="json"))
    return publish_result.model_dump(mode="json")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run collect+publish for an execution bundle")
    parser.add_argument("--spec", required=True, help="Path to collect spec JSON")
    parser.add_argument("--bundle-root", required=True, help="Bundle root path")
    args = parser.parse_args(argv)

    spec = _read_spec(args.spec)
    import asyncio

    result = asyncio.run(run_collect_pipeline(spec, args.bundle_root))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
