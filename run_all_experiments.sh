#!/usr/bin/env bash
# Full experiment suite for CogMAS-TDD paper (CC/MI metrics version).
# All profiles run on humaneval_plus_full (164 tasks).
#
# NOTE: b2_error_feedback run 1 was started separately and is already running.
# This script runs the remaining 17 runs (b2×2 more, then the rest as planned).
#
# Run order (per paper strategy priority):
#   b2_error_feedback × 2     (run 1 already in progress — total will be 3)
#   b_cr_only × 3             CR diagnoses but no fix
#   ablation_no_l2l3 × 3      L2/L3 mechanism ablation
#   ours × 3                  full pipeline
#   b0_direct_generation × 2  single-shot baseline
#   ablation_no_cr × 2        CR necessity ablation
#   ablation_no_eval × 2      Eval necessity ablation
#
# Total: 17 runs × 164 tasks

set -euo pipefail

MANIFEST="benchmark_manifests/humaneval_plus_full.json"
TIMEOUT=1800
SLEEP_BETWEEN=5
LOG_DIR="results/experiment_logs"
PYTHON="F:/LLM/LLM_learning/.venv/Scripts/python.exe"

mkdir -p "$LOG_DIR"

run_profile() {
  local PROFILE="$1"
  local RUN_IDX="$2"
  local TOTAL="$3"

  TS=$(date +%Y%m%d_%H%M%S)
  LOG_FILE="$LOG_DIR/${TS}__${PROFILE}__run${RUN_IDX}.log"

  echo "========================================================"
  echo "[$RUN_IDX/$TOTAL] Profile: $PROFILE  ($(date))"
  echo "Log: $LOG_FILE"
  echo "========================================================"

  PYTHONUNBUFFERED=1 PYTHONPATH="F:/LLM/LLM_learning/lib_stubs" \
    "$PYTHON" -u run_benchmark.py \
    --manifest-path "$MANIFEST" \
    --profile "$PROFILE" \
    --per-task-timeout "$TIMEOUT" \
    --inter-task-sleep "$SLEEP_BETWEEN" \
    --print-each \
    2>&1 | tee "$LOG_FILE"

  echo "Finished: $PROFILE run $RUN_IDX  ($(date))"
  echo ""
}

TOTAL_RUNS=17
IDX=0

# ── Priority 1: b2_error_feedback × 2 more (run 1 already in progress) ───────
for i in 1 2; do
  IDX=$((IDX + 1))
  run_profile "b2_error_feedback" "$IDX" "$TOTAL_RUNS"
done

# ── Priority 2: b_cr_only × 3 ────────────────────────────────────────────────
for i in 1 2 3; do
  IDX=$((IDX + 1))
  run_profile "b_cr_only" "$IDX" "$TOTAL_RUNS"
done

# ── Priority 3: ablation_no_l2l3 × 3 ─────────────────────────────────────────
for i in 1 2 3; do
  IDX=$((IDX + 1))
  run_profile "ablation_no_l2l3" "$IDX" "$TOTAL_RUNS"
done

# ── Priority 4: ours × 3 ─────────────────────────────────────────────────────
for i in 1 2 3; do
  IDX=$((IDX + 1))
  run_profile "ours" "$IDX" "$TOTAL_RUNS"
done

# ── Priority 5: b0_direct_generation × 2 ─────────────────────────────────────
for i in 1 2; do
  IDX=$((IDX + 1))
  run_profile "b0_direct_generation" "$IDX" "$TOTAL_RUNS"
done

# ── Priority 6: ablation_no_cr × 2 ───────────────────────────────────────────
for i in 1 2; do
  IDX=$((IDX + 1))
  run_profile "ablation_no_cr" "$IDX" "$TOTAL_RUNS"
done

# ── Priority 7: ablation_no_eval × 2 ─────────────────────────────────────────
for i in 1 2; do
  IDX=$((IDX + 1))
  run_profile "ablation_no_eval" "$IDX" "$TOTAL_RUNS"
done

echo "========================================================"
echo "All $TOTAL_RUNS scheduled runs completed at $(date)"
echo "========================================================"
