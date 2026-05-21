from __future__ import annotations

"""
测试执行节点（Green 自修复循环核心）。

职责：
- 执行 pytest 验证当前 code + test_cases；
- 记录测试是否通过与错误摘要；
- 维护“连续相同错误计数”，用于提前终止死循环。
"""

import subprocess
import sys
import tempfile
from pathlib import Path

from state import AgentState

NODE_NAME = "test_runner_node"
PROMPT_TEMPLATE = "该节点不调用 LLM，仅执行 pytest 并汇总结果。"


def _normalize_error(output: str) -> str:
    """抽取并压缩 pytest 输出，避免状态过大。"""
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return "pytest failed with empty output"
    return "\n".join(lines[-12:])[:1200]


def _extract_failed_test_and_output(output: str) -> tuple[str, str]:
    """
    从 pytest 输出中提取最可能的失败测试与真实输出摘要。

    当前实现是近似提取：
    - 失败测试：优先取包含 `assert` 的最后一行
    - 真实输出：取最后几行摘要
    """
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    failed_test = next((line for line in reversed(lines) if "assert " in line), "")
    real_output = "\n".join(lines[-8:])[:800] if lines else "pytest failed with empty output"
    return failed_test, real_output


def _ensure_test_imports(test_code: str) -> str:
    """若测试未显式导入实现模块，补充 from app import *。"""
    if "from app import" in test_code or "import app" in test_code:
        return test_code
    return "from app import *\n\n" + test_code


async def run(state: AgentState) -> AgentState:
    """
    执行 pytest 并更新测试状态。

    返回字段：
    - test_passed
    - test_error
    - last_test_error
    - same_error_streak
    - review_comments
    """
    code = state.get("code", "")
    # Always evaluate against the original benchmark test suite, not LLM-generated tests
    # from red_node, so that all profiles are compared on the same ground truth.
    test_cases = state.get("original_test_cases") or state.get("test_cases", "")

    if not code or not test_cases:
        error_msg = "missing code or test_cases before pytest run"
        previous_error = state.get("test_error", "")
        same_error_streak = (
            state.get("same_error_streak", 0) + 1 if error_msg == previous_error else 1
        )
        comments = [*state.get("review_comments", [])]
        comments.append(f"{NODE_NAME}: FAIL (missing input)")
        return {
            "test_passed": False,
            "test_error": error_msg,
            "last_test_error": previous_error,
            "same_error_streak": same_error_streak,
            "review_comments": comments,
        }

    try:
        with tempfile.TemporaryDirectory(prefix="cogmas_tdd_") as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "app.py").write_text(code, encoding="utf-8")
            (workspace / "test_app.py").write_text(
                _ensure_test_imports(test_cases), encoding="utf-8"
            )

            process = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "test_app.py"],
                cwd=str(workspace),
                capture_output=True,
                text=True,
                timeout=60,
            )
    except subprocess.TimeoutExpired as exc:
        timeout_msg = f"pytest timeout after {exc.timeout}s"
        previous_error = state.get("test_error", "")
        same_error_streak = (
            state.get("same_error_streak", 0) + 1
            if timeout_msg == previous_error
            else 1
        )
        comments = [*state.get("review_comments", [])]
        comments.append(f"{NODE_NAME}: FAIL (timeout)")
        return {
            "test_passed": False,
            "test_error": timeout_msg,
            "last_test_error": previous_error,
            "same_error_streak": same_error_streak,
            "review_comments": comments,
        }
    except Exception as exc:  # noqa: BLE001
        runtime_msg = f"pytest runner exception: {exc}"
        previous_error = state.get("test_error", "")
        same_error_streak = (
            state.get("same_error_streak", 0) + 1
            if runtime_msg == previous_error
            else 1
        )
        comments = [*state.get("review_comments", [])]
        comments.append(f"{NODE_NAME}: FAIL (runner exception)")
        return {
            "test_passed": False,
            "test_error": runtime_msg,
            "last_test_error": previous_error,
            "same_error_streak": same_error_streak,
            "review_comments": comments,
        }

    success = process.returncode == 0
    previous_error = state.get("test_error", "")
    combined_output = process.stdout + "\n" + process.stderr
    new_error = "" if success else _normalize_error(combined_output)
    failed_test, real_output = _extract_failed_test_and_output(combined_output)
    if success:
        same_error_streak = 0
    else:
        same_error_streak = (
            state.get("same_error_streak", 0) + 1 if new_error == previous_error else 1
        )

    comments = [*state.get("review_comments", [])]
    comments.append(f"{NODE_NAME}: {'PASS' if success else 'FAIL'}")
    updates: AgentState = {
        "test_passed": success,
        "test_error": new_error,
        "last_test_error": previous_error,
        "same_error_streak": same_error_streak,
        "last_failed_test": failed_test,
        "last_real_output": real_output if not success else "",
        "review_comments": comments,
    }
    if success:
        updates["l1_code"] = code
    return updates
