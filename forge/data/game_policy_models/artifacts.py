"""Artifact and status helpers for GAME self-play runs."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess

from forge.config import ForgeConfig
from forge.data.game_policy_models.contracts import SelfPlayHeartbeat, SelfPlayStatusEntry, SelfPlayStatusState

REPLAY_WINDOW_ROUNDS = 20
REPLAY_WINDOW_ROWS = 50_000
RECENT_REPLAY_FRACTION = 0.7
PERFECT_INFO_GAMES = {"othello", "hex", "clobber"}
PERFECT_INFO_TEACHER_BUDGETS = {
    "othello": {"sim": 1000, "roll": 20},
    "hex": {"sim": 1000, "roll": 50},
    "clobber": {"sim": 1500, "roll": 100},
}
SELFPLAY_RUNTIME_PROFILES: dict[str, dict[str, object]] = {
    "othello": {
        "simulations": 128,
        "epochs": 2,
        "actor_workers": 64,
        "gpu_actor_concurrency": 12,
        "replay_micro_batch_size": 64,
        "shared_eval_batch_size": 512,
        "shared_eval_latency_ms": 16,
        "cheap_teacher_gate_games": 50,
        "cheap_teacher_gate_min_win_rate": 0.80,
        "learner_steps_per_phase": 1,
        "simulation_scale_ramp": 0.5,
        "simulation_scale_gate_push": 1.5,
        "batch_candidates": [4096, 8192, 12288],
        "replay_window_rounds": 32,
        "replay_window_rows": 200_000,
        "recent_fraction": 0.85,
        "quick_gate_interval_updates": 3,
        "teacher_gate_interval_updates": 5,
        "sync_interval_updates": 10,
        "dataloader_workers": 8,
    },
    "hex": {
        "simulations": 256,
        "epochs": 2,
        "actor_workers": 64,
        "gpu_actor_concurrency": 8,
        "replay_micro_batch_size": 64,
        "shared_eval_batch_size": 384,
        "shared_eval_latency_ms": 16,
        "cheap_teacher_gate_games": 50,
        "cheap_teacher_gate_min_win_rate": 0.80,
        "learner_steps_per_phase": 1,
        "simulation_scale_ramp": 0.5,
        "simulation_scale_gate_push": 1.5,
        "batch_candidates": [4096, 8192, 12288],
        "replay_window_rounds": 32,
        "replay_window_rows": 200_000,
        "recent_fraction": 0.85,
        "quick_gate_interval_updates": 3,
        "teacher_gate_interval_updates": 5,
        "sync_interval_updates": 10,
        "dataloader_workers": 8,
    },
    "clobber": {
        "simulations": 192,
        "epochs": 2,
        "actor_workers": 64,
        "gpu_actor_concurrency": 8,
        "replay_micro_batch_size": 64,
        "shared_eval_batch_size": 384,
        "shared_eval_latency_ms": 16,
        "cheap_teacher_gate_games": 50,
        "cheap_teacher_gate_min_win_rate": 0.80,
        "learner_steps_per_phase": 1,
        "simulation_scale_ramp": 0.5,
        "simulation_scale_gate_push": 1.5,
        "batch_candidates": [4096, 8192, 12288],
        "replay_window_rounds": 32,
        "replay_window_rows": 200_000,
        "recent_fraction": 0.85,
        "quick_gate_interval_updates": 3,
        "teacher_gate_interval_updates": 5,
        "sync_interval_updates": 10,
        "dataloader_workers": 8,
    },
    "leduc_poker": {
        "simulations": 48,
        "epochs": 2,
        "actor_workers": 12,
        "shared_eval_batch_size": 256,
        "shared_eval_latency_ms": 20,
        "cheap_teacher_gate_games": 50,
        "cheap_teacher_gate_min_win_rate": 0.72,
        "learner_steps_per_phase": 2,
        "simulation_scale_ramp": 0.5,
        "simulation_scale_gate_push": 1.5,
        "batch_candidates": [8192, 12288, 16384],
        "replay_window_rounds": 24,
        "replay_window_rows": 100_000,
        "recent_fraction": 0.80,
        "quick_gate_interval_updates": 3,
        "teacher_gate_interval_updates": 5,
        "sync_interval_updates": 10,
        "dataloader_workers": 4,
    },
    "goofspiel": {
        "simulations": 64,
        "epochs": 2,
        "actor_workers": 12,
        "shared_eval_batch_size": 256,
        "shared_eval_latency_ms": 20,
        "cheap_teacher_gate_games": 50,
        "cheap_teacher_gate_min_win_rate": 0.72,
        "learner_steps_per_phase": 2,
        "simulation_scale_ramp": 0.5,
        "simulation_scale_gate_push": 1.5,
        "batch_candidates": [8192, 12288],
        "replay_window_rounds": 24,
        "replay_window_rows": 100_000,
        "recent_fraction": 0.80,
        "quick_gate_interval_updates": 3,
        "teacher_gate_interval_updates": 5,
        "sync_interval_updates": 10,
        "dataloader_workers": 4,
    },
    "liars_dice": {
        "simulations": 32,
        "epochs": 1,
        "actor_workers": 8,
        "shared_eval_batch_size": 192,
        "shared_eval_latency_ms": 24,
        "cheap_teacher_gate_games": 50,
        "cheap_teacher_gate_min_win_rate": 0.72,
        "learner_steps_per_phase": 2,
        "simulation_scale_ramp": 0.5,
        "simulation_scale_gate_push": 1.5,
        "batch_candidates": [4096, 8192],
        "replay_window_rounds": 24,
        "replay_window_rows": 100_000,
        "recent_fraction": 0.80,
        "quick_gate_interval_updates": 3,
        "teacher_gate_interval_updates": 5,
        "sync_interval_updates": 10,
        "dataloader_workers": 4,
    },
    "gin_rummy": {
        "simulations": 24,
        "epochs": 1,
        "actor_workers": 6,
        "shared_eval_batch_size": 192,
        "shared_eval_latency_ms": 24,
        "cheap_teacher_gate_games": 50,
        "cheap_teacher_gate_min_win_rate": 0.72,
        "learner_steps_per_phase": 2,
        "simulation_scale_ramp": 0.5,
        "simulation_scale_gate_push": 1.5,
        "batch_candidates": [2048, 4096, 8192],
        "replay_window_rounds": 24,
        "replay_window_rows": 100_000,
        "recent_fraction": 0.80,
        "quick_gate_interval_updates": 3,
        "teacher_gate_interval_updates": 5,
        "sync_interval_updates": 10,
        "dataloader_workers": 4,
    },
}


def _root_dir(output_dir: str) -> Path:
    return Path(output_dir)


def _latest_dir(output_dir: str) -> Path:
    return _root_dir(output_dir) / "latest"


def _best_dir(output_dir: str) -> Path:
    return _root_dir(output_dir) / "best"


def _history_dir(output_dir: str) -> Path:
    return _root_dir(output_dir) / "history"


def _arena_dir(output_dir: str) -> Path:
    return _root_dir(output_dir) / "arena"


def _status_path(output_dir: str) -> Path:
    return _root_dir(output_dir) / "status.json"


def _replay_path(output_dir: str) -> Path:
    return _root_dir(output_dir) / "replay_meta" / "latest_replay.npz"


def _replay_meta_path(output_dir: str) -> Path:
    return _root_dir(output_dir) / "replay_meta" / "latest.json"


def _arena_path(output_dir: str, name: str) -> Path:
    return _arena_dir(output_dir) / f"{name}.json"


def _heartbeat_path(output_dir: str) -> Path:
    return _root_dir(output_dir) / "heartbeat.json"


def _autotune_path(output_dir: str) -> Path:
    return _root_dir(output_dir) / "autotune.json"


def _policy_repo_id(repo_id: str = "") -> str:
    config = ForgeConfig.load()
    return repo_id or config.hf_game_policy_repo or config.hf_game_teacher_repo


def _ensure_dirs(output_dir: str) -> None:
    for path in (
        _root_dir(output_dir),
        _latest_dir(output_dir),
        _best_dir(output_dir),
        _history_dir(output_dir),
        _arena_dir(output_dir),
        _replay_path(output_dir).parent,
    ):
        path.mkdir(parents=True, exist_ok=True)


def _runtime_profile(game_name: str) -> dict[str, object]:
    return dict(SELFPLAY_RUNTIME_PROFILES.get(game_name, {}))


def _save_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _save_heartbeat(payload: SelfPlayHeartbeat) -> None:
    _heartbeat_path(payload.output_dir).write_text(
        json.dumps(payload.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _gpu_snapshot() -> tuple[float, float]:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return 0.0, 0.0
    if result.returncode != 0 or not result.stdout.strip():
        return 0.0, 0.0
    gpu_util = 0.0
    gpu_mem = 0.0
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        return 0.0, 0.0
    values = lines[0].split(",")
    if len(values) != 3:
        return 0.0, 0.0
    try:
        gpu_util = float(values[0].strip())
        used = float(values[1].strip())
        total = float(values[2].strip())
        gpu_mem = (used / total * 100.0) if total > 0 else 0.0
    except ValueError:
        return 0.0, 0.0
    return gpu_util, gpu_mem


def _history_checkpoint_dir(output_dir: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return _history_dir(output_dir) / stamp


def _promote_latest_to_best(output_dir: str) -> str:
    latest = _latest_dir(output_dir)
    best = _best_dir(output_dir)
    best.mkdir(parents=True, exist_ok=True)
    history_target = _history_checkpoint_dir(output_dir)
    history_target.mkdir(parents=True, exist_ok=True)
    if (best / "model.pt").exists():
        for filename in ("model.pt", "metadata.json"):
            source = best / filename
            if source.exists():
                shutil.copy2(source, history_target / filename)
    for filename in ("model.pt", "metadata.json"):
        src = latest / filename
        if src.exists():
            shutil.copy2(src, best / filename)
    return str(best / "model.pt")


def _load_status(output_dir: str, game_name: str) -> SelfPlayStatusState:
    status_file = _status_path(output_dir)
    if not status_file.exists():
        return SelfPlayStatusState(game=game_name, output_dir=output_dir)
    return SelfPlayStatusState.model_validate_json(status_file.read_text(encoding="utf-8"))


def _save_status(state: SelfPlayStatusState) -> None:
    _save_json(_status_path(state.output_dir), state.model_dump(mode="json"))


def sync_selfplay_artifacts_to_hf(*, game_name: str, output_dir: str, repo_id: str = "", token: str = "") -> str:
    resolved_repo = _policy_repo_id(repo_id)
    if not resolved_repo:
        return ""
    try:
        from huggingface_hub import HfApi
    except ImportError as exc:
        raise RuntimeError("huggingface_hub is required to sync GAME self-play artifacts") from exc
    api = HfApi(token=token or ForgeConfig.load().hf_token)
    api.create_repo(repo_id=resolved_repo, repo_type="model", private=True, exist_ok=True)
    uploads = [
        (_status_path(output_dir), f"checkpoints/{game_name}/status.json"),
        (_heartbeat_path(output_dir), f"checkpoints/{game_name}/heartbeat.json"),
        (_autotune_path(output_dir), f"checkpoints/{game_name}/autotune.json"),
        (_latest_dir(output_dir) / "model.pt", f"checkpoints/{game_name}/latest/model.pt"),
        (_latest_dir(output_dir) / "metadata.json", f"checkpoints/{game_name}/latest/metadata.json"),
        (_best_dir(output_dir) / "model.pt", f"checkpoints/{game_name}/best/model.pt"),
        (_best_dir(output_dir) / "metadata.json", f"checkpoints/{game_name}/best/metadata.json"),
        (_arena_path(output_dir, "quick_eval"), f"arena/{game_name}/quick_eval.json"),
        (_arena_path(output_dir, "teacher_eval"), f"arena/{game_name}/teacher_eval.json"),
        (_replay_meta_path(output_dir), f"replay_meta/{game_name}/latest.json"),
    ]
    for local_path, repo_path in uploads:
        if not local_path.exists():
            continue
        api.upload_file(
            path_or_fileobj=str(local_path),
            path_in_repo=repo_path,
            repo_id=resolved_repo,
            repo_type="model",
            commit_message=f"update {game_name} selfplay artifacts",
        )
    return resolved_repo


def restore_selfplay_artifacts_from_hf(*, game_name: str, output_dir: str, repo_id: str = "", token: str = "") -> bool:
    resolved_repo = _policy_repo_id(repo_id)
    if not resolved_repo:
        return False
    try:
        from huggingface_hub import HfApi, hf_hub_download
    except ImportError as exc:
        raise RuntimeError("huggingface_hub is required to restore GAME self-play artifacts") from exc
    api = HfApi(token=token or ForgeConfig.load().hf_token)
    try:
        files = set(api.list_repo_files(repo_id=resolved_repo, repo_type="model"))
    except Exception:
        return False
    prefix_map = {
        f"checkpoints/{game_name}/status.json": _status_path(output_dir),
        f"checkpoints/{game_name}/heartbeat.json": _heartbeat_path(output_dir),
        f"checkpoints/{game_name}/autotune.json": _autotune_path(output_dir),
        f"checkpoints/{game_name}/latest/model.pt": _latest_dir(output_dir) / "model.pt",
        f"checkpoints/{game_name}/latest/metadata.json": _latest_dir(output_dir) / "metadata.json",
        f"checkpoints/{game_name}/best/model.pt": _best_dir(output_dir) / "model.pt",
        f"checkpoints/{game_name}/best/metadata.json": _best_dir(output_dir) / "metadata.json",
        f"arena/{game_name}/quick_eval.json": _arena_path(output_dir, "quick_eval"),
        f"arena/{game_name}/teacher_eval.json": _arena_path(output_dir, "teacher_eval"),
        f"replay_meta/{game_name}/latest.json": _replay_meta_path(output_dir),
    }
    restored = False
    for repo_file, local_target in prefix_map.items():
        if repo_file not in files:
            continue
        local_target.parent.mkdir(parents=True, exist_ok=True)
        downloaded = hf_hub_download(
            repo_id=resolved_repo,
            filename=repo_file,
            repo_type="model",
            token=token or ForgeConfig.load().hf_token,
        )
        shutil.copy2(downloaded, local_target)
        restored = True
    return restored


def selfplay_status(*, game_name: str, output_dir: str) -> SelfPlayStatusEntry:
    root = Path(output_dir)
    status_file = _status_path(output_dir)
    latest_dir = _latest_dir(output_dir)
    best_dir = _best_dir(output_dir)
    latest_metadata: dict[str, object] = {}
    best_metadata: dict[str, object] = {}
    if (latest_dir / "metadata.json").exists():
        latest_metadata = _load_json(latest_dir / "metadata.json")
    if (best_dir / "metadata.json").exists():
        best_metadata = _load_json(best_dir / "metadata.json")
    payload = _load_json(status_file) if status_file.exists() else {}
    return SelfPlayStatusEntry(
        game=game_name,
        output_dir=str(root),
        exists=status_file.exists(),
        latest_exists=(latest_dir / "metadata.json").exists() and (latest_dir / "model.pt").exists(),
        best_exists=(best_dir / "metadata.json").exists() and (best_dir / "model.pt").exists(),
        status=payload,
        latest_metadata=latest_metadata,
        best_metadata=best_metadata,
        persisted_repo=str(payload.get("persisted_repo", "")),
    )
