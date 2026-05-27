#!/usr/bin/env python3
"""Compare b2 vs ours on BigCodeBench quality metrics."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import mean, stdev
from typing import Any


B2_RECORDS_PATH = Path(
    "results/runs/bigcodebench/b2_error_feedback"
    "/20260526_234250__b2_error_feedback__bigcodebench__bigcodebench_complex_3.0cc"
    "/records.jsonl"
)
# Full 150-task ours run (fixed CISQ rules + L3 guards, post-20260527_025849)
OURS_FULL_PATH = Path(
    "results/runs/bigcodebench/ours"
    "/20260527_025849__ours__bigcodebench__bigcodebench_complex_3.0cc"
    "/records.jsonl"
)
# Older partial runs kept for fallback
OURS_CRASHED_PATH = Path(
    "results/runs/bigcodebench/ours"
    "/20260527_014209__ours__bigcodebench__bigcodebench_complex_3.0cc"
    "/records.jsonl"
)
OURS_RESUMED_PATH = Path(
    "results/runs/bigcodebench/ours"
    "/20260527_021029__ours__bigcodebench__bigcodebench_complex_3.0cc"
    "/records.jsonl"
)

METRICS = [
    ("cc_mean", "CC Mean", "lower better"),
    ("cc_max", "CC Max", "lower better"),
    ("cognitive_complexity", "Cognitive CC", "lower better"),
    ("mi_score", "Maintainability Index", "higher better"),
    ("loc", "LOC", "lower better"),
    ("pylint_score", "Pylint Score", "higher better"),
    ("bandit_issues", "Bandit Issues", "lower better"),
]


def load_records(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def collect_ours_records() -> list[dict[str, Any]]:
    """Load full 150-task ours run; fall back to merging crashed+resumed partial runs."""
    if OURS_FULL_PATH.exists():
        return load_records(OURS_FULL_PATH)
    # Fallback: merge crashed (19) + resumed (28) records, dedup by task_id
    records: dict[str, dict[str, Any]] = {}
    if OURS_CRASHED_PATH.exists():
        for r in load_records(OURS_CRASHED_PATH):
            records[r["task_id"]] = r
    if OURS_RESUMED_PATH.exists():
        for r in load_records(OURS_RESUMED_PATH):
            records[r["task_id"]] = r
    return list(records.values())


def stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"n": 0, "mean": float("nan"), "std": float("nan")}
    n = len(values)
    m = mean(values)
    s = stdev(values) if n > 1 else 0.0
    return {"n": n, "mean": round(m, 3), "std": round(s, 3)}


def main() -> None:
    b2_all = load_records(B2_RECORDS_PATH)
    ours_all = collect_ours_records()

    b2_passed = {r["task_id"]: r for r in b2_all if r.get("test_passed")}
    ours_by_id = {r["task_id"]: r for r in ours_all}

    # Tasks where b2 passed and ours also ran
    common_ids = set(b2_passed.keys()) & set(ours_by_id.keys())
    ours_passed_ids = {tid for tid in common_ids if ours_by_id[tid].get("test_passed")}

    print(f"B2 passed tasks: {len(b2_passed)}")
    print(f"Ours tasks processed: {len(ours_by_id)}")
    print(f"Common tasks (b2 passed & ours ran): {len(common_ids)}")
    print(f"Ours passed among common: {len(ours_passed_ids)}")
    l3_ran = sum(1 for tid in common_ids if ours_by_id[tid].get('has_l3_refactor'))
    l3_passed = sum(1 for tid in common_ids if ours_by_id[tid].get('has_l3_refactor') and ours_by_id[tid].get('test_passed'))
    green_failed = sum(1 for tid in common_ids if not ours_by_id[tid].get('test_passed') and not ours_by_id[tid].get('has_l3_refactor'))
    print(f"Ours has_l3_refactor (pipeline ran): {l3_ran}")
    print(f"Ours passed when L2/L3 ran: {l3_passed}/{l3_ran} (pipeline correctness retention)")
    print(f"Green node failures before CR (LLM variance): {green_failed}")
    print()

    # Compare on common tasks where BOTH passed (fair comparison)
    both_passed = {tid for tid in common_ids if ours_by_id[tid].get("test_passed")}
    print(f"Tasks where both b2 and ours passed: {len(both_passed)}")
    print()

    print(f"{'Metric':<25} {'B2 mean':>10} {'Ours mean':>10} {'Delta':>10} {'Pct':>8}  Direction")
    print("-" * 85)
    for key, label, direction in METRICS:
        b2_vals = [b2_passed[tid][key] for tid in both_passed if b2_passed[tid].get(key) is not None]
        ours_vals = [ours_by_id[tid][key] for tid in both_passed if ours_by_id[tid].get(key) is not None]
        b2_s = stats(b2_vals)
        ours_s = stats(ours_vals)
        if b2_s["n"] > 0 and ours_s["n"] > 0:
            delta = ours_s["mean"] - b2_s["mean"]
            pct = (delta / b2_s["mean"] * 100) if b2_s["mean"] != 0 else 0.0
            sign = "+" if delta > 0 else ""
            improved = (delta < 0) if "lower" in direction else (delta > 0)
            marker = "OK" if improved else ("WORSE" if abs(delta) > 0.01 else "~")
            print(
                f"{label:<25} {b2_s['mean']:>10.2f} {ours_s['mean']:>10.2f} "
                f"{sign}{delta:>9.3f} {sign}{pct:>6.1f}%  {marker} {direction}"
            )
        else:
            print(f"{label:<25} n/a (b2:{b2_s['n']} ours:{ours_s['n']})")

    print()
    # Pass rate
    b2_pass_rate = len(b2_passed) / len(b2_all) if b2_all else 0
    # Ours total should include both passed and failed, but we only ran on b2-passing subset
    ours_subset_pass = len(ours_passed_ids)
    ours_subset_total = len(common_ids)
    print(f"Pass rate - B2: {len(b2_passed)}/{len(b2_all)} = {b2_pass_rate:.1%}")
    print(f"Pass rate - Ours on b2-passing subset: {ours_subset_pass}/{ours_subset_total} = {ours_subset_pass/ours_subset_total:.1%}")
    pipeline_ran = sum(1 for tid in common_ids if ours_by_id[tid].get('has_l3_refactor'))
    pipeline_pass = sum(1 for tid in common_ids if ours_by_id[tid].get('has_l3_refactor') and ours_by_id[tid].get('test_passed'))
    if pipeline_ran:
        print(f"  Pipeline correctness (L2/L3 ran): {pipeline_pass}/{pipeline_ran} = {pipeline_pass/pipeline_ran:.1%}")
    green_fail_count = ours_subset_total - pipeline_ran
    print(f"  Green node failures (LLM variance, not L2/L3): {green_fail_count}")

    # Cost
    b2_cost = [r for r in b2_all if r["task_id"] in both_passed]
    ours_cost = [ours_by_id[tid] for tid in both_passed]
    if b2_cost and ours_cost:
        b2_tokens = mean(r.get("total_tokens", 0) for r in b2_cost)
        ours_tokens = mean(r.get("total_tokens", 0) for r in ours_cost)
        b2_calls = mean(r.get("llm_calls", 0) for r in b2_cost)
        ours_calls = mean(r.get("llm_calls", 0) for r in ours_cost)
        print()
        print(f"Cost comparison (both-passed tasks, n={len(both_passed)}):")
        print(f"  Avg tokens - B2: {b2_tokens:.0f}, Ours: {ours_tokens:.0f} (+{(ours_tokens/b2_tokens - 1)*100:.0f}%)")
        print(f"  Avg LLM calls - B2: {b2_calls:.1f}, Ours: {ours_calls:.1f} (+{(ours_calls/b2_calls - 1)*100:.0f}%)")


if __name__ == "__main__":
    main()
