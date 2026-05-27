#!/usr/bin/env python3
"""Before/after quality comparison for ours_from_ref experiment.

Before  = BigCodeBench canonical solutions (reference_code, human-written, CC 8-14).
After   = pipeline output after CR → L2 → L3 → Eval on the same code.

This gives a noise-free paired comparison: same starting code, deterministic baseline,
showing the framework's direct causal effect on code with real structural complexity.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import mean, stdev
from typing import Any

REF_QUALITY_PATH = Path("results/ref_quality_bigcodebench.json")
# Updated by run; use most recent ours_from_ref run directory
RUNS_ROOT = Path("results/runs/bigcodebench/ours_from_ref")

METRICS = [
    ("cc_mean", "CC Mean", "lower better"),
    ("cc_max", "CC Max", "lower better"),
    ("cognitive_complexity", "Cognitive CC", "lower better"),
    ("mi_score", "Maintainability Index", "higher better"),
    ("loc", "LOC", "lower better"),
]


def load_ref_quality() -> dict[str, dict[str, Any]]:
    data = json.loads(REF_QUALITY_PATH.read_text(encoding="utf-8"))
    return {item["task_id"]: item for item in data}


def find_latest_run() -> Path | None:
    if not RUNS_ROOT.exists():
        return None
    runs = sorted(RUNS_ROOT.iterdir(), reverse=True)
    for run_dir in runs:
        records = run_dir / "records.jsonl"
        if records.exists():
            return records
    return None


def load_records(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "mean": float("nan"), "std": float("nan")}
    n = len(values)
    m = mean(values)
    s = stdev(values) if n > 1 else 0.0
    return {"n": n, "mean": round(m, 3), "std": round(s, 3)}


def main(records_path: str | None = None) -> None:
    ref = load_ref_quality()
    if records_path:
        records_file = Path(records_path)
    else:
        records_file = find_latest_run()
    if not records_file or not records_file.exists():
        print(f"No ours_from_ref records found under {RUNS_ROOT}. Run the experiment first.")
        sys.exit(1)
    print(f"Loading run records: {records_file}")
    records = load_records(records_file)

    passed = [r for r in records if r.get("test_passed")]
    refactored = [r for r in passed if r.get("has_l3_refactor") or r.get("has_l2_refactor")]

    print(f"\nRun summary:")
    print(f"  Total tasks:      {len(records)}")
    print(f"  Passed tests:     {len(passed)}/{len(records)}")
    print(f"  L2/L3 refactored: {len(refactored)}/{len(passed)}")
    print()

    # --- Paired before/after on ALL passed tasks ---
    matched = [r for r in passed if r["task_id"] in ref]
    print(f"Tasks with both before & after metrics: {len(matched)}")
    print()

    print(f"{'Metric':<25} {'Before':>10} {'After':>10} {'Delta':>10} {'Pct':>8}  Direction")
    print("-" * 80)
    for key, label, direction in METRICS:
        before_vals = [ref[r["task_id"]][key] for r in matched if ref[r["task_id"]].get(key) is not None]
        after_vals  = [r[key] for r in matched if r.get(key) is not None]
        if len(before_vals) != len(after_vals):
            print(f"{label:<25} data mismatch (before:{len(before_vals)} after:{len(after_vals)})")
            continue
        b = stats(before_vals)
        a = stats(after_vals)
        if b["n"] > 0 and a["n"] > 0:
            delta = a["mean"] - b["mean"]
            pct = (delta / b["mean"] * 100) if b["mean"] != 0 else 0.0
            sign = "+" if delta > 0 else ""
            improved = (delta < 0) if "lower" in direction else (delta > 0)
            marker = "OK" if improved else ("WORSE" if abs(pct) > 0.5 else "~")
            print(
                f"{label:<25} {b['mean']:>10.2f} {a['mean']:>10.2f} "
                f"{sign}{delta:>9.3f} {sign}{pct:>6.1f}%  {marker} {direction}"
            )

    print()
    # --- Zoomed in: only tasks where L2/L3 actually changed code ---
    refactored_ids = {r["task_id"] for r in refactored}
    matched_refactored = [r for r in matched if r["task_id"] in refactored_ids]
    if matched_refactored:
        print(f"Metrics on {len(matched_refactored)} tasks where L2/L3 refactored:")
        print(f"{'Metric':<25} {'Before':>10} {'After':>10} {'Delta':>10} {'Pct':>8}  Direction")
        print("-" * 80)
        for key, label, direction in METRICS:
            before_vals = [ref[r["task_id"]][key] for r in matched_refactored if ref[r["task_id"]].get(key) is not None]
            after_vals  = [r[key] for r in matched_refactored if r.get(key) is not None]
            if not before_vals or len(before_vals) != len(after_vals):
                continue
            b = stats(before_vals)
            a = stats(after_vals)
            delta = a["mean"] - b["mean"]
            pct = (delta / b["mean"] * 100) if b["mean"] != 0 else 0.0
            sign = "+" if delta > 0 else ""
            improved = (delta < 0) if "lower" in direction else (delta > 0)
            marker = "OK" if improved else ("WORSE" if abs(pct) > 0.5 else "~")
            print(
                f"{label:<25} {b['mean']:>10.2f} {a['mean']:>10.2f} "
                f"{sign}{delta:>9.3f} {sign}{pct:>6.1f}%  {marker} {direction}"
            )

    # --- Per-task detail for refactored tasks ---
    if matched_refactored:
        print()
        print("Per-task detail (refactored tasks):")
        print(f"  {'task_id':<25} {'cc_mean_b':>9} {'cc_mean_a':>9} {'cog_b':>6} {'cog_a':>6} {'mi_b':>7} {'mi_a':>7}")
        for r in sorted(matched_refactored, key=lambda x: ref[x["task_id"]].get("cc_mean", 0), reverse=True):
            tid = r["task_id"].replace("BigCodeBench/", "BCB/")
            rv = ref[r["task_id"]]
            print(
                f"  {tid:<25} {rv.get('cc_mean', '?'):>9.1f} {r.get('cc_mean', '?'):>9.1f} "
                f"{rv.get('cognitive_complexity', '?'):>6.1f} {r.get('cognitive_complexity', '?'):>6.1f} "
                f"{rv.get('mi_score', '?'):>7.1f} {r.get('mi_score', '?'):>7.1f}"
            )


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    main(arg)
