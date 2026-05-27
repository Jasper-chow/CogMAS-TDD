#!/usr/bin/env python3
"""
Generate a BigCodeBench manifest filtered by cyclomatic complexity.

Usage:
    python create_bigcodebench_manifest.py
    python create_bigcodebench_manifest.py --min-cc 3 --max-tasks 150 --out benchmark_manifests/bigcodebench_complex.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def compute_cc(code: str) -> float:
    """Return mean cyclomatic complexity of all functions in code, or 0 on error."""
    if not code.strip():
        return 0.0
    try:
        from radon.complexity import cc_visit
        blocks = cc_visit(code)
        if not blocks:
            return 1.0
        return sum(b.complexity for b in blocks) / len(blocks)
    except Exception:
        return 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="v0.1.2")
    parser.add_argument("--min-cc", type=float, default=3.0,
                        help="Minimum mean CC of canonical solution to include task")
    parser.add_argument("--max-tasks", type=int, default=150,
                        help="Maximum number of tasks in the manifest")
    parser.add_argument("--out", default="benchmark_manifests/bigcodebench_complex.json")
    args = parser.parse_args()

    print(f"Loading BigCodeBench split={args.split} ...")
    from datasets import load_dataset  # type: ignore[import]
    ds = load_dataset("bigcode/bigcodebench", split=args.split)
    print(f"Total tasks: {len(ds)}")

    selected: list[dict] = []
    cc_dist: dict[str, int] = {"<2": 0, "2-3": 0, "3-5": 0, "5+": 0}
    for item in ds:
        # Reconstruct full canonical code = complete_prompt + canonical_solution
        full_code = item["complete_prompt"] + item["canonical_solution"]
        cc = compute_cc(full_code)

        if cc < 2:
            cc_dist["<2"] += 1
        elif cc < 3:
            cc_dist["2-3"] += 1
        elif cc < 5:
            cc_dist["3-5"] += 1
        else:
            cc_dist["5+"] += 1

        if cc >= args.min_cc:
            selected.append({
                "task_id": item["task_id"],
                "_cc": round(cc, 2),
                "_libs": item.get("libs", []),
            })

    print(f"\nCC distribution across all {len(ds)} tasks:")
    for bucket, count in cc_dist.items():
        print(f"  CC {bucket}: {count} tasks")
    print(f"\nTasks with CC >= {args.min_cc}: {len(selected)}")

    # Sort by CC descending, then cap at max_tasks
    selected.sort(key=lambda x: x["_cc"], reverse=True)
    selected = selected[: args.max_tasks]

    manifest_items = [{"task_id": t["task_id"]} for t in selected]
    manifest = {
        "name": f"bigcodebench_complex_{args.min_cc}cc",
        "description": (
            f"BigCodeBench tasks with mean CC >= {args.min_cc} in canonical solution "
            f"({len(manifest_items)} tasks, sorted by complexity desc)"
        ),
        "default_dataset": "bigcodebench",
        "items": manifest_items,
        "metadata": {
            "min_cc": args.min_cc,
            "max_tasks": args.max_tasks,
            "split": args.split,
            "top_cc": selected[0]["_cc"] if selected else None,
            "median_cc": selected[len(selected) // 2]["_cc"] if selected else None,
        },
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nManifest saved to {out_path}")
    print(f"Tasks selected: {len(manifest_items)}")
    if selected:
        print(f"CC range: {selected[-1]['_cc']} – {selected[0]['_cc']}")


if __name__ == "__main__":
    main()
