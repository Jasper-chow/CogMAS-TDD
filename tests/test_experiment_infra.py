from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from benchmark_inputs import list_available_manifests, resolve_manifest_path
from utils.humaneval_official import extract_humaneval_completion
from utils.ldb_prompt_protocol import build_cumulative_ldb_history
from utils.result_layout import create_run_artifacts


def test_manifest_registry_can_resolve_named_manifest() -> None:
    manifests = list_available_manifests()
    names = {item["name"] for item in manifests}
    assert "shared_baseline_subset_v1" in names

    manifest_path = resolve_manifest_path("shared_baseline_subset_v1")
    assert manifest_path.name == "shared_baseline_subset_v1.json"


def test_result_layout_creates_run_tree(tmp_path: Path) -> None:
    artifacts = create_run_artifacts(
        profile_name="ours",
        dataset_name="humaneval",
        manifest_name="humaneval_smoke_v1",
        run_name="smoke",
        results_root=tmp_path,
    )

    assert artifacts.run_dir.exists()
    assert artifacts.records_path.parent == artifacts.run_dir
    assert artifacts.summary_path.parent == artifacts.run_dir
    assert artifacts.humaneval_eval_path.parent == artifacts.run_dir


def test_extract_humaneval_completion_strips_prompt_prefix() -> None:
    prompt = 'def add(a, b):\n    """Return the sum of two integers."""\n'
    full_code = prompt + "    return a + b\n"

    completion = extract_humaneval_completion(
        full_code,
        prompt=prompt,
        entry_point="add",
    )

    assert completion == "    return a + b"


def test_build_cumulative_ldb_history_keeps_recent_rounds() -> None:
    history = build_cumulative_ldb_history(
        ["round-a", "round-b", "round-c", "round-d"],
        max_histories=3,
    )

    assert "round-a" not in history
    assert "round-b" in history
    assert "## Debug Round 1" in history
