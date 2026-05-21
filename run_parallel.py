from __future__ import annotations

"""
Parallel benchmark runner using two SiliconFlow API keys.

Splits a manifest in half, spawns two run_benchmark.py subprocesses
each using a different API key, streams prefixed output, then merges
the JSONL records into a single combined results file.

Required .env keys:
  SILICONFLOW_API_KEY    — worker A (first half of tasks)
  SILICONFLOW_API_KEY_2  — worker B (second half of tasks)

Usage:
  uv run python run_parallel.py --manifest-name humaneval_plus_full --profile ours
  uv run python run_parallel.py --manifest-name humaneval_plus_full --profile b0_direct_generation
"""

import argparse
import json
import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Parallel benchmark runner (2 API keys)")
    p.add_argument("--manifest-name", required=True, help="Manifest to split and run in parallel")
    p.add_argument("--profile", default="ours", help="Experiment profile name")
    p.add_argument("--results-root", default="results/runs", help="Root directory for run artifacts")
    p.add_argument("--run-name", default="", help="Optional label appended to run directory name")
    p.add_argument("--seed-source", choices=["empty", "reference", "manifest"], default="empty")
    p.add_argument("--equivalence-mode", default="weak", choices=["weak", "strong"])
    p.add_argument("--max-green-attempts", type=int, default=None)
    p.add_argument("--print-each", action="store_true", help="Print each task record as it finishes")
    p.add_argument("--skip-official-humaneval-eval", action="store_true")
    return p.parse_args()


def _stream_output(pipe, prefix: str, lines: list[str]) -> None:
    for raw in pipe:
        line = raw.rstrip("\n")
        tagged = f"[{prefix}] {line}"
        print(tagged, flush=True)
        lines.append(tagged)


def _write_sub_manifest(tasks: list, manifest_name: str, label: str, stamp: str) -> Path:
    manifest_dir = Path("benchmark_manifests")
    manifest_dir.mkdir(exist_ok=True)

    datasets = {t.dataset_name for t in tasks}
    use_default = len(datasets) == 1
    items = (
        [{"task_id": t.task_id} for t in tasks]
        if use_default
        else [{"dataset": t.dataset_name, "task_id": t.task_id} for t in tasks]
    )
    payload: dict = {
        "name": f"{manifest_name}_{label}_{stamp}",
        "description": f"Auto-split [{label}] from {manifest_name} at {stamp}",
        "items": items,
    }
    if use_default:
        payload["default_dataset"] = next(iter(datasets))

    path = manifest_dir / f"_parallel_{manifest_name}_{label}_{stamp}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _build_subprocess_cmd(
    manifest_path: Path,
    results_path: str,
    summary_path: str,
    args: argparse.Namespace,
) -> list[str]:
    cmd = [
        sys.executable, "run_benchmark.py",
        "--manifest-path", str(manifest_path),
        "--profile", args.profile,
        "--results-path", results_path,
        "--summary-path", summary_path,
        "--seed-source", args.seed_source,
        "--equivalence-mode", args.equivalence_mode,
    ]
    if args.print_each:
        cmd.append("--print-each")
    if args.max_green_attempts is not None:
        cmd += ["--max-green-attempts", str(args.max_green_attempts)]
    if args.skip_official_humaneval_eval:
        cmd.append("--skip-official-humaneval-eval")
    return cmd


def _merge_jsonl(paths: list[str]) -> list[dict]:
    records: list[dict] = []
    for path_str in paths:
        p = Path(path_str)
        if not p.exists():
            return records
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records


def main() -> None:
    args = _parse_args()

    from benchmark_inputs import load_tasks_from_manifest_name
    manifest = load_tasks_from_manifest_name(args.manifest_name)
    tasks = manifest.items
    n = len(tasks)
    if n == 0:
        raise SystemExit("No tasks found in manifest.")

    half = (n + 1) // 2
    tasks_a, tasks_b = tasks[:half], tasks[half:]
    print(f"Total tasks: {n}  →  Worker-A: {len(tasks_a)}, Worker-B: {len(tasks_b)}", flush=True)

    key1 = os.environ.get("SILICONFLOW_API_KEY", "")
    key2 = os.environ.get("SILICONFLOW_API_KEY_2", "")
    if not key1:
        raise SystemExit("SILICONFLOW_API_KEY is not set.")
    if not key2:
        print("Warning: SILICONFLOW_API_KEY_2 not set — both workers will share the same key.", flush=True)
        key2 = key1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    manifest_a = _write_sub_manifest(tasks_a, args.manifest_name, "a", stamp)
    manifest_b = _write_sub_manifest(tasks_b, args.manifest_name, "b", stamp)

    merged_dir = Path(args.results_root) / f"_parallel_{args.manifest_name}_{stamp}"
    merged_dir.mkdir(parents=True, exist_ok=True)

    results_a = str(merged_dir / "records_a.jsonl")
    results_b = str(merged_dir / "records_b.jsonl")
    summary_a = str(merged_dir / "summary_a.json")
    summary_b = str(merged_dir / "summary_b.json")

    cmd_a = _build_subprocess_cmd(manifest_a, results_a, summary_a, args)
    cmd_b = _build_subprocess_cmd(manifest_b, results_b, summary_b, args)

    env_a = {**os.environ, "SILICONFLOW_API_KEY": key1}
    env_b = {**os.environ, "SILICONFLOW_API_KEY": key2}

    print("Spawning Worker-A and Worker-B...", flush=True)
    proc_a = subprocess.Popen(cmd_a, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env_a)
    proc_b = subprocess.Popen(cmd_b, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env_b)

    lines_a: list[str] = []
    lines_b: list[str] = []
    t_a = threading.Thread(target=_stream_output, args=(proc_a.stdout, "A", lines_a), daemon=True)
    t_b = threading.Thread(target=_stream_output, args=(proc_b.stdout, "B", lines_b), daemon=True)
    t_a.start()
    t_b.start()
    t_a.join()
    t_b.join()
    rc_a = proc_a.wait()
    rc_b = proc_b.wait()

    manifest_a.unlink(missing_ok=True)
    manifest_b.unlink(missing_ok=True)

    print(f"\nWorker-A exit={rc_a}  Worker-B exit={rc_b}", flush=True)

    records = _merge_jsonl([results_a, results_b])
    merged_records_path = merged_dir / "records.jsonl"
    with merged_records_path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    total = len(records)
    passed = sum(1 for r in records if r.get("test_passed"))
    success = sum(1 for r in records if r.get("workflow_status") == "success")
    avg_attempts = sum(r.get("green_attempts", 0) for r in records) / total if total else 0.0

    summary = {
        "profile": args.profile,
        "manifest": args.manifest_name,
        "total_tasks": total,
        "worker_a_tasks": len(tasks_a),
        "worker_b_tasks": len(tasks_b),
        "test_pass_rate": round(passed / total, 4) if total else 0.0,
        "workflow_success_rate": round(success / total, 4) if total else 0.0,
        "avg_green_attempts": round(avg_attempts, 2),
        "merged_records": str(merged_records_path),
        "run_dir": str(merged_dir),
        "worker_a_exit": rc_a,
        "worker_b_exit": rc_b,
    }
    (merged_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("\n" + json.dumps(summary, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
