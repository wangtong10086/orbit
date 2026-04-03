"""GAME-specific data CLI commands."""

from __future__ import annotations

import json
import os

import click

from forge.data.collect_service import build_collect_spec, local_collect_pipeline
from forge.data.game_trajectory_generators import resolve_game_trajectory_generator
from forge.foundation.data_contracts import IngestReport

GAME_TEACHER_GAMES = ["goofspiel", "leduc_poker", "liars_dice", "gin_rummy"]
SELFPLAY_GAMES = ["othello", "hex", "clobber", "goofspiel", "leduc_poker", "liars_dice", "gin_rummy"]


def _report_ingest_result(result: dict | IngestReport) -> None:
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
    click.echo(json.dumps(payload, indent=2, ensure_ascii=False))


@click.command(name="game-gen")
@click.option("--game", "game_name", default=None, type=click.Choice(SELFPLAY_GAMES))
@click.option("--all", "all_games", is_flag=True, help="Generate every supported GAME environment")
@click.option("-n", "--num", default=10, type=int, help="Target kept samples per game")
@click.option("-o", "--output", default="data/game_synthetic.jsonl", help="Output staging path")
@click.option("--start-seed", default=100000, type=int, help="Starting seed")
@click.option("--attempt-multiplier", default=4, type=int, help="Maximum oversampling factor while searching for kept wins")
@click.option("--generator-source", default="default", type=click.Choice(["default", "policy_model"]), help="Select the active GAME sampling backend")
@click.option("--ingest", is_flag=True, help="Auto-ingest generated samples into canonical GAME")
def game_gen(game_name, all_games, num, output, start_seed, attempt_multiplier, generator_source, ingest):
    """Generate local GAME data using the registry-selected generator."""
    if not all_games and not game_name:
        raise click.ClickException("Specify --game or --all")
    spec = build_collect_spec(
        env_name="GAME",
        output_filename=os.path.basename(output),
        hf_repo=os.environ.get("HF_DATASET_REPO", ""),
        source="game_algorithm_local",
        num=num,
        model="",
        start_id=start_seed,
        concurrency=0,
        problem_type=None,
        phase1=False,
        seeds="",
        subtasks="",
        plugins="",
        cache_dir="",
        timeout=0,
        game_name=game_name,
        all_games=all_games,
        attempt_multiplier=attempt_multiplier,
        generator_source=generator_source,
        templates=(),
        tier="lite",
        tier_mix=False,
        jobs=1,
        split_target=0,
        balance=False,
        shuffle_seed=42,
        machine="",
    )
    report = local_collect_pipeline(spec, staging_path=output, ingest=ingest)
    result = report.collect.model_dump(mode="json")
    click.echo(f"Generated {result['records']} GAME samples -> {output}")
    for name, count in sorted(result["per_game"].items()):
        click.echo(f"  {name}: {count}")
    click.echo(f"  generator_source: {result.get('generator_source', generator_source)}")
    if ingest:
        click.echo("\nAppending to canonical...")
        _report_ingest_result(report.ingest)


@click.command(name="game-build-policy")
@click.option("--game", "game_name", required=True, type=click.Choice(GAME_TEACHER_GAMES))
@click.option("--algo", default="", help="Override algorithm family (defaults to the registry family)")
@click.option("--output", default="", help="Override output policy snapshot path")
@click.option("--iterations", default=0, type=int, help="Override solver iterations")
def game_build_policy(game_name, algo, output, iterations):
    """Build an offline policy snapshot for GAME trajectory collection."""
    from forge.data.game_generators.policy_generators import build_policy_snapshot

    spec = resolve_game_trajectory_generator(game_name)
    family = algo or spec.family
    if family not in {"cfr", "mccfr", "deep_cfr"}:
        raise click.ClickException(
            f"{game_name} uses `{spec.family}` in the registry; only policy-based families can be built here"
        )
    if not spec.policy_path and not output:
        raise click.ClickException(f"{game_name} does not declare a default policy path")
    report = build_policy_snapshot(
        game_name=game_name,
        generator_name=spec.name,
        family=family,
        params=spec.game_params,
        output_path=output or spec.policy_path,
        iterations=iterations or spec.default_iterations,
    )
    click.echo(json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False))


@click.command(name="game-policy-status")
@click.option("--game", "game_name", default="", type=click.Choice(GAME_TEACHER_GAMES))
def game_policy_status(game_name):
    """Show the current policy-snapshot status for GAME generators."""
    from forge.data.game_generators.policy_generators import policy_status

    names = [game_name] if game_name else GAME_TEACHER_GAMES
    payload = []
    for name in names:
        spec = resolve_game_trajectory_generator(name)
        payload.append(
            policy_status(
                game_name=name,
                generator_name=spec.name,
                family=spec.family,
                policy_path=spec.policy_path,
            ).model_dump(mode="json")
        )
    click.echo(json.dumps(payload, indent=2, ensure_ascii=False))


@click.command(name="game-upload-teacher")
@click.option("--game", "game_name", required=True, type=click.Choice(GAME_TEACHER_GAMES))
@click.option("--repo", default="", help="Target HF model repo (default: HF_GAME_TEACHER_REPO)")
@click.option("--policy-path", default="", help="Override local teacher snapshot path")
@click.option("--private/--public", default=True, help="Create or keep the target HF model repo private")
@click.option("--readme/--no-readme", default=True, help="Upload or refresh the repo-level README")
def game_upload_teacher(game_name, repo, policy_path, private, readme):
    """Upload a finished GAME exact-teacher snapshot to a private HF model repo."""
    from forge.data.game_teacher_repo import upload_teacher_snapshot

    spec = resolve_game_trajectory_generator(game_name)
    family = spec.family
    if family not in {"cfr", "mccfr", "deep_cfr"}:
        raise click.ClickException(
            f"{game_name} uses `{family}` in the registry; only policy-based teachers can be uploaded here"
        )
    report = upload_teacher_snapshot(
        game_name=game_name,
        family=family,
        policy_path=policy_path or spec.policy_path,
        repo_id=repo,
        private=private,
        update_readme=readme,
    )
    if report.status != "success":
        raise click.ClickException(report.reason or "teacher upload failed")
    click.echo(json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False))


@click.command(name="game-train-policy-model")
@click.option("--game", "game_name", required=True, type=click.Choice(GAME_TEACHER_GAMES))
@click.option("--dataset", "dataset_path", required=True, help="Expert dataset produced by game-build-expert-dataset")
@click.option("--output", default="", help="Output policy-model directory")
@click.option("--hidden-dim", default=256, type=int, help="MLP hidden size")
@click.option("--batch-size", default=512, type=int, help="Training batch size")
@click.option("--epochs", default=10, type=int, help="Training epochs")
@click.option("--lr", default=1e-3, type=float, help="Learning rate")
@click.option("--weight-decay", default=1e-4, type=float, help="AdamW weight decay")
@click.option("--device", default="", help="Torch device override (default: cuda if available)")
def game_train_policy_model(game_name, dataset_path, output, hidden_dim, batch_size, epochs, lr, weight_decay, device):
    """Train a small PyTorch action model for one imperfect-information GAME."""
    from forge.data.game_policy_models import default_policy_model_dir, train_policy_model

    report = train_policy_model(
        game_name=game_name,
        dataset_path=dataset_path,
        output_dir=output or default_policy_model_dir(game_name),
        hidden_dim=hidden_dim,
        batch_size=batch_size,
        epochs=epochs,
        learning_rate=lr,
        weight_decay=weight_decay,
        device=device,
    )
    click.echo(json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False))


@click.command(name="game-policy-model-status")
@click.option("--game", "game_name", default="", type=click.Choice(SELFPLAY_GAMES))
def game_policy_model_status(game_name):
    """Show the trained policy-model status for GAME policy samplers."""
    from forge.data.game_policy_models import default_policy_model_dir, policy_model_status

    names = [game_name] if game_name else SELFPLAY_GAMES
    payload = []
    for name in names:
        payload.append(
            policy_model_status(
                game_name=name,
                model_dir=default_policy_model_dir(name),
            ).model_dump(mode="json")
        )
    click.echo(json.dumps(payload, indent=2, ensure_ascii=False))


GAME_COMMANDS = [
    game_gen,
    game_build_policy,
    game_policy_status,
    game_upload_teacher,
    game_train_policy_model,
    game_policy_model_status,
]
