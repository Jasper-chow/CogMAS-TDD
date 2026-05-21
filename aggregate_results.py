from __future__ import annotations

"""
实验结果聚合脚本。

目标：
- 读取一个或多个实验 JSONL 结果文件；
- 产出统一 JSON 汇总，便于做 baseline / ablation 对比；
- 支持按 profile、dataset、profile+dataset 等维度做分组统计。
"""

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_EXPERIMENTS_DIR = PROJECT_ROOT / "results" / "experiments"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate CogMAS-TDD experiment JSONL results")
    parser.add_argument(
        "--inputs",
        nargs="*",
        default=[],
        help="Explicit JSONL files or glob patterns. If omitted, scan --input-dir with --glob.",
    )
    parser.add_argument(
        "--input-dir",
        default=str(DEFAULT_EXPERIMENTS_DIR),
        help="Directory used when --inputs is omitted.",
    )
    parser.add_argument(
        "--glob",
        default="*.jsonl",
        help="Glob pattern under --input-dir when --inputs is omitted.",
    )
    parser.add_argument(
        "--group-by",
        choices=["none", "profile", "dataset", "profile_dataset", "file"],
        default="profile_dataset",
    )
    parser.add_argument("--profile", default="", help="Optional profile_name filter.")
    parser.add_argument("--dataset", default="", help="Optional dataset_name filter.")
    parser.add_argument("--output-path", default="", help="Optional output JSON path.")
    parser.add_argument("--print-record-count", action="store_true")
    return parser.parse_args()


def _resolve_input_paths(args: argparse.Namespace) -> list[Path]:
    paths: list[Path] = []

    if args.inputs:
        for raw_input in args.inputs:
            candidate = Path(raw_input)
            if candidate.exists():
                paths.append(candidate.resolve())
                continue

            matched = sorted(PROJECT_ROOT.glob(raw_input))
            if matched:
                paths.extend(path.resolve() for path in matched if path.is_file())
                continue

            raise FileNotFoundError(f"input not found: {raw_input}")
    else:
        input_dir = Path(args.input_dir)
        if not input_dir.exists():
            raise FileNotFoundError(f"input directory not found: {input_dir}")
        paths = sorted(path.resolve() for path in input_dir.glob(args.glob) if path.is_file())

    unique_paths: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique_paths.append(path)
    return unique_paths


def _load_jsonl_records(paths: list[Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in paths:
        with path.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                payload = json.loads(stripped)
                if not isinstance(payload, dict):
                    raise ValueError(f"record in {path}:{line_number} is not a JSON object")
                payload["_source_file"] = str(path)
                payload["_source_name"] = path.name
                records.append(payload)
    return records


def _filter_records(
    records: list[dict[str, Any]],
    *,
    profile: str = "",
    dataset: str = "",
) -> list[dict[str, Any]]:
    filtered = records
    if profile:
        filtered = [record for record in filtered if str(record.get("profile_name", "")) == profile]
    if dataset:
        filtered = [record for record in filtered if str(record.get("dataset_name", "")) == dataset]
    return filtered


def _safe_mean(values: list[int | float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _ratio(records: list[dict[str, Any]], key: str, expected: Any) -> float:
    if not records:
        return 0.0
    matched = sum(1 for record in records if record.get(key) == expected)
    return matched / len(records)


def _nullable_ratio(records: list[dict[str, Any]], key: str) -> dict[str, float | int]:
    non_null_values = [record.get(key) for record in records if record.get(key) is not None]
    if not non_null_values:
        return {"coverage": 0.0, "pass_rate": 0.0, "count": 0}
    passed = sum(1 for value in non_null_values if value is True)
    total = len(non_null_values)
    return {
        "coverage": total / len(records) if records else 0.0,
        "pass_rate": passed / total if total else 0.0,
        "count": total,
    }


def _distribution(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    counter = Counter(str(record.get(key, "")) for record in records)
    return dict(sorted(counter.items(), key=lambda item: item[0]))


def _task_ids(records: list[dict[str, Any]]) -> list[str]:
    task_ids = {str(record.get("task_id", "")).strip() for record in records if str(record.get("task_id", "")).strip()}
    return sorted(task_ids)


def _group_key(record: dict[str, Any], group_by: str) -> str:
    if group_by == "profile":
        return str(record.get("profile_name", ""))
    if group_by == "dataset":
        return str(record.get("dataset_name", ""))
    if group_by == "profile_dataset":
        profile = str(record.get("profile_name", ""))
        dataset = str(record.get("dataset_name", ""))
        return f"{profile}::{dataset}"
    if group_by == "file":
        return str(record.get("_source_name", ""))
    return "all"


def _summarize_records(records: list[dict[str, Any]], *, label: str) -> dict[str, Any]:
    total_runs = len(records)
    green_attempts = [int(record.get("green_attempts", 0) or 0) for record in records]
    same_error_streaks = [int(record.get("same_error_streak", 0) or 0) for record in records]
    iterations = [int(record.get("iteration", 0) or 0) for record in records]
    failed_rule_counts = [len(record.get("failed_rule_ids", []) or []) for record in records]
    activated_rule_counts = [len(record.get("activated_rule_ids", []) or []) for record in records]

    return {
        "label": label,
        "total_runs": total_runs,
        "unique_tasks": len(_task_ids(records)),
        "task_ids": _task_ids(records),
        "profiles": sorted({str(record.get("profile_name", "")) for record in records if record.get("profile_name", "")}),
        "datasets": sorted({str(record.get("dataset_name", "")) for record in records if record.get("dataset_name", "")}),
        "source_files": sorted(
            {str(record.get("_source_file", "")) for record in records if record.get("_source_file", "")}
        ),
        "workflow_success_rate": _ratio(records, "workflow_status", "success"),
        "test_pass_rate": _ratio(records, "test_passed", True),
        "evaluation_pass_rate": _ratio(records, "final_verdict", "pass"),
        "avg_green_attempts": _safe_mean(green_attempts),
        "avg_same_error_streak": _safe_mean(same_error_streaks),
        "avg_iteration": _safe_mean(iterations),
        "avg_failed_rule_count": _safe_mean(failed_rule_counts),
        "avg_activated_rule_count": _safe_mean(activated_rule_counts),
        "weak_equivalence": _nullable_ratio(records, "weak_passed"),
        "strong_equivalence": _nullable_ratio(records, "strong_passed"),
        "semantic_equivalence": _nullable_ratio(records, "is_equivalent"),
        "l2_refactor_rate": _ratio(records, "has_l2_refactor", True),
        "l3_refactor_rate": _ratio(records, "has_l3_refactor", True),
        "workflow_status_distribution": _distribution(records, "workflow_status"),
        "stop_reason_distribution": _distribution(records, "stop_reason"),
        "final_verdict_distribution": _distribution(records, "final_verdict"),
        "dynamic_verdict_distribution": _distribution(records, "dynamic_verdict"),
        "static_verdict_distribution": _distribution(records, "static_verdict"),
    }


def aggregate_records(records: list[dict[str, Any]], *, group_by: str) -> dict[str, Any]:
    overview = _summarize_records(records, label="all")

    groups: dict[str, list[dict[str, Any]]] = {}
    if group_by != "none":
        for record in records:
            key = _group_key(record, group_by)
            groups.setdefault(key, []).append(record)

    group_summaries = {
        key: _summarize_records(group_records, label=key)
        for key, group_records in sorted(groups.items(), key=lambda item: item[0])
    }
    return {
        "overview": overview,
        "group_by": group_by,
        "groups": group_summaries,
    }


def _write_output(payload: dict[str, Any], output_path: str | None) -> None:
    if not output_path:
        return
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    args = _parse_args()
    input_paths = _resolve_input_paths(args)
    if not input_paths:
        raise ValueError("no input files found")

    records = _load_jsonl_records(input_paths)
    filtered_records = _filter_records(records, profile=args.profile, dataset=args.dataset)
    if not filtered_records:
        raise ValueError("no records matched the given filters")

    payload = {
        "input_files": [str(path) for path in input_paths],
        "input_record_count": len(records),
        "filtered_record_count": len(filtered_records),
        "filters": {
            "profile": args.profile,
            "dataset": args.dataset,
        },
        "aggregation": aggregate_records(filtered_records, group_by=args.group_by),
    }
    _write_output(payload, args.output_path)

    if args.print_record_count:
        print(f"loaded={len(records)} filtered={len(filtered_records)}")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
