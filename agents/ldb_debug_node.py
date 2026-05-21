from __future__ import annotations

"""
LDB 调试节点。

职责：
- 在 Green 测试失败后，调用 LLMDebugger 风格的 block tracing；
- 把失败测试、真实输出、block trace 组织成结构化调试报告；
- 将报告回传给 Green，帮助其定向修复，而不是只盯着字符串报错。
"""

from pydantic import BaseModel

from state import AgentState
from utils.helpers import generate_with_outlines
from utils.local_ldb import (
    choose_suspicious_block,
    get_ldb_block_trace,
    heuristic_ldb_block_report,
    render_block_reports_for_prompt,
    select_focus_trace_blocks,
)
from utils.ldb_prompt_protocol import (
    build_ldb_debug_history,
    build_ldb_debug_protocol_prompt,
)

NODE_NAME = "ldb_debug_node"
PROMPT_TEMPLATE = """
你是 LDB 调试代理。
目标：根据失败测试、真实输出和 block 级执行轨迹，识别最可疑的代码块并给出结构化解释。
输出：更新 ldb_debug_context 与 ldb_debug_report。
""".strip()


class BlockDebugItem(BaseModel):
    block: str = ""
    correct: bool = False
    explanation: str = ""


class LDBDebugOutput(BaseModel):
    failed_test: str = ""
    real_output: str = ""
    suspicious_block: str = ""
    block_reports: list[BlockDebugItem] = []
    summary: str = ""


async def run(state: AgentState) -> AgentState:
    """
    生成 LDB 风格 block 调试报告。
    """
    failed_test = state.get("last_failed_test", "") or state.get("test_error", "")
    real_output = state.get("last_real_output", "") or state.get("test_error", "")
    code = state.get("code", "")
    entry_point = state.get("entry_point", "solve")

    ldb_result = get_ldb_block_trace(
        code=code,
        failed_test=failed_test,
        entry_point=entry_point,
    )

    trace_blocks = ldb_result["trace_blocks"]
    fallback = heuristic_ldb_block_report(
        failed_test=failed_test,
        real_output=real_output,
        trace_blocks=trace_blocks,
    )

    focused_blocks = select_focus_trace_blocks(trace_blocks, max_blocks=10, max_lines_per_block=16)
    fallback_payload = {
        "failed_test": fallback["failed_test"],
        "real_output": fallback["real_output"],
        "suspicious_block": fallback["suspicious_block"],
        "block_reports": [
            item
            for item in fallback["block_reports"]
            if item["block"] in {block["block"] for block in focused_blocks}
        ]
        or fallback["block_reports"],
        "summary": fallback["summary"],
    }

    debug_prompt = build_ldb_debug_protocol_prompt(
        failed_test=failed_test,
        real_output=real_output,
        code=code,
        trace_blocks=focused_blocks,
    )
    data, used_llm, note = generate_with_outlines(
        prompt=debug_prompt,
        output_model=LDBDebugOutput,
        fallback_data=fallback_payload,
    )
    debug_output = LDBDebugOutput(**data)

    if not debug_output.block_reports:
        debug_output = LDBDebugOutput(**fallback_payload)

    suspicious_block = debug_output.suspicious_block or choose_suspicious_block(trace_blocks)
    block_feedback_text = render_block_reports_for_prompt(
        [item.model_dump() for item in debug_output.block_reports],
        max_reports=6,
    )
    debug_history = build_ldb_debug_history(
        failed_test=debug_output.failed_test,
        real_output=debug_output.real_output,
        trace_blocks=focused_blocks,
        block_feedback_text=block_feedback_text,
    )
    previous_sessions = list(state.get("ldb_debug_sessions", []) or [])
    merged_sessions = [*previous_sessions, debug_history][-3:]
    debug_context = (
        f"失败测试: {debug_output.failed_test}\n"
        f"真实输出: {debug_output.real_output}\n"
        f"最可疑 block: {suspicious_block}\n"
        f"调试摘要: {debug_output.summary}\n"
        f"逐块反馈:\n{block_feedback_text or '无'}\n"
        f"LDB Debug History:\n{debug_history}"
    )

    comments = [*state.get("review_comments", [])]
    comments.append(
        f"{NODE_NAME}: generated LDB-style debug session ({'LLM' if used_llm else 'fallback'})"
    )
    comments.append(f"{NODE_NAME}: {note}")
    if ldb_result["error"]:
        comments.append(f"{NODE_NAME}: trace note => {ldb_result['error']}")

    return {
        "ldb_debug_context": debug_context,
        "ldb_debug_report": {
            **debug_output.model_dump(),
            "suspicious_block": suspicious_block,
            "debug_history": debug_history,
            "focused_trace_blocks": focused_blocks,
        },
        "ldb_debug_sessions": merged_sessions,
        "review_comments": comments,
    }
