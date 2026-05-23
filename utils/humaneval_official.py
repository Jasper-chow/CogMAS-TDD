from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
import importlib
import json
import multiprocessing
import os
from pathlib import Path
import platform
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_HUMANEVAL_ROOT = PROJECT_ROOT / "human-eval"
DEFAULT_HUMANEVAL_PROBLEM_FILE = DEFAULT_HUMANEVAL_ROOT / "data" / "HumanEval.jsonl.gz"


@contextmanager
def _human_eval_import_path(root: str | Path = DEFAULT_HUMANEVAL_ROOT):
    root_path = str(Path(root))
    inserted = False
    previous_pythonpath = os.environ.get("PYTHONPATH", "")
    if root_path not in sys.path:
        sys.path.insert(0, root_path)
        inserted = True
    pythonpath_parts = [part for part in previous_pythonpath.split(os.pathsep) if part]
    if root_path not in pythonpath_parts:
        os.environ["PYTHONPATH"] = (
            root_path
            if not previous_pythonpath
            else root_path + os.pathsep + previous_pythonpath
        )
    try:
        yield
    finally:
        if inserted:
            try:
                sys.path.remove(root_path)
            except ValueError:
                pass
        if previous_pythonpath:
            os.environ["PYTHONPATH"] = previous_pythonpath
        else:
            os.environ.pop("PYTHONPATH", None)


def _load_humaneval_modules(root: str | Path = DEFAULT_HUMANEVAL_ROOT):
    with _human_eval_import_path(root):
        data_module = importlib.import_module("human_eval.data")
        execution_module = importlib.import_module("human_eval.execution")
    return data_module, execution_module


def _unsafe_execute_windows_worker(
    problem: dict[str, Any],
    completion: str,
    result: Any,
    humaneval_root: str,
) -> None:
    root_path = str(Path(humaneval_root))
    if root_path not in sys.path:
        sys.path.insert(0, root_path)
    execution_module = importlib.import_module("human_eval.execution")
    with execution_module.create_tempdir():
        import os as _os
        import shutil as _shutil

        rmtree = _shutil.rmtree
        rmdir = _os.rmdir
        chdir = _os.chdir
        execution_module.reliability_guard()
        check_program = (
            problem["prompt"]
            + completion
            + "\n"
            + problem["test"]
            + "\n"
            + f"check({problem['entry_point']})"
        )
        try:
            exec_globals: dict[str, Any] = {}
            with execution_module.swallow_io():
                exec(check_program, exec_globals)
            result.append("passed")
        except BaseException as exc:  # noqa: BLE001
            result.append(f"failed: {exc}")
        _shutil.rmtree = rmtree
        _os.rmdir = rmdir
        _os.chdir = chdir


def _check_correctness_compatible(
    execution_module: Any,
    problem: dict[str, Any],
    completion: str,
    timeout: float,
    completion_id: int,
    humaneval_root: str | Path = DEFAULT_HUMANEVAL_ROOT,
) -> dict[str, Any]:
    """
    Keep HumanEval's official problem format and pass@k aggregation,
    but use a Windows-compatible execution path when `signal.setitimer`
    is unavailable.
    """
    if hasattr(execution_module.signal, "setitimer") and platform.system() != "Windows":
        return execution_module.check_correctness(problem, completion, timeout, completion_id)

    manager = multiprocessing.Manager()
    result = manager.list()

    process = multiprocessing.Process(
        target=_unsafe_execute_windows_worker,
        args=(problem, completion, result, str(humaneval_root)),
    )
    process.start()
    process.join(timeout=timeout + 1)
    if process.is_alive():
        process.kill()

    if not result:
        result.append("timed out")

    return {
        "task_id": problem["task_id"],
        "passed": result[0] == "passed",
        "result": result[0],
        "completion_id": completion_id,
    }


def _estimate_pass_at_k(total: list[int], correct: list[int], k: int) -> float:
    def estimator(n: int, c: int, kth: int) -> float:
        if n - c < kth:
            return 1.0
        product = 1.0
        for value in range(n - c + 1, n + 1):
            product *= 1.0 - kth / value
        return 1.0 - product

    if not total:
        return 0.0
    return sum(estimator(n, c, k) for n, c in zip(total, correct)) / len(total)


def extract_humaneval_completion(
    code: str,
    *,
    prompt: str,
    entry_point: str,  # noqa: ARG001 — kept for API compatibility
) -> str:
    stripped_code = code.strip("\n")
    stripped_prompt = prompt.strip("\n")
    # Case 1: generated code already starts with the full prompt — return only the suffix.
    if stripped_code.startswith(stripped_prompt):
        return stripped_code[len(stripped_prompt) :].lstrip("\n")
    # Case 2: return the full generated code as the completion.
    # The HumanEval eval concatenates `prompt + completion`, so any redefinition of
    # `entry_point` in the generated code overrides the incomplete stub from the prompt
    # (Python last-definition-wins).  Module-level imports and helper functions placed
    # before or after the main function are also preserved this way, fixing NameErrors
    # that arise when L2/L3 refactoring adds imports, extracts helpers, or renames
    # function parameters.
    return stripped_code


def write_humaneval_samples(samples: list[dict[str, Any]], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for sample in samples:
            file.write(json.dumps(sample, ensure_ascii=False) + "\n")
    return path


def evaluate_humaneval_samples(
    sample_file: str | Path,
    *,
    problem_file: str | Path | None = DEFAULT_HUMANEVAL_PROBLEM_FILE,
    k_values: list[int] | None = None,
    timeout: float = 3.0,
    n_workers: int = 4,
    humaneval_root: str | Path = DEFAULT_HUMANEVAL_ROOT,
) -> dict[str, Any]:
    k_values = k_values or [1]
    resolved_problem_file = problem_file or DEFAULT_HUMANEVAL_PROBLEM_FILE
    with _human_eval_import_path(humaneval_root):
        data_module, execution_module = _load_humaneval_modules(humaneval_root)
        problems = data_module.read_problems(str(resolved_problem_file))

        def _stream_jsonl(path: str | Path):
            with Path(path).open("r", encoding="utf-8") as file:
                for line in file:
                    if line.strip():
                        yield json.loads(line)

        futures = []
        completion_id = Counter()
        results: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
        sample_count = 0

        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            for sample in _stream_jsonl(sample_file):
                task_id = sample["task_id"]
                completion = sample["completion"]
                future = executor.submit(
                    _check_correctness_compatible,
                    execution_module,
                    problems[task_id],
                    completion,
                    timeout,
                    completion_id[task_id],
                    humaneval_root,
                )
                futures.append(future)
                completion_id[task_id] += 1
                sample_count += 1

            for future in as_completed(futures):
                result = future.result()
                results[result["task_id"]].append((result["completion_id"], result))

        total: list[int] = []
        correct: list[int] = []
        passed_count = 0
        detailed_results: list[dict[str, Any]] = []
        for task_id, task_results in results.items():
            task_results.sort(key=lambda item: item[0])
            passed_flags = [item[1]["passed"] for item in task_results]
            total.append(len(passed_flags))
            correct_count = sum(1 for passed in passed_flags if passed)
            correct.append(correct_count)
            passed_count += correct_count
            for _, item in task_results:
                detailed_results.append(item)

        pass_metrics = {
            f"pass@{k}": _estimate_pass_at_k(total, correct, k)
            for k in k_values
            if total and all(sample_total >= k for sample_total in total)
        }
        return {
            "sample_file": str(sample_file),
            "problem_file": str(resolved_problem_file),
            "sample_count": sample_count,
            "task_count": len(results),
            "passed_count": passed_count,
            "pass_metrics": pass_metrics,
            "detailed_results": detailed_results,
        }
