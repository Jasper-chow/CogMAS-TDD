#!/usr/bin/env bash
# Sequential runner for the 5 remaining experiment profiles on humaneval_plus_full.
# Runs profiles one by one; logs each run's stdout+stderr to a timestamped file.
# Per-task timeout is 900s to give even the heaviest profiles (5-retry b2) room to finish.

set -euo pipefail

MANIFEST="benchmark_manifests/humaneval_plus_full.json"
TIMEOUT=900
LOG_DIR="results/experiment_logs"
mkdir -p "$LOG_DIR"

# Use venv Python directly — uv run is currently broken (hangs on startup).
PYTHON="F:/LLM/LLM_learning/.venv/Scripts/python.exe"

PROFILES=(
  "b2_error_feedback"
  "b_cr_only"
  "ablation_no_cr"
  "ablation_no_l2l3"
  "ablation_no_eval"
)

for PROFILE in "${PROFILES[@]}"; do
  TS=$(date +%Y%m%d_%H%M%S)
  LOG_FILE="$LOG_DIR/${TS}__${PROFILE}.log"
  echo "========================================================"
  echo "Starting profile: $PROFILE  ($(date))"
  echo "Log: $LOG_FILE"
  echo "========================================================"

  PYTHONUNBUFFERED=1 PYTHONPATH="F:/LLM/LLM_learning/lib_stubs" "$PYTHON" -u run_benchmark.py \
    --manifest-path "$MANIFEST" \
    --profile "$PROFILE" \
    --per-task-timeout "$TIMEOUT" \
    --print-each \
    2>&1 | tee "$LOG_FILE"

  echo "Finished profile: $PROFILE  ($(date))"
  echo ""
done

echo "All profiles completed."
