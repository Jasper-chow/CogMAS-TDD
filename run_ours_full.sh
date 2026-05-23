#!/usr/bin/env bash
# Run the full "ours" profile on humaneval_plus_full.
# Waits for run_remaining_experiments.sh to finish first (checks for "All profiles completed."
# in the master log), then starts the ours run with a 5s inter-task sleep to avoid
# hitting SiliconFlow API rate limits.

set -euo pipefail

MASTER_LOG="results/experiment_logs/sequential_runner_master.log"
MANIFEST="benchmark_manifests/humaneval_plus_full.json"
TIMEOUT=1800      # 30 min per task — ours has many LLM calls (green+LDB+L2+L3+eval+CR)
SLEEP_BETWEEN=5   # seconds between tasks to stay well under rate limits
LOG_DIR="results/experiment_logs"
PYTHON="F:/LLM/LLM_learning/.venv/Scripts/python.exe"

echo "Waiting for remaining experiments to finish..."
echo "(polling $MASTER_LOG for 'All profiles completed.')"

while ! grep -q "All profiles completed." "$MASTER_LOG" 2>/dev/null; do
  sleep 30
done

echo "========================================================"
echo "All prior profiles done. Starting full ours run at $(date)"
echo "========================================================"

TS=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/${TS}__ours_full.log"
mkdir -p "$LOG_DIR"

PYTHONUNBUFFERED=1 PYTHONPATH="F:/LLM/LLM_learning/lib_stubs" "$PYTHON" -u run_benchmark.py \
  --manifest-path "$MANIFEST" \
  --profile "ours" \
  --per-task-timeout "$TIMEOUT" \
  --inter-task-sleep "$SLEEP_BETWEEN" \
  --print-each \
  2>&1 | tee "$LOG_FILE"

echo "========================================================"
echo "ours full run completed at $(date)"
echo "========================================================"
