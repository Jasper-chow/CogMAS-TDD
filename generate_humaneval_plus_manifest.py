from __future__ import annotations

"""
Generate benchmark manifests for HumanEval+ (EvalPlus).

Outputs:
  benchmark_manifests/humaneval_plus_full.json   — all 164 tasks
  benchmark_manifests/humaneval_plus_20.json     — first 20 tasks (quick smoke / dev run)

Requires: uv add evalplus
"""

import json
from pathlib import Path

try:
    from evalplus.data import get_human_eval_plus
except ImportError:
    raise SystemExit("evalplus not installed. Run: uv add evalplus")


def _sort_key(task_id: str) -> int:
    try:
        return int(task_id.split("/")[-1])
    except ValueError:
        return 0


def _make_manifest(name: str, description: str, task_ids: list[str]) -> dict:
    return {
        "name": name,
        "description": description,
        "default_dataset": "humaneval_plus",
        "items": [{"task_id": tid} for tid in task_ids],
        "metadata": {
            "dataset": "humaneval_plus",
            "source": "evalplus",
            "task_count": len(task_ids),
        },
    }


def main() -> None:
    problems = get_human_eval_plus()
    all_ids = sorted(problems.keys(), key=_sort_key)
    print(f"Loaded {len(all_ids)} HumanEval+ tasks from evalplus.")

    manifest_dir = Path("benchmark_manifests")
    manifest_dir.mkdir(exist_ok=True)

    full = _make_manifest(
        "humaneval_plus_full",
        "All 164 HumanEval+ tasks (EvalPlus augmented)",
        all_ids,
    )
    full_path = manifest_dir / "humaneval_plus_full.json"
    full_path.write_text(json.dumps(full, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Written: {full_path}  ({len(all_ids)} tasks)")

    subset_20 = _make_manifest(
        "humaneval_plus_20",
        "First 20 HumanEval+ tasks — dev/smoke run",
        all_ids[:20],
    )
    sub_path = manifest_dir / "humaneval_plus_20.json"
    sub_path.write_text(json.dumps(subset_20, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Written: {sub_path}  (20 tasks)")


if __name__ == "__main__":
    main()
