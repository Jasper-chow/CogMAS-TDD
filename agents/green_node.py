from __future__ import annotations

"""
Green 阶段节点（功能实现）。

目标：
- 尽快让 Red 阶段测试通过；
- 当前不强调架构优雅，重点是功能可用。
"""

from pydantic import BaseModel

from state import AgentState
from utils.helpers import generate_with_outlines
from utils.local_ldb import render_block_reports_for_prompt
from utils.ldb_prompt_protocol import (
    build_cumulative_ldb_history,
    build_ldb_repair_prompt,
)

NODE_NAME = "green_node"
PROMPT_TEMPLATE = """
你是 Green 阶段实现代理。
目标：最短路径通过测试，不做过度优化。
输出：更新 code。
""".strip()


class GreenNodeOutput(BaseModel):
    """Green 结构化输出：只负责实现代码，不承载测试代码。"""

    code: str
    explanation: str = ""


async def run(state: AgentState) -> AgentState:
    """
    Green 节点执行函数（占位版）。

    输入：
    - state.code: 当前代码。

    输出：
    - code: 若为空则生成最小可执行实现。
    - green_output: 结构化结果（code/explanation）。
    - green_attempts: 每次进入 Green 都 +1。
    - review_comments: 写入阶段日志。

    说明：
    - iteration 不在 Green 阶段递增，统一由 Evaluation 阶段计数，
      以确保 L2 -> L3 -> Evaluation 回环时计数持续增长。
    """
    code = state.get("code", "")
    previous_error = state.get("test_error", "")
    ldb_debug_context = state.get("ldb_debug_context", "")
    ldb_debug_report = state.get("ldb_debug_report", {}) or {}
    suspicious_block = str(ldb_debug_report.get("suspicious_block", "")).strip()
    block_reports = ldb_debug_report.get("block_reports", []) or []
    block_feedback_text = render_block_reports_for_prompt(block_reports, max_reports=6)
    debug_history = str(ldb_debug_report.get("debug_history", "")).strip()
    cumulative_history = build_cumulative_ldb_history(
        list(state.get("ldb_debug_sessions", []) or []),
        max_histories=3,
    )
    hide_tests = state.get("hide_tests_in_green", False)
    fallback_code = code or "def placeholder_impl() -> bool:\n    return True\n"
    explanation = "占位实现：已提供最小可执行功能代码。"
    if previous_error:
        explanation = f"根据上一轮测试错误进行重试：{previous_error[:160]}"
    if suspicious_block:
        explanation += f" 优先检查 {suspicious_block} 对应逻辑。"
    fallback = GreenNodeOutput(code=fallback_code, explanation=explanation)

    if not code:
        # Initial generation — no existing code to repair, use a direct generation prompt.
        test_section = "" if hide_tests else state.get("test_cases", "")
        entry_point = state.get("entry_point", "")
        entry_hint = f"\nThe function MUST be named `{entry_point}`." if entry_point else ""
        prompt = (
            f"You are an expert Python programmer.\n\n"
            f"Task:\n{state.get('requirement', 'No requirement provided.')}{entry_hint}\n\n"
            f"Tests:\n```python\n{test_section or '# no tests provided'}\n```\n\n"
            f"Write a complete Python function that passes all tests.\n"
            f"Return strict JSON with:\n"
            f"- code: the complete Python implementation\n"
            f"- explanation: brief description of your approach"
        )
    else:
        # Always anchor on the raw test error, then append richer LDB context if available.
        # Using `or` would silently drop test_error when LDB runs, which hurts small models.
        test_error_ctx = state.get("test_error", "")
        ldb_context = cumulative_history or debug_history or ldb_debug_context or block_feedback_text

        if ldb_context:
            # LDB block trace is available — use the full LDB repair protocol.
            if test_error_ctx and ldb_context:
                effective_debug_history = f"Test error:\n{test_error_ctx}\n\n{ldb_context}"
            else:
                effective_debug_history = ldb_context or (f"Test error:\n{test_error_ctx}" if test_error_ctx else "")
            prompt = build_ldb_repair_prompt(
                requirement=state.get("requirement", ""),
                code=code,
                test_cases="" if hide_tests else state.get("test_cases", ""),
                debug_history=effective_debug_history,
                suspicious_block=suspicious_block,
            )
        else:
            # No LDB context — use a lightweight error-driven repair prompt.
            # The heavy LDB few-shot example bloats the prompt unnecessarily for small models.
            error_section = f"\nError from last run:\n{test_error_ctx}" if test_error_ctx else ""
            test_section = "" if hide_tests else state.get("test_cases", "")
            entry_point = state.get("entry_point", "")
            entry_hint = f"\nThe function MUST be named `{entry_point}`." if entry_point else ""
            prompt = (
                f"You are an expert Python programmer. Fix the following code so it passes the tests.\n\n"
                f"Task:\n{state.get('requirement', 'No requirement provided.')}{entry_hint}"
                f"{error_section}\n\n"
                f"Current code:\n```python\n{code}\n```\n\n"
                f"Tests:\n```python\n{test_section or '# no tests provided'}\n```\n\n"
                f"Return strict JSON with:\n"
                f"- code: the complete corrected Python implementation\n"
                f"- explanation: brief description of what you fixed"
            )
    data, used_llm, note = generate_with_outlines(
        prompt=prompt,
        output_model=GreenNodeOutput,
        fallback_data=fallback.model_dump(),
    )
    output = GreenNodeOutput(**data)
    return {
        "code": output.code,
        "green_output": output.model_dump(),
        "green_attempts": state.get("green_attempts", 0) + 1,
        "review_comments": [
            *state.get("review_comments", []),
            f"{NODE_NAME}: implementation updated with LDB repair protocol ({'LLM' if used_llm else 'fallback'})",
            f"{NODE_NAME}: {note}",
        ],
    }
