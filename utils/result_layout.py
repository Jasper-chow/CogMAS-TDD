from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RUNS_ROOT = PROJECT_ROOT / "results" / "runs"


@dataclass
class RunArtifacts:
    run_dir: Path
    records_path: Path
    summary_path: Path
    loaded_tasks_path: Path
    aggregate_path: Path
    humaneval_samples_path: Path
    humaneval_eval_path: Path
    metadata_path: Path


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", text.strip())
    cleaned = cleaned.strip("._-")
    return cleaned or "unnamed"


def build_run_name(
    *,
    profile_name: str,
    dataset_name: str,
    manifest_name: str = "",
    run_name: str = "",
    timestamp: str | None = None,
) -> str:
    stamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    parts = [stamp, slugify(profile_name), slugify(dataset_name)]
    if manifest_name:
        parts.append(slugify(manifest_name))
    if run_name:
        parts.append(slugify(run_name))
    return "__".join(parts)


def create_run_artifacts(
    *,
    profile_name: str,
    dataset_name: str,
    manifest_name: str = "",
    run_name: str = "",
    results_root: str | Path = DEFAULT_RUNS_ROOT,
) -> RunArtifacts:
    root = Path(results_root)
    final_run_name = build_run_name(
        profile_name=profile_name,
        dataset_name=dataset_name,
        manifest_name=manifest_name,
        run_name=run_name,
    )
    run_dir = root / slugify(dataset_name) / slugify(profile_name) / final_run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    return RunArtifacts(
        run_dir=run_dir,
        records_path=run_dir / "records.jsonl",
        summary_path=run_dir / "summary.json",
        loaded_tasks_path=run_dir / "loaded_tasks.json",
        aggregate_path=run_dir / "aggregate.json",
        humaneval_samples_path=run_dir / "humaneval_samples.jsonl",
        humaneval_eval_path=run_dir / "humaneval_eval.json",
        metadata_path=run_dir / "run_metadata.json",
    )
