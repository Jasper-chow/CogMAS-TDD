from __future__ import annotations

"""
实验输入适配层。

职责：
- 读取 MBPP / HumanEval 原始题目文件；
- 统一转换成 CogMAS-TDD 可消费的任务结构；
- 尽量不依赖外部包的 import 路径，优先使用标准库解析。
"""

from dataclasses import asdict, dataclass, field
import gzip
import json
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_MBPP_PATH = PROJECT_ROOT / "MBPP" / "sanitized-mbpp.json"
DEFAULT_HUMANEVAL_PATH = PROJECT_ROOT / "human-eval" / "data" / "HumanEval.jsonl.gz"
DEFAULT_MANIFEST_DIR = PROJECT_ROOT / "benchmark_manifests"


@dataclass
class BenchmarkTask:
    dataset_name: str
    task_id: str
    requirement: str
    entry_point: str
    test_cases: str
    reference_code: str
    seed_code: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkTaskManifest:
    name: str
    description: str
    items: list[BenchmarkTask]
    metadata: dict[str, Any] = field(default_factory=dict)


def _read_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def _stream_jsonl(path: str | Path) -> Iterable[dict[str, Any]]:
    path = Path(path)
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if line:
                    yield json.loads(line)
        return

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                yield json.loads(line)


def _wrap_mbpp_tests(test_imports: list[str], test_list: list[str]) -> str:
    imports = "\n".join(test_imports) if test_imports else ""
    body = "\n    ".join(test_list)
    prefix = f"{imports}\n\n" if imports else ""
    return prefix + "def test_mbpp_task():\n    " + body + "\n"


def _wrap_humaneval_tests(raw_test: str, entry_point: str) -> str:
    cleaned = raw_test.strip()
    return (
        f"{cleaned}\n\n"
        f"def test_humaneval_task():\n"
        f"    check({entry_point})\n"
    )


def _iter_filtered(
    items: Iterable[dict[str, Any]],
    *,
    offset: int = 0,
    limit: int | None = None,
    task_ids: set[str] | None = None,
) -> Iterable[dict[str, Any]]:
    matched = 0
    yielded = 0
    for item in items:
        item_task_id = str(item.get("task_id", ""))
        if task_ids and item_task_id not in task_ids:
            continue
        if matched < offset:
            matched += 1
            continue
        if limit is not None and yielded >= limit:
            break
        matched += 1
        yielded += 1
        yield item


def load_mbpp_tasks(
    *,
    path: str | Path = DEFAULT_MBPP_PATH,
    offset: int = 0,
    limit: int | None = None,
    task_ids: list[str] | None = None,
) -> list[BenchmarkTask]:
    raw_items = _read_json(path)
    selected = _iter_filtered(
        raw_items,
        offset=offset,
        limit=limit,
        task_ids=set(task_ids or []),
    )
    tasks: list[BenchmarkTask] = []
    for item in selected:
        task_id = str(item["task_id"])
        entry_point = _infer_entry_point_from_code(item["code"])
        tasks.append(
            BenchmarkTask(
                dataset_name="mbpp",
                task_id=task_id,
                requirement=item["prompt"],
                entry_point=entry_point,
                test_cases=_wrap_mbpp_tests(item.get("test_imports", []), item["test_list"]),
                reference_code=item["code"],
                metadata={
                    "source_file": item.get("source_file", ""),
                    "dataset_path": str(Path(path)),
                },
            )
        )
    return tasks


def _humaneval_sort_key(task_id: str) -> int:
    try:
        return int(task_id.split("/")[-1])
    except ValueError:
        return 0


def load_humaneval_plus_tasks(
    *,
    offset: int = 0,
    limit: int | None = None,
    task_ids: list[str] | None = None,
) -> list[BenchmarkTask]:
    try:
        from evalplus.data.humaneval import get_human_eval_plus  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "evalplus is required for HumanEval+. Install with: uv add evalplus"
        ) from exc

    problems = get_human_eval_plus()
    sorted_items = sorted(problems.items(), key=lambda kv: _humaneval_sort_key(kv[0]))
    selected = _iter_filtered(
        ({"task_id": tid, **data} for tid, data in sorted_items),
        offset=offset,
        limit=limit,
        task_ids=set(task_ids or []),
    )
    tasks: list[BenchmarkTask] = []
    for item in selected:
        task_id = str(item["task_id"])
        prompt = item["prompt"]
        entry_point = item["entry_point"]
        canonical_solution = item.get("canonical_solution", "")
        test = item.get("test", "")
        tasks.append(
            BenchmarkTask(
                dataset_name="humaneval_plus",
                task_id=task_id,
                requirement=prompt,
                entry_point=entry_point,
                test_cases=_wrap_humaneval_tests(test, entry_point),
                reference_code=prompt + canonical_solution,
                metadata={"source": "evalplus"},
            )
        )
    return tasks


def load_humaneval_tasks(
    *,
    path: str | Path = DEFAULT_HUMANEVAL_PATH,
    offset: int = 0,
    limit: int | None = None,
    task_ids: list[str] | None = None,
) -> list[BenchmarkTask]:
    selected = _iter_filtered(
        _stream_jsonl(path),
        offset=offset,
        limit=limit,
        task_ids=set(task_ids or []),
    )
    tasks: list[BenchmarkTask] = []
    for item in selected:
        task_id = str(item["task_id"])
        prompt = item["prompt"]
        reference_code = prompt + item["canonical_solution"]
        entry_point = item["entry_point"]
        tasks.append(
            BenchmarkTask(
                dataset_name="humaneval",
                task_id=task_id,
                requirement=prompt,
                entry_point=entry_point,
                test_cases=_wrap_humaneval_tests(item["test"], entry_point),
                reference_code=reference_code,
                metadata={"dataset_path": str(Path(path))},
            )
        )
    return tasks


def load_bigcodebench_tasks(
    *,
    split: str = "v0.1.2",
    offset: int = 0,
    limit: int | None = None,
    task_ids: list[str] | None = None,
) -> list[BenchmarkTask]:
    """Load tasks from BigCodeBench (function-level, complex real-world APIs)."""
    try:
        from datasets import load_dataset  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "datasets is required for BigCodeBench. Install with: uv add datasets"
        ) from exc

    ds = load_dataset("bigcode/bigcodebench", split=split)
    raw_items = list(ds)
    selected = _iter_filtered(
        raw_items,
        offset=offset,
        limit=limit,
        task_ids=set(task_ids or []),
    )
    tasks: list[BenchmarkTask] = []
    for item in selected:
        task_id = str(item["task_id"])
        # complete_prompt = imports + signature + docstring; canonical_solution = body
        reference_code = item["complete_prompt"] + item["canonical_solution"]
        tasks.append(
            BenchmarkTask(
                dataset_name="bigcodebench",
                task_id=task_id,
                requirement=item["instruct_prompt"],
                entry_point=item["entry_point"],
                test_cases=item["test"],
                reference_code=reference_code,
                seed_code=item["code_prompt"],
                metadata={"libs": item.get("libs", [])},
            )
        )
    return tasks


def load_benchmark_tasks(
    dataset_name: str,
    *,
    path: str | Path | None = None,
    offset: int = 0,
    limit: int | None = None,
    task_ids: list[str] | None = None,
) -> list[BenchmarkTask]:
    lowered = dataset_name.lower()
    if lowered == "mbpp":
        return load_mbpp_tasks(
            path=path or DEFAULT_MBPP_PATH,
            offset=offset,
            limit=limit,
            task_ids=task_ids,
        )
    if lowered == "humaneval":
        return load_humaneval_tasks(
            path=path or DEFAULT_HUMANEVAL_PATH,
            offset=offset,
            limit=limit,
            task_ids=task_ids,
        )
    if lowered == "humaneval_plus":
        return load_humaneval_plus_tasks(
            offset=offset,
            limit=limit,
            task_ids=task_ids,
        )
    if lowered == "bigcodebench":
        return load_bigcodebench_tasks(
            offset=offset,
            limit=limit,
            task_ids=task_ids,
        )
    raise ValueError(f"unsupported dataset: {dataset_name}")


def build_task_index(
    dataset_name: str,
    *,
    path: str | Path | None = None,
) -> dict[str, BenchmarkTask]:
    tasks = load_benchmark_tasks(dataset_name, path=path)
    return {task.task_id: task for task in tasks}


def load_tasks_from_manifest(
    manifest_path: str | Path,
) -> BenchmarkTaskManifest:
    manifest = _read_json(manifest_path)
    if not isinstance(manifest, dict):
        raise ValueError("benchmark manifest must be a JSON object")

    dataset_paths = {
        name.lower(): Path(raw_path)
        for name, raw_path in manifest.get("dataset_paths", {}).items()
    }
    items = manifest.get("items", [])
    if not isinstance(items, list):
        raise ValueError("manifest.items must be a JSON array")

    task_indexes: dict[tuple[str, str], dict[str, BenchmarkTask]] = {}
    resolved_tasks: list[BenchmarkTask] = []

    for item in items:
        if not isinstance(item, dict):
            raise ValueError("each manifest item must be an object")

        dataset_name = str(item.get("dataset", manifest.get("default_dataset", ""))).strip().lower()
        if not dataset_name:
            raise ValueError("manifest item is missing dataset")

        task_id = str(item.get("task_id", "")).strip()
        if not task_id:
            raise ValueError("manifest item is missing task_id")

        dataset_path_value = item.get("dataset_path") or dataset_paths.get(dataset_name)
        dataset_path = str(dataset_path_value) if dataset_path_value else ""
        cache_key = (dataset_name, dataset_path)
        if cache_key not in task_indexes:
            task_indexes[cache_key] = build_task_index(
                dataset_name,
                path=dataset_path or None,
            )

        dataset_index = task_indexes[cache_key]
        if task_id not in dataset_index:
            raise ValueError(
                f"task_id {task_id!r} not found in dataset {dataset_name!r}"
                + (f" from {dataset_path}" if dataset_path else "")
            )

        base_task = dataset_index[task_id]
        merged_metadata = {
            **base_task.metadata,
            **manifest.get("metadata", {}),
            **item.get("metadata", {}),
        }
        if dataset_path:
            merged_metadata["dataset_path"] = dataset_path
        if "tags" in item:
            merged_metadata["tags"] = item["tags"]
        if "note" in item:
            merged_metadata["note"] = item["note"]

        resolved_tasks.append(
            BenchmarkTask(
                dataset_name=base_task.dataset_name,
                task_id=base_task.task_id,
                requirement=str(item.get("requirement", base_task.requirement)),
                entry_point=str(item.get("entry_point", base_task.entry_point)),
                test_cases=str(item.get("test_cases", base_task.test_cases)),
                reference_code=str(item.get("reference_code", base_task.reference_code)),
                seed_code=str(item.get("seed_code", "")),
                metadata=merged_metadata,
            )
        )

    return BenchmarkTaskManifest(
        name=str(manifest.get("name", Path(manifest_path).stem)),
        description=str(manifest.get("description", "")),
        items=resolved_tasks,
        metadata=dict(manifest.get("metadata", {})),
    )


def list_available_manifests(
    manifest_dir: str | Path = DEFAULT_MANIFEST_DIR,
) -> list[dict[str, str]]:
    path = Path(manifest_dir)
    if not path.exists():
        return []

    manifests: list[dict[str, str]] = []
    for manifest_path in sorted(path.glob("*.json")):
        try:
            payload = _read_json(manifest_path)
        except Exception:  # noqa: BLE001
            payload = {}
        manifests.append(
            {
                "name": str(payload.get("name", manifest_path.stem)),
                "path": str(manifest_path),
                "description": str(payload.get("description", "")),
            }
        )
    return manifests


def resolve_manifest_path(
    manifest_name_or_path: str | Path,
    *,
    manifest_dir: str | Path = DEFAULT_MANIFEST_DIR,
) -> Path:
    candidate = Path(manifest_name_or_path)
    if candidate.exists():
        return candidate

    if candidate.suffix == ".json":
        named_candidate = Path(manifest_dir) / candidate.name
        if named_candidate.exists():
            return named_candidate
    else:
        named_candidate = Path(manifest_dir) / f"{candidate.name}.json"
        if named_candidate.exists():
            return named_candidate

    available = ", ".join(item["name"] for item in list_available_manifests(manifest_dir))
    raise FileNotFoundError(
        f"manifest not found: {manifest_name_or_path}. "
        f"available manifests: {available or 'none'}"
    )


def load_tasks_from_manifest_name(
    manifest_name_or_path: str | Path,
    *,
    manifest_dir: str | Path = DEFAULT_MANIFEST_DIR,
) -> BenchmarkTaskManifest:
    manifest_path = resolve_manifest_path(manifest_name_or_path, manifest_dir=manifest_dir)
    return load_tasks_from_manifest(manifest_path)


def serialize_benchmark_task(task: BenchmarkTask) -> dict[str, Any]:
    return asdict(task)


def _infer_entry_point_from_code(code: str) -> str:
    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith("def "):
            return stripped.split("def ", 1)[1].split("(", 1)[0]
    return "solve"
