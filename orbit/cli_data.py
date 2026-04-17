"""CLI data subcommands for ORBIT."""

import asyncio
import json
import os
from pathlib import Path
import time
import click

from orbit.data.cli_game import GAME_COMMANDS
from orbit.foundation.data_contracts import IngestReport, MemorygymRawRequest, SweSyncRequest
from orbit.foundation.environment_catalog import default_environment_catalog


def _build_collect_spec(*args, **kwargs):
    from orbit.data.collect_service import build_collect_spec

    return build_collect_spec(*args, **kwargs)


def _ingest_collect_output(*args, **kwargs):
    from orbit.data.collect_service import ingest_collect_output

    return ingest_collect_output(*args, **kwargs)


def _local_collect_pipeline(*args, **kwargs):
    from orbit.data.collect_service import local_collect_pipeline

    return local_collect_pipeline(*args, **kwargs)


def _run_memorygym_raw(*args, **kwargs):
    from orbit.data.collect_service import run_memorygym_raw

    return run_memorygym_raw(*args, **kwargs)


def _run_memorygym_split_local(*args, **kwargs):
    from orbit.data.collect_service import run_memorygym_split_local

    return run_memorygym_split_local(*args, **kwargs)


def _swe_sync_pipeline(*args, **kwargs):
    from orbit.data.collect_service import swe_sync_pipeline

    return swe_sync_pipeline(*args, **kwargs)


def _run_swe_sampling(*args, **kwargs):
    from orbit.data.swe_collection import run_swe_sampling

    return run_swe_sampling(*args, **kwargs)


def _run_swe_relabel(*args, **kwargs):
    from orbit.data.swe_collection import run_swe_relabel

    return run_swe_relabel(*args, **kwargs)


def _run_swe_build_buckets(*args, **kwargs):
    from orbit.data.swe_collection import run_swe_build_buckets

    return run_swe_build_buckets(*args, **kwargs)


def _run_swe_train_verifier_dataset(*args, **kwargs):
    from orbit.data.swe_collection import run_swe_train_verifier_dataset

    return run_swe_train_verifier_dataset(*args, **kwargs)


def _run_swe_smoke(*args, **kwargs):
    from orbit.data.swe_collection import run_swe_smoke

    return run_swe_smoke(*args, **kwargs)


def _parse_sampling_temps(*args, **kwargs):
    from orbit.data.swe_collection import parse_sampling_temps

    return parse_sampling_temps(*args, **kwargs)


@click.group()
def data():
    """Data extraction and management."""
    pass


for command in GAME_COMMANDS:
    data.add_command(command)


def _report_ingest_result(result: dict | IngestReport) -> None:
    import json as json_mod

    payload = result.model_dump(mode="json") if isinstance(result, IngestReport) else result

    if payload["status"] == "rejected":
        click.echo(f"  REJECTED: {payload['reason']}")
        for idx, issues in payload.get("issues", [])[:5]:
            click.echo(f"    entry[{idx}]: {issues}")
        raise click.ClickException("Validation failed")
    if payload["status"] == "dry_run":
        click.echo(f"  Would append: {payload.get('would_append', 0)} entries")
        click.echo(f"  Duplicates skipped: {payload['duplicates_skipped']}")
        click.echo(f"  New total would be: {payload['new_total']}")
        return
    if payload["status"] == "success":
        click.echo(f"  Appended: {payload['appended']} entries")
        click.echo(f"  Duplicates skipped: {payload['duplicates_skipped']}")
        click.echo(f"  New total: {payload['new_total']}")
        if payload.get("hf_upload", {}).get("status") == "success":
            click.echo(f"  HF uploaded: {payload['hf_upload']['file']}")
        return
    click.echo(f"  {json_mod.dumps(payload, indent=2)}")


def _run_remote_collect_via_control(*, config, spec, machine: str, output_path: str) -> None:
    import shutil
    import tempfile

    from orbit.core.control.service import CoreControlService
    from orbit.core.contracts.experiments import CreateExperimentRequest, RunQuery
    from orbit.core.contracts.execution import JobKind, RunState
    from orbit.core.contracts.tasks import TaskSubmission
    from orbit.core.contracts.templates import ExecutionOverrides
    from orbit.core.experiments import ExperimentStore
    from orbit.core.execution.service import ExecutionService
    from orbit.core.templates.registry import ExecutionTemplateRegistry
    from orbit.foundation.schema import RequestContext
    from orbit.tasks import build_default_task_registry

    temp_root = Path(tempfile.mkdtemp(prefix="orbit-data-liveweb-"))
    bundle_dir = temp_root / "bundle"
    context = RequestContext(actor="cli", source="cli.data.liveweb-gen")
    plane = CoreControlService(
        experiments=ExperimentStore(str(temp_root / "experiments")),
        execution=ExecutionService(config),
        templates=ExecutionTemplateRegistry(),
        task_registry=build_default_task_registry(),
        bundle_dir_factory=lambda experiment: str(bundle_dir),
    )
    experiment_id = f"liveweb-remote-{int(time.time())}"
    plane.create_experiment(
        CreateExperimentRequest(
            experiment_id=experiment_id,
            variable="liveweb_remote_generation",
            hypothesis="remote LIVEWEB collection via control kernel",
            data_config={"LIVEWEB": {"source": spec.publish.source or spec.collector}},
            notes="Ephemeral control-plane orchestration from data liveweb-gen -m",
            context=context,
        )
    )
    plane.submit_task(
        TaskSubmission(
            experiment_id=experiment_id,
            task_type="collection",
            task_request=spec.model_dump(mode="json"),
            template_id="targon-rental-host",
            bundle_dir=str(bundle_dir),
            overrides=ExecutionOverrides(target=machine, detach=False),
            context=context,
        )
    )
    status = plane.refresh_run_status(RunQuery(experiment_id=experiment_id, run_kind=JobKind.COLLECT, context=context))
    if status.state != RunState.SUCCEEDED:
        raise click.ClickException(f"Remote LIVEWEB generation failed: {status.state.value} ({status.detail})")
    plane.collect_run_artifacts(RunQuery(experiment_id=experiment_id, run_kind=JobKind.COLLECT, context=context))
    remote_output = bundle_dir / "artifacts" / "staging" / Path(output_path).name
    if not remote_output.exists():
        raise click.ClickException(f"Remote LIVEWEB generation completed but output missing: {remote_output}")
    shutil.copy2(remote_output, output_path)


@data.command()
@click.argument("inputs", nargs=-1, required=True)
@click.option("-o", "--output", required=True, help="Output JSONL path")
@click.option("--max-per-env", default=0, type=int, help="Max records per environment (0=unlimited)")
@click.option("--min-score", default=0.0, type=float, help="Additional score filter")
@click.pass_context
def merge(ctx, inputs, output, max_per_env, min_score):
    """Merge multiple JSONL datasets into one training set.

    Example: orbit data merge data/game_sft.jsonl data/lgc-v2_sft.jsonl -o data/mixed_sft.jsonl
    """
    from orbit.data.sft import merge_datasets

    result = merge_datasets(
        input_paths=list(inputs),
        output_path=output,
        max_per_env=max_per_env,
        min_score=min_score,
    )
    click.echo(f"\nMerged {result['total']} records -> {output}")
    click.echo("By environment:")
    for env_name, count in result["by_env"].items():
        click.echo(f"  {env_name}: {count}")


@data.command()
@click.argument("path")
@click.pass_context
def analyze(ctx, path):
    """Analyze a JSONL dataset file (score distribution, length, turns, envs)."""
    import json as json_mod
    from orbit.data.sft import analyze_dataset

    result = analyze_dataset(path)
    if result["count"] == 0:
        click.echo("Empty dataset")
        return

    click.echo(f"\n=== Dataset Analysis: {path} ===")
    click.echo(f"Total records: {result['count']}")

    s = result["score"]
    click.echo(f"\nScore: min={s['min']:.3f} max={s['max']:.3f} mean={s['mean']:.3f} median={s['median']:.3f}")
    click.echo("  Buckets:")
    for k, v in s["buckets"].items():
        click.echo(f"    {k}: {v} ({v*100/result['count']:.1f}%)")

    c = result["char_length"]
    click.echo(f"\nChar length: min={c['min']} max={c['max']} mean={c['mean']:.0f} median={c['median']}")
    click.echo(f"  Over 16K chars: {c['over_16k']} ({c['over_16k']*100/result['count']:.1f}%)")

    t = result["turns"]
    click.echo(f"\nTurns: min={t['min']} max={t['max']} mean={t['mean']:.1f}")

    click.echo(f"\nEnvironments:")
    for env_name, count in result["envs"].items():
        click.echo(f"  {env_name}: {count}")


@data.command(name="validate")
@click.argument("path")
@click.option("--env", default=None, help="Environment (auto-detected from records if omitted)")
@click.pass_context
def data_validate(ctx, path, env):
    """Deep quality audit of a JSONL dataset (scorer-aligned checks)."""
    import json as json_mod

    with open(path) as f:
        records = [json_mod.loads(line) for line in f]

    if not records:
        click.echo("Empty dataset")
        return

    detected_env = env or records[0].get("env", "")

    if detected_env == "NAVWORLD":
        from orbit.data.sft import validate_navworld
        result = validate_navworld(records)
        click.echo(f"\n=== NAVWORLD Validation: {path} ===")
        click.echo(f"Total: {result['total']}  Pass: {result['pass']}  Fail: {result['fail']}  Rate: {result['pass_rate']:.1%}")
        click.echo(f"\nIssues:")
        for issue, count in result["issues"].items():
            click.echo(f"  {issue}: {count} ({count*100/result['total']:.0f}%)")
        click.echo(f"\nTool coverage:")
        for tool, count in sorted(result["tool_coverage"].items(), key=lambda x: -x[1]):
            click.echo(f"  {tool}: {count} ({count*100/result['total']:.0f}%)")
    else:
        # Generic: run through cleaner and report pass/fail
        from orbit.data.sft import ENV_CLEANERS
        cleaner = ENV_CLEANERS.get(detected_env)
        if not cleaner:
            click.echo(f"No validator for env '{detected_env}'. Available: {', '.join(ENV_CLEANERS.keys())}")
            return
        passed = sum(1 for r in records if cleaner(dict(r)) is not None)
        click.echo(f"\n=== {detected_env} Validation: {path} ===")
        click.echo(f"Total: {len(records)}  Pass: {passed}  Fail: {len(records)-passed}  Rate: {passed/len(records):.1%}")


@data.command(name="status")
@click.pass_context
def data_status(ctx):
    """Show data inventory: local files, counts, freshness vs synth_config targets."""
    import json as json_mod
    from pathlib import Path

    config = ctx.obj["config"]
    config_path = config.project_root / "synth_config.json"

    if not config_path.exists():
        raise click.ClickException("synth_config.json not found")

    with open(config_path) as f:
        synth = json_mod.load(f)

    click.echo(f"\n{'Environment':12} {'Enabled':>8} {'Priority':>9} {'Current':>8} {'Target':>8} {'File':>8} {'Status'}")
    click.echo("-" * 80)

    for env_name, env_cfg in sorted(synth["environments"].items(), key=lambda x: x[1].get("priority", 99)):
        enabled = "Yes" if env_cfg.get("enabled") else "No"
        priority = env_cfg.get("priority", "—")
        current = env_cfg.get("current_count", 0)
        target = env_cfg.get("target_count", "—")

        # Check local file (try output, synthetic_output, dynamo_output)
        output = env_cfg.get("output") or env_cfg.get("synthetic_output") or env_cfg.get("dynamo_output") or ""
        local_path = config.project_root / output if output else None
        file_count = 0
        if local_path and local_path.exists():
            with open(local_path) as f:
                file_count = sum(1 for _ in f)
            file_str = str(file_count)
        else:
            file_str = "—"

        # Status
        if not env_cfg.get("enabled"):
            status = "disabled"
        elif isinstance(target, int) and current >= target:
            status = "done"
        else:
            status = f"need {target - current}" if isinstance(target, int) else "?"

        click.echo(f"{env_name:12} {enabled:>8} {priority!s:>9} {current:>8} {target!s:>8} {file_str:>8} {status}")

    click.echo(f"Synth status: {synth.get('status', '?')}")


@data.command(name="upload")
@click.argument("path")
@click.option("--filename", default=None, help="Target filename in HF repo (default: same as local)")
@click.option("--repo", default=None, help="HF dataset repo (default: HF_DATASET_REPO env var)")
@click.pass_context
def data_upload(ctx, path, filename, repo):
    """Upload a local JSONL file to HuggingFace dataset repo."""
    from pathlib import Path as P
    from huggingface_hub import HfApi

    config = ctx.obj["config"]
    repo = repo or os.environ.get("HF_DATASET_REPO", "")
    if not repo:
        raise click.ClickException("--repo is required or set HF_DATASET_REPO env var")

    local = P(path)
    if not local.exists():
        raise click.ClickException(f"File not found: {path}")

    target = filename or local.name

    # Count lines
    with open(local) as f:
        count = sum(1 for _ in f)

    click.echo(f"Uploading {local.name} ({count} records) -> {repo}/{target}")
    api = HfApi(token=config.hf_token)
    api.upload_file(
        path_or_fileobj=str(local),
        path_in_repo=target,
        repo_id=repo,
        repo_type="dataset",
    )
    click.echo(f"Done: https://huggingface.co/datasets/{repo}")


@data.command(name="filter")
@click.argument("path")
@click.option("-o", "--output", required=True, help="Output filtered JSONL path")
@click.option("--env", required=True, help="Environment (GAME, NAVWORLD, SWE-INFINITE)")
@click.option("--seq-len", default=8192, type=int, help="Max sequence length for truncation filter")
@click.pass_context
def data_filter(ctx, path, output, env, seq_len):
    """Quality-filter a dataset: remove low-signal entries, cap templates, seq_len filter.

    Examples:
      orbit data filter data/canonical/game.jsonl -o data/game_filtered.jsonl --env GAME
      orbit data filter data/canonical/swe_synth.jsonl -o data/swe_filtered.jsonl --env SWE-INFINITE --seq-len 16384
    """
    from orbit.data.canonical_ops import (
        filter_by_seq_len, filter_game_quality, filter_navworld_templates, load_staging_file,
    )
    import json as json_mod

    entries = load_staging_file(path)
    original = len(entries)
    click.echo(f"Loaded {original} entries from {path}")

    # seq_len filter (applies to all envs)
    max_chars = int(seq_len * 3.5)  # Qwen3 ~3.5 chars/token
    entries, seq_rejected = filter_by_seq_len(entries, max_chars)
    if seq_rejected:
        click.echo(f"  seq_len={seq_len} filter: removed {seq_rejected} ({seq_rejected*100/original:.1f}%)")

    # Environment-specific filters
    if env == "GAME":
        entries, reasons = filter_game_quality(entries)
        click.echo(f"  GAME quality filter: removed {sum(reasons.values())} — {reasons}")
    elif env == "NAVWORLD":
        entries, nw_rejected = filter_navworld_templates(entries)
        click.echo(f"  NAVWORLD template downsample: removed {nw_rejected}")

    with open(output, "w") as f:
        for e in entries:
            f.write(json_mod.dumps(e, ensure_ascii=False) + "\n")

    click.echo(f"\nResult: {len(entries)}/{original} entries kept ({len(entries)*100/original:.1f}%)")
    click.echo(f"Saved: {output}")


@data.command(name="audit")
@click.pass_context
def data_audit(ctx):
    """Run format audit on all canonical files (schema, roles, content checks)."""
    from orbit.data.canonical_ops import full_audit

    results = full_audit()
    all_pass = True
    total_entries = 0
    for env, r in results.items():
        status = "✅" if r["status"] == "PASS" else "❌"
        if r["status"] != "PASS":
            all_pass = False
        total_entries += r["count"]
        click.echo(f"  {status} {env}: {r['count']} entries, {r['valid']} valid, {r['invalid']} invalid")
    click.echo(f"\nTotal: {total_entries} entries across {len(results)} environments")
    click.echo(f"Result: {'ALL PASS' if all_pass else 'ISSUES FOUND'}")
    if not all_pass:
        raise click.ClickException("Audit failed — fix issues before training")


@data.command(name="ingest")
@click.argument("path")
@click.option("--env", required=True, help="Target environment (GAME, NAVWORLD, SWE-INFINITE, LIVEWEB, MEMORYGYM)")
@click.option("--source", default="staging", help="Source label for tracking")
@click.option("--no-normalize", is_flag=True, help="Skip tool_calls flattening")
@click.option("--no-upload", is_flag=True, help="Skip HF upload after append")
@click.option("--dry-run", is_flag=True, help="Validate and dedup without writing")
@click.pass_context
def data_ingest(ctx, path, env, source, no_normalize, no_upload, dry_run):
    """Ingest a staging JSONL file into canonical (validate + dedup + append + HF upload).

    Example: orbit data ingest data/navworld_phase1_half_day.jsonl --env NAVWORLD --source d8_phase1
    """
    if not os.path.exists(path):
        raise click.ClickException(f"File not found: {path}")

    click.echo(f"Ingesting {path} → canonical/{env}")
    if dry_run:
        click.echo("  (dry run — no changes will be made)")

    result = _ingest_collect_output(
        env=env,
        staging_path=path,
        source=source,
        normalize=not no_normalize,
        upload=not no_upload,
        dry_run=dry_run,
    ).model_dump(mode="json")

    _report_ingest_result(result)


@data.command(name="canonical-upload")
@click.option("--env", default="all", help="Environment to upload (or 'all')")
@click.pass_context
def data_canonical_upload(ctx, env):
    """Upload canonical file(s) to HuggingFace dataset repo.

    Example: orbit data canonical-upload --env NAVWORLD
    """
    from orbit.data.canonical_ops import upload_to_hf, upload_all_to_hf

    valid_envs = default_environment_catalog().list_data_envs()

    if env == "all":
        click.echo("Uploading all canonical files to HF...")
        results = upload_all_to_hf()
        for e, r in results.items():
            status = "✅" if r.status == "success" else "❌"
            click.echo(f"  {status} {e}: {r.status}")
    elif env in valid_envs:
        click.echo(f"Uploading {env} to HF...")
        result = upload_to_hf(env)
        if result.status == "success":
            click.echo(f"  ✅ Uploaded: {result.file}")
        else:
            raise click.ClickException(f"Upload failed: {result.reason or 'unknown'}")
    else:
        raise click.ClickException(f"Unknown env '{env}'. Valid: {', '.join(valid_envs)} or 'all'")


@data.command(name="hf-sync")
@click.option("--repo", default=None, help="HF dataset repo (default: HF_DATASET_REPO env var)")
@click.option("--local-dir", default=".hf-sync", help="Destination directory")
@click.option("--prefix", "prefixes", multiple=True, help="Optional repo prefixes to sync")
def data_hf_sync(repo, local_dir, prefixes):
    """Sync selected paths from the HF dataset repo into a local workspace."""
    from orbit.data.canonical_ops import hf_sync_repo

    result = hf_sync_repo(
        repo_id=repo,
        local_dir=local_dir,
        prefixes=tuple(prefixes) if prefixes else ("raw/", "canonical/", "README.md"),
    )
    click.echo(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False))


@data.command(name="canonical-sync")
@click.option("--env", required=True, help="Environment to sync from HF canonical")
@click.option("--repo", default=None, help="HF dataset repo (default: HF_DATASET_REPO env var)")
def data_canonical_sync(env, repo):
    """Download one canonical file from HF datasets storage."""
    from orbit.data.canonical_ops import download_from_hf

    result = download_from_hf(env, repo_id=repo)
    click.echo(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False))


@data.command(name="publish-mixed")
@click.option("--repo", default=None, help="HF dataset repo (default: HF_DATASET_REPO env var)")
@click.option("--canonical-dir", default="data/canonical", help="Canonical directory to build from")
@click.option("--output-dir", default="data/mixed", help="Local parquet output directory")
@click.option("--config", "config_name", default="mixed", help="Dataset config name")
@click.option("--split", default="train", help="Dataset split name")
@click.option("--envs", default=None, help="Comma-separated environments (default: all canonical envs)")
@click.option("--min-score", default=0.0, type=float)
@click.option("--max-per-env", default=0, type=int)
def data_publish_mixed(repo, canonical_dir, output_dir, config_name, split, envs, min_score, max_per_env):
    """Publish the mixed viewer-friendly dataset to HF."""
    from orbit.data.canonical_ops import publish_mixed

    env_list = envs.split(",") if envs else None
    result = publish_mixed(
        repo_id=repo,
        canonical_dir=canonical_dir,
        output_dir=output_dir,
        config_name=config_name,
        split=split,
        envs=env_list,
        min_score=min_score,
        max_samples_per_env=max_per_env,
    )
    click.echo(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False))


@data.command(name="liveweb-gen")
@click.option("--seeds", required=True, help="Seed range (e.g. '1-2500' or '42')")
@click.option("--subtasks", default="2,3,4", help="Subtask counts (comma-separated)")
@click.option("--plugins", default="coingecko,hackernews,hybrid,stooq,taostats", help="Active plugins (comma-separated)")
@click.option("-o", "--output", default="data/liveweb_teacher.jsonl", help="Output staging path")
@click.option("--concurrency", default=4, type=int, help="Parallel generation tasks")
@click.option("--cache-dir", default=None, help="Override liveweb cache dir")
@click.option("--ingest", is_flag=True, help="Auto-ingest to canonical after generation")
@click.option("--dry-run", is_flag=True, help="Show plan without generating")
@click.option("-m", "--machine", default=None, help="Run on remote machine")
@click.pass_context
def liveweb_gen(ctx, seeds, subtasks, plugins, output, concurrency, cache_dir, ingest, dry_run, machine):
    """Generate LIVEWEB composite SFT data using the teacher-bot pipeline."""
    from pathlib import Path

    from orbit.data.liveweb_teacher_gen import (
        parse_seed_range,
        require_liveweb_repo,
    )

    seed_range = parse_seed_range(seeds)
    subtask_list = [int(item.strip()) for item in subtasks.split(",") if item.strip()]
    plugin_list = [item.strip() for item in plugins.split(",") if item.strip()]
    resolved_cache_dir = cache_dir or os.environ.get(
        "LIVEWEB_CACHE_DIR",
        str((Path(ctx.obj["config"].project_root) / ".cache" / "liveweb-arena").resolve()),
    )
    total_trajectories = len(seed_range) * len(subtask_list)

    click.echo("LIVEWEB Teacher Gen")
    click.echo(f"  Seeds: {seed_range.start}-{seed_range.stop - 1} ({len(seed_range)})")
    click.echo(f"  Subtasks: {subtask_list}")
    click.echo(f"  Plugins: {plugin_list}")
    click.echo(f"  Trajectories: {total_trajectories}")
    click.echo(f"  Est. records: ~{total_trajectories * 5}")
    click.echo(f"  Output: {output}")
    if machine:
        click.echo(f"  Remote machine: {machine}")

    if dry_run:
        click.echo("\n(dry-run — no generation)")
        return

    if machine and ingest:
        raise click.ClickException("--ingest is not supported together with --machine in this pass")

    require_liveweb_repo()

    if machine:
        spec = _build_collect_spec(
            env_name="LIVEWEB",
            output_filename=Path(output).name,
            hf_repo=os.environ.get("HF_DATASET_REPO", ""),
            source="liveweb_teacher",
            num=0,
            model="",
            start_id=0,
            concurrency=concurrency,
            problem_type=None,
            phase1=False,
            seeds=seeds,
            subtasks=subtasks,
            plugins=plugins,
            cache_dir=resolved_cache_dir,
            timeout=240,
            game_name=None,
            all_games=False,
            attempt_multiplier=0,
            templates=(),
            tier="lite",
            tier_mix=False,
            jobs=1,
            split_target=0,
            balance=False,
            shuffle_seed=42,
            machine="",
        )
        _run_remote_collect_via_control(
            config=ctx.obj["config"],
            spec=spec,
            machine=machine,
            output_path=output,
        )
    else:
        spec = _build_collect_spec(
            env_name="LIVEWEB",
            output_filename=Path(output).name,
            hf_repo=os.environ.get("HF_DATASET_REPO", ""),
            source="liveweb_teacher",
            num=0,
            model="",
            start_id=0,
            concurrency=concurrency,
            problem_type=None,
            phase1=False,
            seeds=seeds,
            subtasks=subtasks,
            plugins=plugins,
            cache_dir=resolved_cache_dir,
            timeout=240,
            game_name=None,
            all_games=False,
            attempt_multiplier=0,
            templates=(),
            tier="lite",
            tier_mix=False,
            jobs=1,
            split_target=0,
            balance=False,
            shuffle_seed=42,
            machine="",
        )
        click.echo("\nGenerating...")
        report = _local_collect_pipeline(spec, staging_path=output, ingest=ingest)
        result = report.collect.model_dump(mode="json")
        click.echo(f"\nDone: {result.get('records', 0)} records, {result.get('errors', 0)} errors")
        if ingest:
            _report_ingest_result(report.ingest)


@data.command(name="memorygym-gen")
@click.option("-o", "--output", default="data/memorygym_raw.jsonl", help="Output staging path")
@click.option("--seeds", default=10, type=int, help="Number of seeds per template")
@click.option("--template", "templates", multiple=True, help="Restrict generation to one or more templates")
@click.option("--tier", default="lite", type=click.Choice(["lite", "standard", "hard", "multi"]))
@click.option("--tier-mix", is_flag=True, help="Generate a mixed lite/standard/hard schedule")
@click.option("-j", "--jobs", default=1, type=int, help="Parallel workers")
def memorygym_gen(output, seeds, templates, tier, tier_mix, jobs):
    """Generate raw MEMORYGYM trajectories into a staging JSONL file."""
    request = MemorygymRawRequest(
        output=output,
        seeds=seeds,
        templates=templates,
        tier=tier,
        tier_mix=tier_mix,
        jobs=jobs,
    )
    report = _run_memorygym_raw(request)
    click.echo(json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False))


@data.command(name="memorygym-split")
@click.option("-i", "--input", "input_path", required=True, help="Input raw trajectory JSONL")
@click.option("-o", "--output", default="data/memorygym_split.jsonl", help="Output event-split JSONL")
@click.option("--target", default=0, type=int, help="Target sample count (0 = keep all)")
@click.option("--balance", is_flag=True, help="Balance event type distribution")
@click.option("--shuffle-seed", default=42, type=int, help="Shuffle seed")
@click.option("--ingest", is_flag=True, help="Auto-ingest split samples into canonical MEMORYGYM")
def memorygym_split(input_path, output, target, balance, shuffle_seed, ingest):
    """Split MEMORYGYM raw trajectories into canonical-ready event samples."""
    from pathlib import Path

    canonical_target = Path("data/canonical/memorygym.jsonl")
    if ingest and Path(output) == canonical_target:
        raise click.ClickException("--output must be a staging file when used with --ingest")

    result = _run_memorygym_split_local(
        input_path=input_path,
        output_path=output,
        target=target,
        balance=balance,
        shuffle_seed=shuffle_seed,
    )

    if ingest:
        click.echo("\nAppending to canonical...")
        ingest_result = _ingest_collect_output(
            env="MEMORYGYM",
            staging_path=output,
            source="memorygym_split",
            upload=True,
            dry_run=False,
        )
        _report_ingest_result(ingest_result)




@data.command(name="navworld-gen")
@click.option("-n", "--num", default=10, type=int, help="Number of samples to generate (per type if --phase1)")
@click.option("-o", "--output", default="data/navworld_synthetic.jsonl", help="Output path")
@click.option("--model", default="qwen3-max", help="LLM model for generation")
@click.option("--start-id", default=0, type=int, help="Starting task ID")
@click.option("--concurrency", default=3, type=int, help="Parallel requests")
@click.option("--type", "problem_type", default=None, help="Generate only this problem type")
@click.option("--phase1", is_flag=True, help="Generate all 8 Phase 1 diversity types")
@click.pass_context
def navworld_gen(ctx, num, output, model, start_id, concurrency, problem_type, phase1):
    """Generate synthetic NAVWORLD SFT data using AMap API + LLM.

    Examples:
      orbit data navworld-gen -n 50 --type half_day -o data/half_day.jsonl
      orbit data navworld-gen -n 50 --phase1  # 8 types × 50 = 400 entries
    """
    from orbit.data.navworld_prompts import PHASE1_TYPES

    amap_key = os.environ.get("AMAP_API_KEY") or os.environ.get("AMAP_MAPS_API_KEY", "")
    api_key = os.environ.get("QWEN_API_KEY") or os.environ.get("CHUTES_API_KEY", "")

    if not amap_key:
        raise click.ClickException("AMAP_API_KEY not set")
    if not api_key:
        raise click.ClickException("QWEN_API_KEY not set")

    if phase1:
        click.echo(f"Phase 1 diversity: {len(PHASE1_TYPES)} types × {num} samples")
        total = 0
        for i, ptype in enumerate(PHASE1_TYPES):
            out = output.replace(".jsonl", f"_{ptype}.jsonl")
            click.echo(f"\n=== [{i+1}/{len(PHASE1_TYPES)}] {ptype} → {out} ===")
            spec = _build_collect_spec(
                env_name="NAVWORLD",
                output_filename=os.path.basename(out),
                hf_repo=os.environ.get("HF_DATASET_REPO", ""),
                source="navworld_local",
                num=num,
                model=model,
                start_id=start_id + total,
                concurrency=concurrency,
                problem_type=ptype,
                phase1=False,
                seeds="",
                subtasks="",
                plugins="",
                cache_dir="",
                timeout=0,
                game_name=None,
                all_games=False,
                attempt_multiplier=0,
                templates=(),
                tier="lite",
                tier_mix=False,
                jobs=1,
                split_target=0,
                balance=False,
                shuffle_seed=42,
                machine="",
            )
            _local_collect_pipeline(spec, staging_path=out, ingest=False)
            total += num
        click.echo(f"\nPhase 1 complete: {total} samples across {len(PHASE1_TYPES)} types")
    else:
        click.echo(f"Generating {num} NAVWORLD samples using {model}")
        if problem_type:
            click.echo(f"Problem type: {problem_type}")
        spec = _build_collect_spec(
            env_name="NAVWORLD",
            output_filename=os.path.basename(output),
            hf_repo=os.environ.get("HF_DATASET_REPO", ""),
            source="navworld_local",
            num=num,
            model=model,
            start_id=start_id,
            concurrency=concurrency,
            problem_type=problem_type,
            phase1=False,
            seeds="",
            subtasks="",
            plugins="",
            cache_dir="",
            timeout=0,
            game_name=None,
            all_games=False,
            attempt_multiplier=0,
            templates=(),
            tier="lite",
            tier_mix=False,
            jobs=1,
            split_target=0,
            balance=False,
            shuffle_seed=42,
            machine="",
        )
        _local_collect_pipeline(spec, staging_path=output, ingest=False)


# ===== SWE-Infinite Commands =====

@data.group(name="swe-collect")
def swe_collect():
    """Staged SWE collection: sample, relabel, build buckets, and smoke."""
    pass


@swe_collect.command(name="sample")
@click.option("--task-range", default="", help="Task id range, e.g. 1-10,20")
@click.option("--task-file", default="", help="File containing task ids or task JSONL rows")
@click.option(
    "--format",
    "trajectory_format",
    type=click.Choice(["miniswe", "codex"]),
    default="miniswe",
    show_default=True,
    help="Student trajectory format to sample.",
)
@click.option("--workers", default=1, type=int, help="Reserved worker count for orchestration wrappers")
@click.option("--resume/--no-resume", default=False, help="Skip trajectories already present in raw output")
@click.option("--student-endpoint", default="", help="OpenAI-compatible /v1 endpoint for the student deployment")
@click.option("--student-model", default="", help="Model id for the student deployment")
@click.option("--student-api-key", default="", help="API key for the student deployment")
@click.option("--teacher-endpoint", default="", help="OpenAI-compatible /v1 endpoint for issue-level rubric construction")
@click.option("--teacher-model", default="", help="Model id for issue-level rubric construction")
@click.option("--teacher-api-key", default="", help="API key for issue-level rubric construction")
@click.option("--temps", default="0.3,0.6,0.9", show_default=True, help="Comma-separated sampling temperatures")
@click.option("--max-steps", default=24, type=int, show_default=True, help="Maximum shell interaction steps")
@click.option("--localization-budget", default=16, type=int, show_default=True, help="Number of short localization rollouts")
@click.option("--localization-top-k", default=4, type=int, show_default=True, help="How many localization states to keep")
@click.option("--plan-samples-per-state", default=2, type=int, show_default=True, help="Patch plans per shortlisted localization")
@click.option("--max-realizations", default=4, type=int, show_default=True, help="Maximum full patch realizations to run")
@click.option("--output-dir", required=True, help="Collector output directory")
@click.option("--cache-dir", default="/tmp/orbit-swe-task-cache", show_default=True, help="Local SWE task cache")
def swe_collect_sample(
    task_range,
    task_file,
    trajectory_format,
    workers,
    resume,
    student_endpoint,
    student_model,
    student_api_key,
    teacher_endpoint,
    teacher_model,
    teacher_api_key,
    temps,
    max_steps,
    localization_budget,
    localization_top_k,
    plan_samples_per_state,
    max_realizations,
    output_dir,
    cache_dir,
):
    """Run hidden-oracle-guided cascade sampling for SWE tasks."""
    result = _run_swe_sampling(
        fmt=trajectory_format,
        task_range=task_range,
        task_file=task_file,
        output_dir=output_dir,
        student_endpoint=student_endpoint,
        student_model=student_model,
        student_api_key=student_api_key,
        teacher_endpoint=teacher_endpoint,
        teacher_model=teacher_model,
        teacher_api_key=teacher_api_key,
        cache_dir=cache_dir,
        max_steps=max_steps,
        resume=resume,
        temps=_parse_sampling_temps(temps),
        localization_budget=localization_budget,
        localization_top_k=localization_top_k,
        plan_samples_per_state=plan_samples_per_state,
        max_realizations=max_realizations,
    )
    click.echo("SWE sampling complete")
    click.echo(f"  Profile: {trajectory_format}_student_cascade_v1")
    click.echo(f"  Workers: {workers}")
    click.echo(f"  Trajectories: {result.records}")
    click.echo(f"  Verified success: {result.success}")
    click.echo(f"  Failed/unfinished: {result.failed}")
    if result.reason:
        click.echo(f"  Warning: rubric degraded: {result.reason}")
    click.echo(f"  Raw trajectories: {result.output}")


@swe_collect.command(name="relabel")
@click.option("--input-dir", required=True, help="Existing sample output directory")
@click.option("--cache-dir", default="/tmp/orbit-swe-task-cache", show_default=True, help="Local SWE task cache")
@click.option("--teacher-endpoint", default="", help="OpenAI-compatible /v1 endpoint for teacher critique")
@click.option("--teacher-model", default="", help="Model id for teacher critique")
@click.option("--teacher-api-key", default="", help="API key for teacher critique")
@click.option("--window-radius", default=1, type=int, show_default=True, help="Number of adjacent states to include")
@click.option("--max-repairs", default=2, type=int, show_default=True, help="Maximum near-miss repairs to request")
def swe_collect_relabel(input_dir, cache_dir, teacher_endpoint, teacher_model, teacher_api_key, window_radius, max_repairs):
    """Repair near-miss failures and attach minimal teacher revision actions."""
    result = _run_swe_relabel(
        input_dir=input_dir,
        cache_dir=cache_dir,
        teacher_endpoint=teacher_endpoint,
        teacher_model=teacher_model,
        teacher_api_key=teacher_api_key,
        window_radius=window_radius,
        max_repairs=max_repairs,
    )
    click.echo("SWE relabel complete")
    click.echo(f"  Failure points: {result.records}")
    click.echo(f"  Repair records: {result.success}")
    click.echo(f"  Relabel dir: {result.raw_path}")


@swe_collect.command(name="build-buckets")
@click.option("--input-dir", required=True, help="Existing sample/relabel output directory")
def swe_collect_build_buckets(input_dir):
    """Build A/B/C/V training buckets and append autonomous A rows to canonical."""
    result = _run_swe_build_buckets(input_dir=input_dir)
    click.echo("SWE bucket build complete")
    click.echo(f"  Samples: {result.records}")
    click.echo(f"  A-bucket successes: {result.success}")
    if result.distribution:
        click.echo(f"  Distribution: {json.dumps(result.distribution, sort_keys=True)}")
    click.echo(f"  Bucket dir: {result.output}")


@swe_collect.command(name="train-verifier")
@click.option("--input-dir", required=True, help="Existing sample/relabel/bucket output directory")
@click.option("--output-dir", default="", help="Optional output root for verifier training data")
def swe_collect_train_verifier(input_dir, output_dir):
    """Materialize a lightweight verifier/PRM training dataset from V bucket rows."""
    result = _run_swe_train_verifier_dataset(input_dir=input_dir, output_dir=output_dir)
    click.echo("SWE verifier dataset ready")
    click.echo(f"  Rows: {result.records}")
    click.echo(f"  Dataset: {result.output}")


@swe_collect.command(name="smoke")
@click.option("--output-dir", required=True, help="Root directory for the smoke run")
@click.option("--mini-task-range", default="1-1", show_default=True, help="MiniSWE task range")
@click.option("--codex-task-range", default="2-2", show_default=True, help="Codex task range")
@click.option("--cache-dir", default="/tmp/orbit-swe-task-cache", show_default=True, help="Local SWE task cache")
@click.option("--max-steps", default=12, type=int, show_default=True, help="Maximum shell interaction steps")
@click.option("--temps", default="0.3", show_default=True, help="Comma-separated sampling temperatures")
@click.option("--mini-student-endpoint", default="", help="MiniSWE student endpoint")
@click.option("--mini-student-model", default="", help="MiniSWE student model")
@click.option("--mini-student-api-key", default="", help="MiniSWE student API key")
@click.option("--codex-student-endpoint", default="", help="Codex student endpoint")
@click.option("--codex-student-model", default="", help="Codex student model")
@click.option("--codex-student-api-key", default="", help="Codex student API key")
@click.option("--teacher-endpoint", default="", help="Teacher critique endpoint")
@click.option("--teacher-model", default="", help="Teacher critique model")
@click.option("--teacher-api-key", default="", help="Teacher critique API key")
def swe_collect_smoke(
    output_dir,
    mini_task_range,
    codex_task_range,
    cache_dir,
    max_steps,
    temps,
    mini_student_endpoint,
    mini_student_model,
    mini_student_api_key,
    codex_student_endpoint,
    codex_student_model,
    codex_student_api_key,
    teacher_endpoint,
    teacher_model,
    teacher_api_key,
):
    """Run a small end-to-end sample -> relabel -> build-buckets smoke."""
    result = _run_swe_smoke(
        output_dir=output_dir,
        mini_task_range=mini_task_range,
        codex_task_range=codex_task_range,
        cache_dir=cache_dir,
        max_steps=max_steps,
        temps=_parse_sampling_temps(temps),
        mini_student_endpoint=mini_student_endpoint,
        mini_student_model=mini_student_model,
        mini_student_api_key=mini_student_api_key,
        codex_student_endpoint=codex_student_endpoint,
        codex_student_model=codex_student_model,
        codex_student_api_key=codex_student_api_key,
        teacher_endpoint=teacher_endpoint,
        teacher_model=teacher_model,
        teacher_api_key=teacher_api_key,
    )
    click.echo("SWE smoke complete")
    click.echo(f"  Output root: {result.output}")
    click.echo(f"  Total records: {result.records}")
    click.echo(f"  Success-count summary: {result.success}")
    click.echo(f"  Failure-count summary: {result.failed}")

@data.command(name="swe-status")
@click.option("--log", "show_log", is_flag=True, help="Show recent distillation log")
@click.option("--log-lines", default=30, type=int, help="Number of log lines")
@click.option("--batch", default="latest", help="Attempt id stem or `latest`")
@click.option("-m", "--machine", default=None, help="Use a registered machine from machines.json for SWE sync")
def swe_status(show_log, log_lines, batch, machine):
    """Show SWE-Infinite collection pipeline status.

    Checks remote machine for running collector processes, exported files,
    run manifests, Docker containers, and local canonical counts.
    """
    from orbit.data.swe_ops import distill_status, distill_log, count_local_canonical

    click.echo("SWE-Infinite Pipeline Status")
    click.echo("=" * 50)

    # Local canonical
    local = count_local_canonical()
    click.echo(f"\nCanonical: {local['total']} entries")
    for lang, count in sorted(local["by_language"].items(), key=lambda x: -x[1]):
        click.echo(f"  {lang}: {count}")

    # Remote status
    click.echo(f"\nRemote collector:")
    try:
        status = distill_status(machine=machine) if machine is not None else distill_status()
        if status.get("infra_error"):
            click.echo(f"  [BLOCKED] {status['infra_error']}")
        elif status["running"]:
            click.echo(f"  Collection: RUNNING ({len(status['processes'])} processes)")
            for p in status["processes"]:
                click.echo(f"    PID {p['pid']}: {p['cmd'][:80]}")
        else:
            click.echo("  Collection: STOPPED")
            click.echo(f"  Docker containers: {status['containers'] if status['containers'] is not None else '?'}")

            if status["output_files"]:
                click.echo("  Exported files:")
                for of in status["output_files"]:
                    click.echo(f"    {of['name']}: {of['count']} entries")
            if status.get("runs"):
                click.echo("  Run manifests:")
                for run_path in status["runs"][-5:]:
                    click.echo(f"    {run_path}")
            if status.get("probe_warning"):
                click.echo(f"  [WARN] {status['probe_warning']}")
    except Exception as e:
        click.echo(f"  [ERROR] Cannot reach collector host: {e}")

    if show_log:
        click.echo(f"\nLog ({batch}):")
        click.echo("-" * 50)
        if machine is not None:
            click.echo(distill_log(lines=log_lines, batch=batch, machine=machine))
        else:
            click.echo(distill_log(lines=log_lines, batch=batch))


@data.command(name="swe-sync")
@click.option("--dry-run", is_flag=True, help="Show what would be synced without writing")
@click.option("--upload/--no-upload", default=True, help="Upload to HF after sync")
@click.option("-m", "--machine", default=None, help="Use a registered machine from machines.json for SWE sync")
@click.option("--remote-dir", default="", help="Remote collector output root")
def swe_sync(dry_run, upload, machine, remote_dir):
    """Sync new SWE-Infinite trajectories from remote to canonical.

    Downloads collector-exported canonical files from the remote host,
    deduplicates against canonical, validates format, and appends new entries.
    """
    click.echo("Syncing SWE-Infinite trajectories...")
    report = _swe_sync_pipeline(
        SweSyncRequest(
            machine=machine or "",
            dry_run=dry_run,
            upload=upload,
            repo_id=os.environ.get("HF_DATASET_REPO", ""),
            remote_dir=remote_dir,
        )
    )
    result = report.collect.model_dump(mode="json")
    if result.get("blocked_reason"):
        raise click.ClickException(f"SWE sync blocked: {result['blocked_reason']}")

    click.echo(f"\nResults:")
    click.echo(f"  New entries:     {result['new_count']}")
    click.echo(f"  Skipped (dup):   {result['skipped_dup']}")
    click.echo(f"  Skipped (invalid): {result['skipped_invalid']}")
    click.echo(f"  Total canonical: {result['total']}")

    if dry_run:
        click.echo("\n(dry-run — no changes written)")
    elif result["new_count"] > 0 and upload:
        click.echo("\nHF sync complete.")


@data.command(name="aggregate")
@click.option("-o", "--output", default="data/train_merged.jsonl", help="Output file")
@click.option("--envs", default=None, help="Comma-separated envs (default: all enabled)")
@click.option("--min-score", default=0.0, type=float, help="Min score filter")
@click.option("--max-per-env", default=0, type=int, help="Max samples per env")
@click.option("--upload/--no-upload", default=True, help="Upload merged file to HF")
@click.option("--remote-name", default="train_merged.jsonl", help="Filename on HF")
@click.pass_context
def aggregate(ctx, output, envs, min_score, max_per_env, upload, remote_name):
    """Build a training dataset from local canonical data via the data pipeline.

    Example: orbit data aggregate --envs GAME,NAVWORLD -o data/train.jsonl
    """
    from orbit.data.aggregate import build_from_canonical, upload_merged

    config = ctx.obj["config"]
    token = config.hf_token
    env_list = envs.split(",") if envs else None

    click.echo("Building dataset from local canonical repository...")
    stats = build_from_canonical(
        output_path=output,
        envs=env_list,
        min_score=min_score,
        max_samples_per_env=max_per_env,
    )

    if upload and stats.get("total", 0) > 0:
        if not token:
            raise click.ClickException("HF_TOKEN not set. Add it to .env or environment.")
        click.echo("\nUploading merged file to HF...")
        upload_merged(output, token=token, remote_filename=remote_name)

    click.echo(f"\nDone! {stats.get('total', 0)} samples ready for training.")
