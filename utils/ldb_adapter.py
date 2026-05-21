from __future__ import annotations

"""
LLMDebugger 迁移适配层。

目标：
- 复用 LLMDebugger 的 block 级 trace 思路，而不是整套工程直接硬拷贝；
- 对当前 CogMAS-TDD 暴露稳定接口；
- 若 LLMDebugger 源码或依赖不可用，优雅降级而不是中断主流程。
"""

import importlib
import sys
from pathlib import Path
from typing import Any

DEFAULT_IMPORT_HEADER = (
    "from typing import *\n"
    "import math\n"
    "from heapq import *\n"
    "import itertools\n"
    "import re\n"
    "import typing\n"
    "import heapq\n"
    "_str=str\n"
    "import re\n"
)


def _get_ldb_programming_root() -> Path:
    return Path(__file__).resolve().parent.parent / "LLMDebugger" / "programming"


def _load_tracer_module():
    """按需加载 LLMDebugger 的 tracing.tracer 模块。"""
    root = _get_ldb_programming_root()
    if not root.exists():
        raise FileNotFoundError(f"LLMDebugger not found: {root}")

    root_str = str(root)
    inserted = False
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
        inserted = True
    try:
        module = importlib.import_module("tracing.tracer")
        return module
    finally:
        if inserted:
            try:
                sys.path.remove(root_str)
            except ValueError:
                pass


def get_ldb_block_trace(
    *,
    code: str,
    failed_test: str,
    entry_point: str,
) -> dict[str, Any]:
    """
    使用 LLMDebugger 的 block tracing 获取运行时块级上下文。

    返回：
    - ok: 是否成功
    - trace_blocks: block 列表
    - error: 错误信息
    """
    if not code or not failed_test:
        return {
            "ok": False,
            "trace_blocks": [],
            "error": "missing code or failed_test for LDB tracing",
        }

    try:
        tracer = _load_tracer_module()
        call_expr = failed_test.replace("assert ", "").split("==")[0].strip()
        trace_blocks = tracer.get_code_traces_block(
            DEFAULT_IMPORT_HEADER + code, call_expr, entry_point
        )
        if isinstance(trace_blocks, str):
            return {"ok": False, "trace_blocks": [], "error": trace_blocks}
        return {"ok": True, "trace_blocks": trace_blocks, "error": ""}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "trace_blocks": [], "error": f"ldb adapter error: {exc}"}


def render_trace_blocks_for_prompt(
    trace_blocks: list[list[str]], *, max_blocks: int = 8, max_lines_per_block: int = 12
) -> str:
    """把 block trace 渲染成适合提示词消费的文本。"""
    if not trace_blocks:
        return ""

    selected_blocks = trace_blocks
    if len(selected_blocks) > max_blocks:
        half = max_blocks // 2
        selected_blocks = selected_blocks[:half] + selected_blocks[-half:]

    rendered: list[str] = []
    for index, block in enumerate(selected_blocks):
        block_lines = block[:max_lines_per_block]
        if len(block) > max_lines_per_block:
            block_lines = block_lines + ["..."]
        rendered.append(f"[BLOCK-{index}]\n" + "\n".join(block_lines))
    return "\n".join(rendered)


def heuristic_ldb_block_report(
    *,
    failed_test: str,
    real_output: str,
    trace_blocks: list[list[str]],
) -> dict[str, Any]:
    """
    在 LLM 不可用时提供一个最小可运行的 block 调试报告。
    """
    if not trace_blocks:
        return {
            "failed_test": failed_test,
            "real_output": real_output,
            "suspicious_block": "BLOCK-0",
            "block_reports": [
                {
                    "block": "BLOCK-0",
                    "correct": False,
                    "explanation": "未获取到可用 block trace，请先检查失败测试与入口函数。",
                }
            ],
            "summary": "LDB block trace 不可用，建议回退到错误信息驱动修复。",
        }

    suspicious_index = min(1, len(trace_blocks) - 1)
    return {
        "failed_test": failed_test,
        "real_output": real_output,
        "suspicious_block": f"BLOCK-{suspicious_index}",
        "block_reports": [
            {
                "block": f"BLOCK-{suspicious_index}",
                "correct": False,
                "explanation": (
                    "该 block 在失败测试对应路径上最值得优先检查。"
                    " 请结合其中的变量快照与测试期望，核对条件判断与返回值。"
                ),
            }
        ],
        "summary": "已生成启发式 LDB 调试报告，请优先检查可疑 block。",
    }
