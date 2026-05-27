#!/usr/bin/env bash
set -euo pipefail

MANIFEST="benchmark_manifests/humaneval_plus_full.json"
TIMEOUT=1800
SLEEP=5
LOG_DIR="results/experiment_logs"
PYTHON="F:/LLM/LLM_learning/.venv/Scripts/python.exe"

mkdir -p "$LOG_DIR"

run_profile() {
  local PROFILE="$1"
  TS=$(date +%Y%m%d_%H%M%S)
  LOG="$LOG_DIR/${TS}__${PROFILE}__new_metrics.log"
  echo "========================================================"
  echo "Starting: $PROFILE  ($(date))"
  echo "Log: $LOG"
  echo "========================================================"
  PYTHONUNBUFFERED=1 PYTHONPATH="F:/LLM/LLM_learning/lib_stubs" \
    "$PYTHON" -u run_benchmark.py \
    --manifest-path "$MANIFEST" \
    --profile "$PROFILE" \
    --per-task-timeout "$TIMEOUT" \
    --inter-task-sleep "$SLEEP" \
    --print-each \
    2>&1 | tee "$LOG"
  echo "Finished: $PROFILE  ($(date))"
  echo ""
}

run_profile "b2_error_feedback"
run_profile "ours"

echo "Comparison runs completed at $(date)"
