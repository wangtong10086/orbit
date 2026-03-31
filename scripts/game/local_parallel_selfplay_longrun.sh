#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON_BIN="${AFFINE_LOCAL_PYTHON:-${PROJECT_ROOT}/.venv/bin/python}"
JOB_NAME="${AFFINE_GAME_LOCAL_JOB_NAME:-formal-7gpu-teacher90-streak3}"
RUN_ROOT="${AFFINE_GAME_LOCAL_RUN_ROOT:-${PROJECT_ROOT}/artifacts/game_local_runs/${JOB_NAME}}"
LOG_DIR="${RUN_ROOT}/logs"
PID_DIR="${RUN_ROOT}/pids"
CFG_DIR="${RUN_ROOT}/configs"
STATUS_DIR="${RUN_ROOT}/status"
mkdir -p "${LOG_DIR}" "${PID_DIR}" "${CFG_DIR}" "${STATUS_DIR}"

GAMES=(goofspiel leduc_poker liars_dice gin_rummy othello hex clobber)
GPUS=(0 1 2 3 4 5 6)

game_episodes() {
  case "$1" in
    liars_dice|gin_rummy) echo "${AFFINE_GAME_SELFPLAY_EPISODES_IMPERFECT_SMALL:-128}" ;;
    *) echo "${AFFINE_GAME_SELFPLAY_EPISODES_DEFAULT:-256}" ;;
  esac
}

game_simulations() {
  case "$1" in
    othello) echo "${AFFINE_GAME_SELFPLAY_SIM_OTHELLO:-128}" ;;
    hex) echo "${AFFINE_GAME_SELFPLAY_SIM_HEX:-256}" ;;
    clobber) echo "${AFFINE_GAME_SELFPLAY_SIM_CLOBBER:-192}" ;;
    leduc_poker) echo "${AFFINE_GAME_SELFPLAY_SIM_LEDUC:-48}" ;;
    goofspiel) echo "${AFFINE_GAME_SELFPLAY_SIM_GOOFSPIEL:-64}" ;;
    liars_dice) echo "${AFFINE_GAME_SELFPLAY_SIM_LIARS_DICE:-32}" ;;
    gin_rummy) echo "${AFFINE_GAME_SELFPLAY_SIM_GIN_RUMMY:-24}" ;;
    *) echo "${AFFINE_GAME_SELFPLAY_SIM_DEFAULT:-64}" ;;
  esac
}

game_epochs() {
  case "$1" in
    liars_dice|gin_rummy) echo "${AFFINE_GAME_SELFPLAY_EPOCHS_SMALL:-1}" ;;
    *) echo "${AFFINE_GAME_SELFPLAY_EPOCHS_DEFAULT:-2}" ;;
  esac
}

game_quick_min() {
  case "$1" in
    othello|hex|clobber) echo "${AFFINE_GAME_SELFPLAY_QUICK_MIN_PERFECT:-0.55}" ;;
    *) echo "${AFFINE_GAME_SELFPLAY_QUICK_MIN_IMPERFECT:-0.52}" ;;
  esac
}

game_output_dir() {
  echo "${RUN_ROOT}/outputs/$1"
}

game_log_path() {
  echo "${LOG_DIR}/$1.log"
}

game_pid_path() {
  echo "${PID_DIR}/$1.pid"
}

game_session_name() {
  echo "${JOB_NAME}-$1"
}

game_cfg_path() {
  echo "${CFG_DIR}/$1.json"
}

is_running() {
  local session="$1"
  screen -ls 2>/dev/null | grep -Eq "[[:space:]][0-9]+\\.${session}[[:space:]]"
}

write_config() {
  local game="$1"
  local gpu="$2"
  local output_dir="$3"
  local cfg_path
  cfg_path="$(game_cfg_path "${game}")"
  "${PYTHON_BIN}" - <<PY
import json
from pathlib import Path

payload = {
    "job_name": "${JOB_NAME}",
    "game": "${game}",
    "gpu": ${gpu},
    "output_dir": "${output_dir}",
    "episodes": int("${EPISODES}"),
    "simulations": int("${SIMULATIONS}"),
    "epochs": int("${EPOCHS}"),
    "batch_size_ceiling": int("${BATCH_SIZE}"),
    "quick_gate_games": int("${QUICK_GATE_GAMES}"),
    "quick_gate_min_win_rate": float("${QUICK_MIN}"),
    "teacher_gate_games": int("${TEACHER_GATE_GAMES}"),
    "teacher_gate_min_win_rate": float("${TEACHER_MIN}"),
    "teacher_gate_required_streak": int("${REQUIRED_STREAK}"),
    "quick_gate_interval": int("${QUICK_INTERVAL}"),
    "teacher_gate_interval": int("${TEACHER_INTERVAL}"),
    "sync_interval": int("${SYNC_INTERVAL}"),
    "max_rounds": int("${MAX_ROUNDS}"),
    "resume": True,
    "autotune_batch": True,
}
Path("${cfg_path}").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
PY
}

launch_one() {
  local game="$1"
  local gpu="$2"
  local pid_path log_path output_dir cfg_path session
  pid_path="$(game_pid_path "${game}")"
  log_path="$(game_log_path "${game}")"
  output_dir="$(game_output_dir "${game}")"
  cfg_path="$(game_cfg_path "${game}")"
  session="$(game_session_name "${game}")"

  if is_running "${session}"; then
    echo "RUNNING ${game} session=${session} gpu=${gpu} log=${log_path}"
    return 0
  fi

  mkdir -p "${output_dir}"
  EPISODES="$(game_episodes "${game}")"
  SIMULATIONS="$(game_simulations "${game}")"
  EPOCHS="$(game_epochs "${game}")"
  BATCH_SIZE="${AFFINE_GAME_SELFPLAY_BATCH_CEILING:-16384}"
  QUICK_GATE_GAMES="${AFFINE_GAME_SELFPLAY_QUICK_GAMES:-50}"
  QUICK_MIN="$(game_quick_min "${game}")"
  TEACHER_GATE_GAMES="${AFFINE_GAME_SELFPLAY_TEACHER_GAMES:-200}"
  TEACHER_MIN="${AFFINE_GAME_SELFPLAY_TEACHER_MIN_WIN_RATE:-0.90}"
  REQUIRED_STREAK="${AFFINE_GAME_SELFPLAY_REQUIRED_STREAK:-3}"
  QUICK_INTERVAL="${AFFINE_GAME_SELFPLAY_QUICK_INTERVAL:-3}"
  TEACHER_INTERVAL="${AFFINE_GAME_SELFPLAY_TEACHER_INTERVAL:-5}"
  SYNC_INTERVAL="${AFFINE_GAME_SELFPLAY_SYNC_INTERVAL:-10}"
  MAX_ROUNDS="${AFFINE_GAME_SELFPLAY_MAX_ROUNDS:-1000}"
  write_config "${game}" "${gpu}" "${output_dir}"

  screen -S "${session}" -X quit 2>/dev/null || true
  screen -dmS "${session}" bash -lc "
    cd '${PROJECT_ROOT}' && \
    export PYTHONPATH='${PROJECT_ROOT}' && \
    export PYTHONUNBUFFERED=1 && \
    export CUDA_DEVICE_ORDER=PCI_BUS_ID && \
    export CUDA_VISIBLE_DEVICES='${gpu}' && \
    export AFFINE_GAME_NAME='${game}' && \
    export AFFINE_GAME_POLICY_MODEL_DIR='${output_dir}' && \
    export AFFINE_GAME_SELFPLAY_EPISODES='${EPISODES}' && \
    export AFFINE_GAME_SELFPLAY_SIMULATIONS='${SIMULATIONS}' && \
    export AFFINE_GAME_POLICY_EPOCHS='${EPOCHS}' && \
    export AFFINE_GAME_POLICY_BATCH_SIZE='${BATCH_SIZE}' && \
    export AFFINE_GAME_POLICY_LR='${AFFINE_GAME_POLICY_LR:-5e-4}' && \
    export AFFINE_GAME_POLICY_WEIGHT_DECAY='${AFFINE_GAME_POLICY_WEIGHT_DECAY:-1e-4}' && \
    export AFFINE_GAME_POLICY_DEVICE='cuda' && \
    export AFFINE_GAME_SELFPLAY_QUICK_GAMES='${QUICK_GATE_GAMES}' && \
    export AFFINE_GAME_SELFPLAY_QUICK_MIN_WIN_RATE='${QUICK_MIN}' && \
    export AFFINE_GAME_SELFPLAY_TEACHER_GAMES='${TEACHER_GATE_GAMES}' && \
    export AFFINE_GAME_SELFPLAY_TEACHER_MIN_WIN_RATE='${TEACHER_MIN}' && \
    export AFFINE_GAME_SELFPLAY_REQUIRED_STREAK='${REQUIRED_STREAK}' && \
    export AFFINE_GAME_SELFPLAY_QUICK_INTERVAL='${QUICK_INTERVAL}' && \
    export AFFINE_GAME_SELFPLAY_TEACHER_INTERVAL='${TEACHER_INTERVAL}' && \
    export AFFINE_GAME_SELFPLAY_SYNC_INTERVAL='${SYNC_INTERVAL}' && \
    export AFFINE_GAME_SELFPLAY_AUTOTUNE_BATCH='1' && \
    export AFFINE_GAME_SELFPLAY_MAX_ROUNDS='${MAX_ROUNDS}' && \
    export AFFINE_GAME_SELFPLAY_RESUME='1' && \
    export AFFINE_GAME_POLICY_REPO='${AFFINE_GAME_POLICY_REPO:-}' && \
    export HF_TOKEN='${HF_TOKEN:-}' && \
    exec '${PYTHON_BIN}' -u '${PROJECT_ROOT}/scripts/game/targon_game_selfplay_longrun.py' >> '${log_path}' 2>&1
  "
  printf '%s\n' "${session}" > "${pid_path}"

  echo "STARTED ${game} session=${session} gpu=${gpu} out=${output_dir} log=${log_path} cfg=${cfg_path}"
}

status_one() {
  local game="$1"
  local gpu="$2"
  local pid_path output_dir log_path session
  pid_path="$(game_pid_path "${game}")"
  output_dir="$(game_output_dir "${game}")"
  log_path="$(game_log_path "${game}")"
  session="$(game_session_name "${game}")"
  "${PYTHON_BIN}" - <<PY
import json
from pathlib import Path

game = "${game}"
gpu = "${gpu}"
pid_path = Path("${pid_path}")
output_dir = Path("${output_dir}")
log_path = Path("${log_path}")
session = "${session}"
running = False
if pid_path.exists():
    import subprocess
    proc = subprocess.run(
        ["screen", "-ls"],
        capture_output=True,
        text=True,
        check=False,
    )
    running = f".{session}" in proc.stdout

heartbeat_path = output_dir / "heartbeat.json"
status_path = output_dir / "status.json"
payload = {
    "game": game,
    "gpu": gpu,
    "running": running,
    "screen_session": session,
    "output_dir": str(output_dir),
    "log_path": str(log_path),
}
if heartbeat_path.exists():
    heartbeat = json.loads(heartbeat_path.read_text(encoding="utf-8"))
    payload["heartbeat"] = {
        "phase": heartbeat.get("phase"),
        "rows_generated_total": heartbeat.get("rows_generated_total"),
        "rows_consumed_total": heartbeat.get("rows_consumed_total"),
        "replay_states_per_sec": heartbeat.get("replay_states_per_sec"),
        "learner_steps_completed": heartbeat.get("learner_steps_completed"),
        "last_quick_win_rate": heartbeat.get("last_quick_win_rate"),
        "last_teacher_win_rate": heartbeat.get("last_teacher_win_rate"),
        "eval_batch_size": heartbeat.get("eval_batch_size"),
        "eval_queue_depth": heartbeat.get("eval_queue_depth"),
        "eval_batches_per_sec": heartbeat.get("eval_batches_per_sec"),
        "checkpoint_version": heartbeat.get("checkpoint_version"),
        "gpu_util_avg_5m": heartbeat.get("gpu_util_avg_5m"),
        "gpu_mem_avg_5m": heartbeat.get("gpu_mem_avg_5m"),
        "updated_at": heartbeat.get("updated_at"),
    }
if status_path.exists():
    status = json.loads(status_path.read_text(encoding="utf-8"))
    payload["status"] = {
        "learner_updates": status.get("learner_updates"),
        "learner_steps_completed": status.get("learner_steps_completed"),
        "train_epochs": status.get("train_epochs"),
        "replay_rows": status.get("replay_rows"),
        "phase_replay_rows": status.get("phase_replay_rows"),
        "last_quick_win_rate": status.get("last_quick_win_rate"),
        "last_cheap_teacher_win_rate": status.get("last_cheap_teacher_win_rate"),
        "last_teacher_win_rate": status.get("last_teacher_win_rate"),
        "teacher_pass_streak": status.get("teacher_pass_streak"),
        "full_teacher_games_played": status.get("full_teacher_games_played"),
        "evaluator_version": status.get("evaluator_version"),
        "latest_checkpoint": status.get("latest_checkpoint"),
        "best_checkpoint": status.get("best_checkpoint"),
        "autotuned_batch_size": status.get("autotuned_batch_size"),
        "updated_at": status.get("updated_at"),
    }
print(json.dumps(payload, ensure_ascii=False))
PY
}

stop_one() {
  local game="$1"
  local pid_path session
  pid_path="$(game_pid_path "${game}")"
  session="$(game_session_name "${game}")"
  if ! [[ -f "${pid_path}" ]]; then
    echo "NOT_FOUND ${game}"
    return 0
  fi
  if is_running "${session}"; then
    screen -S "${session}" -X quit
    echo "STOPPED ${game} session=${session}"
  else
    echo "STALE ${game} session=${session}"
  fi
  rm -f "${pid_path}"
}

tail_one() {
  local game="$1"
  tail -n "${TAIL_LINES:-80}" "$(game_log_path "${game}")"
}

cmd="${1:-launch}"
case "${cmd}" in
  launch)
    for idx in "${!GAMES[@]}"; do
      launch_one "${GAMES[$idx]}" "${GPUS[$idx]}"
    done
    ;;
  status)
    for idx in "${!GAMES[@]}"; do
      status_one "${GAMES[$idx]}" "${GPUS[$idx]}"
    done
    ;;
  stop)
    for idx in "${!GAMES[@]}"; do
      stop_one "${GAMES[$idx]}"
    done
    ;;
  tail)
    game="${2:?usage: $0 tail <game>}"
    tail_one "${game}"
    ;;
  *)
    echo "usage: $0 {launch|status|stop|tail <game>}" >&2
    exit 1
    ;;
esac
