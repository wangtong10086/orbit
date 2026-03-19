"""CLI data subcommands for Affine Forge."""

import os
import click


@click.group()
def data():
    """Data extraction and management."""
    pass


@data.command()
@click.argument("inputs", nargs=-1, required=True)
@click.option("-o", "--output", required=True, help="Output JSONL path")
@click.option("--max-per-env", default=0, type=int, help="Max records per environment (0=unlimited)")
@click.option("--min-score", default=0.0, type=float, help="Additional score filter")
@click.pass_context
def merge(ctx, inputs, output, max_per_env, min_score):
    """Merge multiple JSONL datasets into one training set.

    Example: forge data merge data/game_sft.jsonl data/lgc-v2_sft.jsonl -o data/mixed_sft.jsonl
    """
    from forge.data.sft import merge_datasets

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
    from forge.data.sft import analyze_dataset

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
        from forge.data.sft import validate_navworld
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
        from forge.data.sft import ENV_CLEANERS
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
    config_path = config.project_root / "forge" / "data" / "synth_config.json"

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
@click.option("--env", required=True, help="Environment (GAME, NAVWORLD, SWE-SYNTH)")
@click.option("--seq-len", default=8192, type=int, help="Max sequence length for truncation filter")
@click.pass_context
def data_filter(ctx, path, output, env, seq_len):
    """Quality-filter a dataset: remove low-signal entries, cap templates, seq_len filter.

    Examples:
      forge data filter data/canonical/game.jsonl -o data/game_filtered.jsonl --env GAME
      forge data filter data/canonical/swe_synth.jsonl -o data/swe_filtered.jsonl --env SWE-SYNTH --seq-len 16384
    """
    from forge.data.canonical_ops import (
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
    from forge.data.canonical_ops import full_audit

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
@click.option("--env", required=True, help="Target environment (GAME, NAVWORLD, SWE-SYNTH, LIVEWEB)")
@click.option("--source", default="staging", help="Source label for tracking")
@click.option("--no-normalize", is_flag=True, help="Skip tool_calls flattening")
@click.option("--no-upload", is_flag=True, help="Skip HF upload after append")
@click.option("--dry-run", is_flag=True, help="Validate and dedup without writing")
@click.pass_context
def data_ingest(ctx, path, env, source, no_normalize, no_upload, dry_run):
    """Ingest a staging JSONL file into canonical (validate + dedup + append + HF upload).

    Example: forge data ingest data/navworld_phase1_half_day.jsonl --env NAVWORLD --source d8_phase1
    """
    import json as json_mod
    from forge.data.canonical_ops import ingest_staging

    if not os.path.exists(path):
        raise click.ClickException(f"File not found: {path}")

    click.echo(f"Ingesting {path} → canonical/{env}")
    if dry_run:
        click.echo("  (dry run — no changes will be made)")

    result = ingest_staging(
        staging_path=path,
        env=env,
        source=source,
        normalize=not no_normalize,
        upload=not no_upload,
        dry_run=dry_run,
    )

    if result["status"] == "rejected":
        click.echo(f"  REJECTED: {result['reason']}")
        for idx, issues in result.get("issues", [])[:5]:
            click.echo(f"    entry[{idx}]: {issues}")
        raise click.ClickException("Validation failed")
    elif result["status"] == "dry_run":
        click.echo(f"  Would append: {result['would_append']} entries")
        click.echo(f"  Duplicates skipped: {result['duplicates_skipped']}")
        click.echo(f"  New total would be: {result['new_total']}")
    elif result["status"] == "success":
        click.echo(f"  Appended: {result['appended']} entries")
        click.echo(f"  Duplicates skipped: {result['duplicates_skipped']}")
        click.echo(f"  New total: {result['new_total']}")
        if result.get("hf_upload", {}).get("status") == "success":
            click.echo(f"  HF uploaded: {result['hf_upload']['file']}")
    else:
        click.echo(f"  {json_mod.dumps(result, indent=2)}")


@data.command(name="canonical-upload")
@click.option("--env", default="all", help="Environment to upload (or 'all')")
@click.pass_context
def data_canonical_upload(ctx, env):
    """Upload canonical file(s) to HuggingFace dataset repo.

    Example: forge data canonical-upload --env NAVWORLD
    """
    from forge.data.canonical_ops import upload_to_hf, upload_all_to_hf, VALID_ROLES

    if env == "all":
        click.echo("Uploading all canonical files to HF...")
        results = upload_all_to_hf()
        for e, r in results.items():
            status = "✅" if r.get("status") == "success" else "❌"
            click.echo(f"  {status} {e}: {r.get('status', 'error')}")
    elif env in VALID_ROLES:
        click.echo(f"Uploading {env} to HF...")
        result = upload_to_hf(env)
        if result["status"] == "success":
            click.echo(f"  ✅ Uploaded: {result['file']}")
        else:
            raise click.ClickException(f"Upload failed: {result.get('reason', 'unknown')}")
    else:
        raise click.ClickException(f"Unknown env '{env}'. Valid: {', '.join(VALID_ROLES.keys())} or 'all'")


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
      forge data navworld-gen -n 50 --type half_day -o data/half_day.jsonl
      forge data navworld-gen -n 50 --phase1  # 8 types × 50 = 400 entries
    """
    import asyncio
    from forge.data.navworld_gen import generate_batch
    from forge.data.navworld_prompts import PHASE1_TYPES

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
            asyncio.run(generate_batch(
                num_samples=num, output_path=out, amap_key=amap_key,
                api_key=api_key, model=model, start_id=start_id + total,
                concurrency=concurrency, problem_type=ptype,
            ))
            total += num
        click.echo(f"\nPhase 1 complete: {total} samples across {len(PHASE1_TYPES)} types")
    else:
        click.echo(f"Generating {num} NAVWORLD samples using {model}")
        if problem_type:
            click.echo(f"Problem type: {problem_type}")
        asyncio.run(generate_batch(
            num_samples=num, output_path=output, amap_key=amap_key,
            api_key=api_key, model=model, start_id=start_id,
            concurrency=concurrency, problem_type=problem_type,
        ))
