#!/usr/bin/env bash
# Re-run ours + ablation_no_l2l3 + ablation_no_eval after the static_verdict gate fix.
# b0/b2/b_cr_only/ablation_no_cr are unaffected (they don't use evaluation_node).

set -euo pipefail

MANIFEST="benchmark_manifests/humaneval_plus_full.json"
TIMEOUT=1800
SLEEP_BETWEEN=5
LOG_DIR="results/experiment_logs"
mkdir -p "$LOG_DIR"
PYTHON="F:/LLM/LLM_learning/.venv/Scripts/python.exe"

PROFILES=(
  "ours"
  "ablation_no_l2l3"
  "ablation_no_eval"
)

for PROFILE in "${PROFILES[@]}"; do
  TS=$(date +%Y%m%d_%H%M%S)
  LOG_FILE="$LOG_DIR/${TS}__rerun_${PROFILE}.log"
  echo "========================================================"
  echo "Starting: $PROFILE  ($(date))"
  echo "Log: $LOG_FILE"
  echo "========================================================"

  PYTHONUNBUFFERED=1 PYTHONPATH="F:/LLM/LLM_learning/lib_stubs" "$PYTHON" -u run_benchmark.py \
    --manifest-path "$MANIFEST" \
    --profile "$PROFILE" \
    --per-task-timeout "$TIMEOUT" \
    --inter-task-sleep "$SLEEP_BETWEEN" \
    --print-each \
    2>&1 | tee "$LOG_FILE"

  echo "Finished: $PROFILE  ($(date))"
  echo ""
done

echo "All re-runs completed."
