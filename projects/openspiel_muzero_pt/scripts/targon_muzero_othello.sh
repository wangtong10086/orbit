#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FORGE_BIN="${FORGE_BIN:-$ROOT/.venv-all/bin/forge}"
REMOTE_BASE="${REMOTE_BASE:-/root/project}"
REMOTE_PYTHON="${REMOTE_PYTHON:-python3}"
REMOTE_TIMEOUT_BOOTSTRAP="${REMOTE_TIMEOUT_BOOTSTRAP:-3600}"
REMOTE_TIMEOUT_DEFAULT="${REMOTE_TIMEOUT_DEFAULT:-1800}"
MACHINE=""
STAGE="smoke"
CONFIG=""
INIT=""

usage() {
  cat <<'EOF'
Usage:
  bash scripts/game/targon_muzero_othello.sh --machine <registered-machine> [--stage smoke|full|corpus|label|warmstart|online|eval]

Options:
  --machine   Required. Registered rental machine name from machines.json.
  --stage     smoke|full|corpus|label|warmstart|online|eval
  --config    Override config path relative to repo root.
  --init      Override init checkpoint path on remote machine for online stage.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --machine)
      MACHINE="${2:-}"
      shift 2
      ;;
    --stage)
      STAGE="${2:-}"
      shift 2
      ;;
    --config)
      CONFIG="${2:-}"
      shift 2
      ;;
    --init)
      INIT="${2:-}"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$MACHINE" ]]; then
  echo "--machine is required" >&2
  usage
  exit 2
fi

if [[ ! -x "$FORGE_BIN" ]]; then
  echo "forge binary not found: $FORGE_BIN" >&2
  exit 1
fi

if [[ -z "$CONFIG" ]]; then
  if [[ "$STAGE" == "smoke" ]]; then
    CONFIG="projects/openspiel_muzero_pt/configs/othello_8x8_smoke.yaml"
  else
    CONFIG="projects/openspiel_muzero_pt/configs/othello_8x8.yaml"
  fi
fi

REMOTE_PROJECTS_BASE="$REMOTE_BASE/projects"
REMOTE_PACKAGE_ROOT="$REMOTE_PROJECTS_BASE/openspiel_muzero_pt"
REMOTE_CONFIG="$REMOTE_PACKAGE_ROOT/configs/$(basename "$CONFIG")"
REMOTE_ARTIFACT_ROOT="$REMOTE_BASE/artifacts/openspiel_muzero_pt/othello"
REMOTE_CORPUS="$REMOTE_ARTIFACT_ROOT/state_corpus.jsonl"
REMOTE_EXPERT="$REMOTE_ARTIFACT_ROOT/expert"
REMOTE_WARMSTART="$REMOTE_ARTIFACT_ROOT/warmstart"
REMOTE_ONLINE="$REMOTE_ARTIFACT_ROOT/online"
REMOTE_INIT="${INIT:-$REMOTE_WARMSTART/best.pt}"
REMOTE_EVAL_JSON="$REMOTE_ONLINE/eval_vs_affine_mcts.json"

sync_project() {
  "$FORGE_BIN" remote machine -m "$MACHINE" sync \
    -p projects/__init__.py \
    -p projects/openspiel_muzero_pt \
    -p scripts/game/targon_muzero_othello.sh \
    --remote-base "$REMOTE_BASE"
}

remote_run() {
  local cmd="$1"
  local timeout="${2:-$REMOTE_TIMEOUT_DEFAULT}"
  "$FORGE_BIN" remote machine -m "$MACHINE" exec --timeout "$timeout" "cd $REMOTE_BASE && $cmd"
}

normalize_remote_layout() {
  remote_run "bash -lc 'set -euo pipefail && mkdir -p $REMOTE_PROJECTS_BASE && if [ -d $REMOTE_PROJECTS_BASE/projects/openspiel_muzero_pt ]; then cp -a $REMOTE_PROJECTS_BASE/projects/openspiel_muzero_pt/. $REMOTE_PROJECTS_BASE/openspiel_muzero_pt/ && rm -rf $REMOTE_PROJECTS_BASE/projects; fi && if [ -d $REMOTE_PROJECTS_BASE/openspiel_muzero_pt/openspiel_muzero_pt ]; then cp -a $REMOTE_PROJECTS_BASE/openspiel_muzero_pt/openspiel_muzero_pt/. $REMOTE_PROJECTS_BASE/openspiel_muzero_pt/ && rm -rf $REMOTE_PROJECTS_BASE/openspiel_muzero_pt/openspiel_muzero_pt; fi && test -f $REMOTE_PACKAGE_ROOT/requirements.txt && test -f $REMOTE_CONFIG'" 300
}

bootstrap_env() {
  remote_run "bash -lc 'set -euo pipefail && mkdir -p $REMOTE_ARTIFACT_ROOT && if [ ! -d .venv-muzero ]; then $REMOTE_PYTHON -m venv .venv-muzero; fi && . .venv-muzero/bin/activate && python -m pip install --upgrade pip && python -m pip install numpy PyYAML open_spiel pytest && python -m pip install --force-reinstall torch==2.5.1 && python -m pip install -r $REMOTE_PACKAGE_ROOT/requirements.txt && PYTHONPATH=$REMOTE_BASE python -c \"import torch, pyspiel, numpy; print(torch.__version__); print(torch.cuda.is_available())\"'" "$REMOTE_TIMEOUT_BOOTSTRAP"
}

run_corpus() {
  remote_run "bash -lc 'set -euo pipefail && . .venv-muzero/bin/activate && PYTHONPATH=$REMOTE_BASE python -m projects.openspiel_muzero_pt.pipelines.build_state_corpus --config $REMOTE_CONFIG --output $REMOTE_CORPUS'"
}

run_label() {
  remote_run "bash -lc 'set -euo pipefail && . .venv-muzero/bin/activate && PYTHONPATH=$REMOTE_BASE python -m projects.openspiel_muzero_pt.pipelines.label_with_mcts --config $REMOTE_CONFIG --input $REMOTE_CORPUS --output $REMOTE_EXPERT'"
}

run_warmstart() {
  remote_run "bash -lc 'set -euo pipefail && . .venv-muzero/bin/activate && PYTHONPATH=$REMOTE_BASE python -m projects.openspiel_muzero_pt.pipelines.warmstart --config $REMOTE_CONFIG --expert $REMOTE_EXPERT --out $REMOTE_WARMSTART --device cuda'"
}

run_online() {
  remote_run "bash -lc 'set -euo pipefail && . .venv-muzero/bin/activate && PYTHONPATH=$REMOTE_BASE python -m projects.openspiel_muzero_pt.pipelines.train_online --config $REMOTE_CONFIG --init $REMOTE_INIT --expert $REMOTE_EXPERT --out $REMOTE_ONLINE --device cuda'"
}

run_eval() {
  remote_run "bash -lc 'set -euo pipefail && . .venv-muzero/bin/activate && PYTHONPATH=$REMOTE_BASE python -m projects.openspiel_muzero_pt.pipelines.evaluate_vs_affine_mcts --mode quick --config $REMOTE_CONFIG --checkpoint $REMOTE_ONLINE/best.pt --device cuda --output $REMOTE_EVAL_JSON'"
}

sync_project
normalize_remote_layout
bootstrap_env

case "$STAGE" in
  smoke)
    run_corpus
    run_label
    run_warmstart
    run_online
    run_eval
    ;;
  corpus)
    run_corpus
    ;;
  label)
    run_label
    ;;
  warmstart)
    run_warmstart
    ;;
  online)
    run_online
    ;;
  eval)
    run_eval
    ;;
  full)
    run_corpus
    run_label
    run_warmstart
    run_online
    run_eval
    ;;
  *)
    echo "Unsupported stage: $STAGE" >&2
    exit 2
    ;;
esac

echo "Remote Othello stage completed on machine=$MACHINE stage=$STAGE"
