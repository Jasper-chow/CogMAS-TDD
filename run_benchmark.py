from __future__ import annotations

"""
最小实验批跑入口。

当前目标：
- 让 MBPP / HumanEval 可以直接接入当前实验框架；
- 支持 baseline / ablation / ours 的小规模批量运行；
- 先解决“实验能跑起来”的最高优先级问题。
"""

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from aggregate_results import aggregate_records
from benchmark_inputs import (
    BenchmarkTask,
    BenchmarkTaskManifest,
    load_benchmark_tasks,
    load_tasks_from_manifest_name,
    load_tasks_from_manifest,
    list_available_manifests,
    resolve_manifest_path,
    serialize_benchmark_task,
)
from main import run_experiment_once
from utils.humaneval_official import (
    extract_humaneval_completion,
    write_humaneval_samples,
)
from utils.experiment_logger import append_experiment_record
from utils.result_layout import DEFAULT_RUNS_ROOT, create_run_artifacts


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CogMAS-TDD on benchmark tasks")
    parser.add_argument("--dataset", choices=["mbpp", "humaneval", "humaneval_plus"], default="")
    parser.add_argument("--dataset-path", default="")
    parser.add_argument("--manifest-path", default="")
    parser.add_argument("--manifest-name", default="")
    parser.add_argument("--list-manifests", action="store_true")
    parser.add_argument("--profile", default="ours")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--task-ids", nargs="*", default=[])
    parser.add_argument(
        "--seed-source",
        choices=["empty", "reference", "manifest"],
        default="empty",
        help="whether to preload the dataset reference code into initial state",
    )
    parser.add_argument("--results-path", default="")
    parser.add_argument("--summary-path", default="")
    parser.add_argument("--results-root", default=str(DEFAULT_RUNS_ROOT))
    parser.add_argument("--run-name", default="")
    parser.add_argument("--equivalence-mode", default="weak", choices=["weak", "strong"])
    parser.add_argument("--max-green-attempts", type=int, default=None)
    parser.add_argument("--max-same-error-streak", type=int, default=None)
    parser.add_argument("--max-refactor-retries", type=int, default=None)
    parser.add_argument("--skip-official-humaneval-eval", action="store_true")
    parser.add_argument("--humaneval-timeout", type=float, default=3.0)
    parser.add_argument("--humaneval-workers", type=int, default=4)
    parser.add_argument("--humaneval-k", nargs="*", type=int, default=[1])
    parser.add_argument("--list-only", action="store_true")
    parser.add_argument("--export-loaded-tasks", default="")
    parser.add_argument("--print-each", action="store_true")
    parser.add_argument(
        "--per-task-timeout",
        type=float,
        default=600.0,
        help="Max seconds per task before it is cancelled and recorded as failed (0 = no limit)",
    )
    parser.add_argument(
        "--inter-task-sleep",
        type=float,
        default=0.0,
        help="Seconds to sleep between tasks (throttle to avoid API rate limits)",
    )
    args = parser.parse_args()
    if args.list_manifests:
        return args
    if args.manifest_path and args.manifest_name:
        parser.error("use either --manifest-path or --manifest-name, not both")
    if not args.manifest_path and not args.manifest_name and not args.dataset:
        parser.error("--dataset is required unless --manifest-path is provided")
    return args


def _resolve_code_seed(task: BenchmarkTask, seed_source: str) -> str:
    if seed_source == "manifest":
        return task.seed_code
    if seed_source == "reference":
        return task.reference_code
    return ""


def _load_tasks(args: argparse.Namespace) -> tuple[list[BenchmarkTask], BenchmarkTaskManifest | None]:
    if args.manifest_name:
        manifest = load_tasks_from_manifest_name(args.manifest_name)
        items = manifest.items
        if args.task_ids:
            task_id_set = set(args.task_ids)
            items = [t for t in items if t.task_id in task_id_set]
        return items, manifest

    if args.manifest_path:
        manifest = load_tasks_from_manifest(args.manifest_path)
        items = manifest.items
        if args.task_ids:
            task_id_set = set(args.task_ids)
            items = [t for t in items if t.task_id in task_id_set]
        return items, manifest

    return (
        load_benchmark_tasks(
            args.dataset,
            path=args.dataset_path or None,
            offset=args.offset,
            limit=args.limit,
            task_ids=args.task_ids or None,
        ),
        None,
    )


def _dump_loaded_tasks(tasks: list[BenchmarkTask], export_path: str | None) -> None:
    if not export_path:
        return
    path = Path(export_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [serialize_benchmark_task(task) for task in tasks]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _print_loaded_tasks(tasks: list[BenchmarkTask]) -> None:
    payload = [
        {
            "dataset_name": task.dataset_name,
            "task_id": task.task_id,
            "entry_point": task.entry_point,
            "requirement_preview": task.requirement[:120],
            "has_seed_code": bool(task.seed_code),
            "metadata": task.metadata,
        }
        for task in tasks
    ]
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _derive_dataset_label(tasks: list[BenchmarkTask]) -> str:
    names = sorted({task.dataset_name for task in tasks})
    if not names:
        return "unknown"
    if len(names) == 1:
        return names[0]
    return "mixed"


def _build_run_metadata(
    *,
    args: argparse.Namespace,
    tasks: list[BenchmarkTask],
    manifest: BenchmarkTaskManifest | None,
    dataset_label: str,
    artifacts_dir: str,
) -> dict[str, Any]:
    return {
        "dataset_label": dataset_label,
        "profile": args.profile,
        "manifest_name": manifest.name if manifest else "",
        "manifest_description": manifest.description if manifest else "",
        "task_count": len(tasks),
        "task_ids": [task.task_id for task in tasks],
        "results_dir": artifacts_dir,
        "seed_source": args.seed_source,
        "equivalence_mode": args.equivalence_mode,
    }


async def _run_single_task(task: BenchmarkTask, args: argparse.Namespace) -> dict[str, Any]:
    final_state, record = await run_experiment_once(
        profile=args.profile,
        requirement=task.requirement,
        task_id=task.task_id,
        dataset_name=task.dataset_name,
        entry_point=task.entry_point,
        code=_resolve_code_seed(task, args.seed_source),
        test_cases=task.test_cases,
        equivalence_mode=args.equivalence_mode,
        results_path=args.results_path,
        max_green_attempts=args.max_green_attempts,
        max_same_error_streak=args.max_same_error_streak,
        max_refactor_retries=args.max_refactor_retries,
    )
    return {
        "task": task,
        "record": record,
        "final_state": final_state,
    }


def _build_summary(
    records: list[dict[str, Any]],
    args: argparse.Namespace,
    *,
    dataset_label: str,
    manifest: BenchmarkTaskManifest | None,
    run_dir: str,
) -> dict[str, Any]:
    total = len(records)
    success = sum(1 for item in records if item.get("workflow_status") == "success")
    passed = sum(1 for item in records if item.get("test_passed"))
    avg_green_attempts = (
        sum(item.get("green_attempts", 0) for item in records) / total if total else 0.0
    )
    avg_iteration = (
        sum(item.get("iteration", 0) for item in records) / total if total else 0.0
    )
    avg_wall_seconds = (
        sum(item.get("wall_seconds") or 0 for item in records) / total if total else 0.0
    )
    avg_tokens = (
        sum(item.get("total_tokens", 0) for item in records) / total if total else 0.0
    )
    avg_llm_calls = (
        sum(item.get("llm_calls", 0) for item in records) / total if total else 0.0
    )
    cr_initial_total = sum(item.get("cr_initial_findings", 0) for item in records)
    cr_resolved_total = sum(item.get("cr_findings_resolved", 0) for item in records)
    findings_resolved_rate = (cr_resolved_total / cr_initial_total) if cr_initial_total else 0.0
    avg_cr_score = (
        sum(item.get("cr_overall_score") or 0 for item in records) / total if total else 0.0
    )
    return {
        "dataset": dataset_label,
        "profile": args.profile,
        "manifest_name": manifest.name if manifest else "",
        "seed_source": args.seed_source,
        "run_dir": run_dir,
        "total_tasks": total,
        "workflow_success_rate": success / total if total else 0.0,
        "test_pass_rate": passed / total if total else 0.0,
        "avg_green_attempts": avg_green_attempts,
        "avg_iteration": avg_iteration,
        "avg_wall_seconds": round(avg_wall_seconds, 3),
        "avg_tokens": round(avg_tokens, 1),
        "avg_llm_calls": round(avg_llm_calls, 2),
        "avg_cr_score": round(avg_cr_score, 2),
        "cr_initial_findings_total": cr_initial_total,
        "cr_findings_resolved_total": cr_resolved_total,
        "findings_resolved_rate": round(findings_resolved_rate, 3),
    }


def _write_summary(summary: dict[str, Any], summary_path: str | None) -> None:
    if not summary_path:
        return
    path = Path(summary_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_json(payload: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_humaneval_outputs(
    run_results: list[dict[str, Any]],
    args: argparse.Namespace,
    samples_path: str | Path,
    eval_path: str | Path,
) -> dict[str, Any] | None:
    humaneval_results = [
        item for item in run_results
        if item["task"].dataset_name in ("humaneval", "humaneval_plus")
    ]
    if not humaneval_results or args.skip_official_humaneval_eval:
        return None

    samples = []
    for item in humaneval_results:
        task = item["task"]
        final_state = item["final_state"]
        final_code = str(final_state.get("code", ""))
        completion = extract_humaneval_completion(
            final_code,
            prompt=task.requirement,
            entry_point=task.entry_point,
        )
        samples.append(
            {
                "task_id": task.task_id,
                "completion": completion,
            }
        )
    write_humaneval_samples(samples, samples_path)
    command = [
        sys.executable,
        "evaluate_humaneval.py",
        "--sample-file",
        str(samples_path),
        "--timeout",
        str(args.humaneval_timeout),
        "--workers",
        str(args.humaneval_workers),
        "--output-path",
        str(eval_path),
    ]
    if args.humaneval_k:
        command.append("--k")
        command.extend(str(item) for item in args.humaneval_k)
    completed = subprocess.run(
        command,
        cwd=Path(__file__).resolve().parent,
        capture_output=True,
        text=True,
        check=True,
    )
    evaluation_summary = json.loads(completed.stdout)
    return {
        key: value
        for key, value in evaluation_summary.items()
        if key != "detailed_results"
    }


async def main() -> None:
    args = _parse_args()
    if args.list_manifests:
        print(json.dumps(list_available_manifests(), ensure_ascii=False, indent=2))
        return

    tasks, manifest = _load_tasks(args)
    if not tasks:
        raise ValueError("no tasks loaded for the given dataset / filters")
    dataset_label = _derive_dataset_label(tasks)
    artifacts = create_run_artifacts(
        profile_name=args.profile,
        dataset_name=dataset_label,
        manifest_name=manifest.name if manifest else "",
        run_name=args.run_name,
        results_root=args.results_root,
    )
    results_path = args.results_path or str(artifacts.records_path)
    summary_path = args.summary_path or str(artifacts.summary_path)
    export_loaded_tasks_path = args.export_loaded_tasks or str(artifacts.loaded_tasks_path)

    _write_json(
        _build_run_metadata(
            args=args,
            tasks=tasks,
            manifest=manifest,
            dataset_label=dataset_label,
            artifacts_dir=str(artifacts.run_dir),
        ),
        artifacts.metadata_path,
    )
    _dump_loaded_tasks(tasks, export_loaded_tasks_path)
    if args.list_only:
        _print_loaded_tasks(tasks)
        return

    per_task_limit: float | None = args.per_task_timeout if args.per_task_timeout > 0 else None
    run_results: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    for task in tasks:
        task_args = argparse.Namespace(**vars(args))
        task_args.results_path = results_path
        task_start = time.time()
        try:
            if per_task_limit is not None:
                result = await asyncio.wait_for(
                    _run_single_task(task, task_args), timeout=per_task_limit
                )
            else:
                result = await _run_single_task(task, task_args)
        except asyncio.TimeoutError:
            wall = round(time.time() - task_start, 3)
            timeout_record: dict[str, Any] = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "profile_name": args.profile,
                "run_id": "",
                "dataset_name": task.dataset_name,
                "task_id": task.task_id,
                "workflow_status": "failed",
                "stop_reason": "per_task_timeout",
                "test_passed": False,
                "green_attempts": 0,
                "same_error_streak": 0,
                "iteration": 0,
                "dynamic_verdict": "unknown",
                "static_verdict": "unknown",
                "final_verdict": "unknown",
                "enabled_agents": [],
                "weak_passed": None,
                "strong_passed": None,
                "is_equivalent": None,
                "has_l2_refactor": False,
                "has_l3_refactor": False,
                "cr_overall_score": None,
                "cr_security_score": None,
                "cr_reliability_score": None,
                "cr_maintainability_score": None,
                "cr_performance_score": None,
                "cr_needs_refactoring": None,
                "cr_total_findings": None,
                "wall_seconds": wall,
                "total_tokens": 0,
                "llm_calls": 0,
                "last_review_comment": f"per_task_timeout after {per_task_limit:.0f}s",
                "all_review_comments": [f"per_task_timeout after {per_task_limit:.0f}s"],
            }
            append_experiment_record(timeout_record, results_path)
            result = {"task": task, "record": timeout_record, "final_state": {}}
        run_results.append(result)
        records.append(result["record"])
        if args.print_each:
            print(json.dumps(result["record"], ensure_ascii=False, indent=2))
        if args.inter_task_sleep > 0:
            await asyncio.sleep(args.inter_task_sleep)

    official_humaneval_eval = _write_humaneval_outputs(
        run_results,
        args,
        artifacts.humaneval_samples_path,
        artifacts.humaneval_eval_path,
    )
    summary = _build_summary(
        records,
        args,
        dataset_label=dataset_label,
        manifest=manifest,
        run_dir=str(artifacts.run_dir),
    )
    if official_humaneval_eval:
        summary["official_humaneval_eval"] = official_humaneval_eval
    _write_summary(summary, summary_path)
    aggregate_payload = {
        "input_record_count": len(records),
        "aggregation": aggregate_records(records, group_by="profile_dataset"),
    }
    _write_json(aggregate_payload, artifacts.aggregate_path)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
