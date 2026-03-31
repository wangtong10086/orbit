"""Service-layer orchestration for the GAME long-running job."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import threading

from forge.data.game_gen import generate_game_data
from forge.data.game_generators.base import count_jsonl_records
from forge.data.game_policy_models import sync_selfplay_artifacts_to_hf, train_selfplay_policy_model
from forge.domain_jobs.game_longrun.contracts import (
    PERFECT_INFO_GAMES,
    GameLongRunConfig,
    GameLongRunState,
    IMPERFECT_INFO_GAMES,
    LongRunCollectionState,
    LongRunTrainingState,
)


def default_longrun_root(job_name: str) -> str:
    return str(Path(__file__).resolve().parents[3] / "artifacts" / "game_longrun" / job_name)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state_path(root_dir: str) -> Path:
    return Path(root_dir) / "state.json"


def _stop_path(root_dir: str) -> Path:
    return Path(root_dir) / "STOP"


def _dataset_path(root_dir: str, bucket: str, game: str) -> str:
    return str(Path(root_dir) / "datasets" / bucket / f"{game}.jsonl")


def _model_dir(game: str) -> str:
    return str(Path(__file__).resolve().parents[3] / "artifacts" / "game_policy_models" / game / "default")


def _tmp_chunk_path(root_dir: str, bucket: str, game: str, chunk_index: int) -> Path:
    path = Path(root_dir) / "tmp" / bucket
    path.mkdir(parents=True, exist_ok=True)
    return path / f"{game}_chunk_{chunk_index}.jsonl"


def _training_profile(config: GameLongRunConfig, game: str) -> dict[str, int | bool]:
    if game == "othello":
        return {"episodes": config.selfplay_episodes, "simulations": 128, "epochs": 2, "batch_size": config.batch_size}
    if game == "hex":
        return {"episodes": config.selfplay_episodes, "simulations": 256, "epochs": 2, "batch_size": config.batch_size}
    if game == "clobber":
        return {"episodes": config.selfplay_episodes, "simulations": 192, "epochs": 2, "batch_size": config.batch_size}
    if game == "leduc_poker":
        return {"episodes": config.selfplay_episodes, "simulations": 48, "epochs": 2, "batch_size": config.batch_size}
    if game == "goofspiel":
        return {"episodes": config.selfplay_episodes, "simulations": 64, "epochs": 2, "batch_size": config.batch_size}
    if game == "liars_dice":
        return {"episodes": max(config.selfplay_episodes // 2, 64), "simulations": 32, "epochs": 1, "batch_size": min(config.batch_size, 8192)}
    if game == "gin_rummy":
        return {"episodes": max(config.selfplay_episodes // 2, 64), "simulations": 24, "epochs": 1, "batch_size": min(config.batch_size, 4096)}
    return {
        "episodes": config.selfplay_episodes,
        "simulations": config.selfplay_simulations,
        "epochs": config.selfplay_epochs,
        "batch_size": config.batch_size,
    }


class _StateStore:
    def __init__(self, path: Path, initial: GameLongRunState):
        self.path = path
        self.lock = threading.Lock()
        self.state = initial
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.write()

    def write(self) -> None:
        self.path.write_text(json.dumps(self.state.model_dump(mode="json"), indent=2, ensure_ascii=False), encoding="utf-8")

    def update(self, **kwargs) -> GameLongRunState:
        with self.lock:
            self.state = self.state.model_copy(update={**kwargs, "updated_at": _timestamp()})
            self.write()
            return self.state

    def update_collection(self, section: str, task: LongRunCollectionState) -> None:
        with self.lock:
            current = dict(getattr(self.state, section))
            current[task.game] = task
            self.state = self.state.model_copy(update={section: current, "updated_at": _timestamp()})
            self.write()

    def update_training_section(self, section: str, task: LongRunTrainingState) -> None:
        with self.lock:
            current = dict(getattr(self.state, section))
            current[task.game] = task
            self.state = self.state.model_copy(update={section: current, "updated_at": _timestamp()})
            self.write()

    def append_note(self, note: str) -> None:
        with self.lock:
            notes = list(self.state.notes)
            notes.append(f"[{_timestamp()}] {note}")
            self.state = self.state.model_copy(update={"notes": notes, "updated_at": _timestamp()})
            self.write()

    def update_model_sync(self, game: str, repo_id: str) -> None:
        with self.lock:
            sync = dict(self.state.model_sync)
            sync[game] = repo_id
            self.state = self.state.model_copy(update={"model_sync": sync, "updated_at": _timestamp()})
            self.write()


def _append_jsonl(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with src.open(encoding="utf-8") as input_handle, dst.open("a", encoding="utf-8") as output_handle:
        for line in input_handle:
            if line.strip():
                output_handle.write(line)


def _collect_loop(*, store: _StateStore, section: str, game: str, generator_source: str, target_count: int, chunk_size: int, attempt_multiplier: int, root_dir: str, stop_flag: Path, start_seed: int) -> LongRunCollectionState:
    bucket = "perfect" if section == "perfect_collection" else "imperfect"
    output_path = Path(_dataset_path(root_dir, bucket, game))
    current = count_jsonl_records(output_path)
    task = LongRunCollectionState(
        game=game,
        generator_source=generator_source,
        output_path=str(output_path),
        target_count=target_count,
        current_count=current,
        chunk_size=chunk_size,
        chunks_completed=0,
        seed_cursor=start_seed,
        status="running" if current < target_count else "completed",
        updated_at=_timestamp(),
    )
    store.update_collection(section, task)
    if current >= target_count:
        return task
    while current < target_count:
        if stop_flag.exists():
            task = task.model_copy(update={"status": "stopped", "current_count": current, "updated_at": _timestamp()})
            store.update_collection(section, task)
            return task
        chunk_index = task.chunks_completed
        chunk_target = min(chunk_size, target_count - current)
        tmp_path = _tmp_chunk_path(root_dir, section, game, chunk_index)
        generate_game_data(
            output_path=str(tmp_path),
            game_name=game,
            sample_count=chunk_target,
            start_seed=task.seed_cursor,
            attempt_multiplier=attempt_multiplier,
            generator_source=generator_source,
        )
        _append_jsonl(tmp_path, output_path)
        tmp_path.unlink(missing_ok=True)
        current = count_jsonl_records(output_path)
        task = task.model_copy(
            update={
                "current_count": current,
                "chunks_completed": task.chunks_completed + 1,
                "seed_cursor": task.seed_cursor + 1_000_000,
                "status": "completed" if current >= target_count else "running",
                "updated_at": _timestamp(),
            }
        )
        store.update_collection(section, task)
        store.append_note(
            f"{section}:{game} chunk={task.chunks_completed} records={current}/{target_count} source={generator_source}"
        )
    return task


def _train_one_game(*, store: _StateStore, config: GameLongRunConfig, game: str, stop_flag: Path, section: str) -> LongRunTrainingState:
    rounds = 0
    profile = _training_profile(config, game)
    task = LongRunTrainingState(
        game=game,
        output_dir=_model_dir(game),
        status="running",
        updated_at=_timestamp(),
    )
    store.update_training_section(section, task)
    while rounds < config.max_rounds_per_game:
        if stop_flag.exists():
            task = task.model_copy(update={"status": "stopped", "updated_at": _timestamp()})
            store.update_training_section(section, task)
            return task
        quick_gate_min = 0.55 if game in PERFECT_INFO_GAMES and config.quick_gate_min_win_rate <= 0.52 else config.quick_gate_min_win_rate
        report = train_selfplay_policy_model(
            game_name=game,
            output_dir=_model_dir(game),
            selfplay_episodes=int(profile["episodes"]),
            start_seed=100000 + rounds * config.seed_stride,
            simulations=int(profile["simulations"]),
            epochs=int(profile["epochs"]),
            batch_size=int(profile["batch_size"]),
            autotune_batch_size=config.autotune_batch,
            learning_rate=config.learning_rate,
            weight_decay=config.weight_decay,
            device=config.device,
            quick_gate_games=config.quick_gate_games,
            teacher_gate_games=config.teacher_gate_games,
            quick_gate_interval_updates=config.quick_gate_interval_updates,
            teacher_gate_interval_updates=config.teacher_gate_interval_updates,
            sync_interval_updates=config.sync_interval_updates,
            resume=True,
            repo_id=config.policy_repo_id,
            quick_gate_min_win_rate=quick_gate_min,
            teacher_gate_min_win_rate=config.teacher_gate_min_win_rate,
            teacher_gate_required_streak=config.teacher_gate_required_streak,
        )
        rounds += 1
        task = task.model_copy(
            update={
                "rounds_completed": rounds,
                "status": "completed"
                if report.teacher_pass_streak >= config.teacher_gate_required_streak
                and (report.teacher_eval.win_rate if report.teacher_eval else 0.0) >= config.teacher_gate_min_win_rate
                else "running",
                "last_quick_win_rate": report.quick_eval.win_rate if report.quick_eval else 0.0,
                "last_teacher_win_rate": report.teacher_eval.win_rate if report.teacher_eval else 0.0,
                "teacher_pass_streak": report.teacher_pass_streak,
                "latest_checkpoint": report.latest_checkpoint,
                "best_checkpoint": report.best_checkpoint,
                "persisted_repo": report.persisted_repo,
                "autotuned_batch_size": report.batch_size,
                "updated_at": _timestamp(),
            }
        )
        store.update_training_section(section, task)
        store.append_note(
            f"train:{game} round={rounds} quick={task.last_quick_win_rate:.3f} teacher={task.last_teacher_win_rate:.3f} streak={task.teacher_pass_streak}"
        )
        if task.status == "completed":
            return task
    task = task.model_copy(update={"status": "failed", "last_error": "max_rounds_exceeded", "updated_at": _timestamp()})
    store.update_training_section(section, task)
    return task


def _sync_models(store: _StateStore, config: GameLongRunConfig) -> None:
    for game in (*PERFECT_INFO_GAMES, *IMPERFECT_INFO_GAMES):
        repo_id = sync_selfplay_artifacts_to_hf(
            game_name=game,
            output_dir=_model_dir(game),
            repo_id=config.policy_repo_id,
        )
        if repo_id:
            store.update_model_sync(game, repo_id)
            store.append_note(f"model-sync:{game} repo={repo_id}")


def run_game_longrun_job(config: GameLongRunConfig) -> GameLongRunState:
    root = Path(config.root_dir)
    root.mkdir(parents=True, exist_ok=True)
    stop_flag = _stop_path(config.root_dir)
    initial_state = GameLongRunState(
        job_name=config.job_name,
        root_dir=config.root_dir,
        status="running",
        phase="bootstrap",
        started_at=_timestamp(),
        updated_at=_timestamp(),
        perfect_collection={
            game: LongRunCollectionState(
                game=game,
                generator_source="policy_model",
                output_path=_dataset_path(config.root_dir, "perfect", game),
                target_count=config.perfect_target,
                chunk_size=config.perfect_chunk,
                seed_cursor=100000,
                updated_at=_timestamp(),
            )
            for game in PERFECT_INFO_GAMES
        },
        perfect_training={
            game: LongRunTrainingState(game=game, output_dir=_model_dir(game), updated_at=_timestamp())
            for game in PERFECT_INFO_GAMES
        },
        imperfect_training={
            game: LongRunTrainingState(game=game, output_dir=_model_dir(game), updated_at=_timestamp())
            for game in IMPERFECT_INFO_GAMES
        },
        imperfect_collection={
            game: LongRunCollectionState(
                game=game,
                generator_source="policy_model",
                output_path=_dataset_path(config.root_dir, "imperfect", game),
                target_count=config.imperfect_target,
                chunk_size=config.imperfect_chunk,
                seed_cursor=700000,
                updated_at=_timestamp(),
            )
            for game in IMPERFECT_INFO_GAMES
        },
    )
    store = _StateStore(_state_path(config.root_dir), initial_state)
    store.append_note("job started")
    try:
        store.update(phase="perfect_training")
        for game in PERFECT_INFO_GAMES:
            trained = _train_one_game(store=store, config=config, game=game, stop_flag=stop_flag, section="perfect_training")
            if trained.status != "completed":
                raise RuntimeError(f"self-play training did not complete for {game}: {trained.last_error or trained.status}")
        store.update(phase="perfect_collection")
        for idx, game in enumerate(PERFECT_INFO_GAMES):
            collected = _collect_loop(
                store=store,
                section="perfect_collection",
                game=game,
                generator_source="policy_model",
                target_count=config.perfect_target,
                chunk_size=config.perfect_chunk,
                attempt_multiplier=config.perfect_attempt_multiplier,
                root_dir=config.root_dir,
                stop_flag=stop_flag,
                start_seed=100000 + idx * config.seed_stride,
            )
            if collected.status not in {"completed", "stopped"}:
                raise RuntimeError(f"policy-model collection failed for {game}: {collected.last_error or collected.status}")
        store.update(phase="imperfect_training")
        for game in IMPERFECT_INFO_GAMES:
            trained = _train_one_game(store=store, config=config, game=game, stop_flag=stop_flag, section="imperfect_training")
            if trained.status != "completed":
                raise RuntimeError(f"self-play training did not complete for {game}: {trained.last_error or trained.status}")
        store.update(phase="model_sync")
        _sync_models(store, config)
        store.update(phase="imperfect_collection")
        for idx, game in enumerate(IMPERFECT_INFO_GAMES):
            collected = _collect_loop(
                store=store,
                section="imperfect_collection",
                game=game,
                generator_source="policy_model",
                target_count=config.imperfect_target,
                chunk_size=config.imperfect_chunk,
                attempt_multiplier=config.imperfect_attempt_multiplier,
                root_dir=config.root_dir,
                stop_flag=stop_flag,
                start_seed=900000 + idx * config.seed_stride,
            )
            if collected.status not in {"completed", "stopped"}:
                raise RuntimeError(f"policy-model collection failed for {game}: {collected.last_error or collected.status}")
        final_state = store.update(status="completed", phase="completed")
        store.append_note("job completed")
        return final_state
    except Exception as exc:
        store.append_note(f"job failed: {exc}")
        store.update(status="failed", phase="failed")
        raise


def load_game_longrun_state(root_dir: str) -> GameLongRunState:
    return GameLongRunState.model_validate_json(_state_path(root_dir).read_text(encoding="utf-8"))


def request_game_longrun_stop(root_dir: str) -> None:
    path = _stop_path(root_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("stop\n", encoding="utf-8")
