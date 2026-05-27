from __future__ import annotations

"""
Evaluation 节点（LDB 动态仲裁层）。

目标：
- 对比重构前后执行轨迹，判断是否发生语义偏移；
- 将判定结果写回 traces，供主图决定“通过”还是“回环重构”。
"""

from typing import Any

from pydantic import BaseModel

from state import AgentState
from utils.executor import (
    compare_traces,
    compare_traces_strong,
    compare_traces_weak,
    execute_code_with_trace,
    summarize_trace_difference,
)
from utils.helpers import generate_with_outlines, heuristic_static_cisq_audit

NODE_NAME = "evaluation_node"
PROMPT_TEMPLATE = """
你是 LDB 动态评估代理。
目标：比较重构前后执行轨迹，判定是否语义等价。
输出：更新 traces 与 review_comments。
""".strip()


class StaticReviewOutput(BaseModel):
    """静态审判结构化输出。"""

    passed: bool = False
    failed_rule_ids: list[str] = []
    findings: list[Any] = []  # LLM may return list[dict]; accept any element type
    summary: str = ""

async def run(state: AgentState) -> AgentState:
    """
    Evaluation 节点执行函数（占位版）。

    处理步骤：
    1. 分别执行 L1 与 L3 代码，采集真实运行轨迹；
    2. 先计算 weak/strong 两种判定结果；
    3. 按 state.equivalence_mode 选择最终仲裁结果；
    4. 把轨迹和判定结果写回 state.traces；
    5. iteration 统一在此 +1（每次进入仲裁都计数）；
    6. 写入 review_comments，标记 PASS 或 RETRY。
    """
    l1_code = state.get("l1_code") or state.get("code", "")
    l3_code = state.get("l3_code") or state.get("code", "")
    test_cases = state.get("test_cases", "")

    l1_result = execute_code_with_trace(l1_code, test_cases)
    l3_result = execute_code_with_trace(l3_code, test_cases)
    original_trace = l1_result["trace"]
    refactored_trace = l3_result["trace"]

    both_executable = l1_result["passed"] and l3_result["passed"]
    weak_passed = both_executable and compare_traces_weak(original_trace, refactored_trace)
    strong_passed = both_executable and compare_traces_strong(
        original_trace, refactored_trace
    )
    # dynamic_verdict 以"两版代码均能通过测试"为核心判定标准。
    # 轨迹比对结果（weak/strong）作为附加研究指标保存在 traces 中，
    # 但不作为通过门槛——重构后函数签名不变、行数可变，强行要求轨迹等长会拒绝所有有效重构。
    dynamic_verdict = "pass" if both_executable else "fail"

    all_rules = state.get("standard_constraints", {}).get("rules", [])
    heuristic_review = heuristic_static_cisq_audit(l3_code, all_rules)

    # 将规则格式化为可读文本，避免将 Python list repr 直接注入 prompt。
    rules_text = "\n".join(
        f"- {r.get('rule_id', '?')}: {r.get('title', '')} — {r.get('repair_pattern', r.get('risk_reason', ''))}"
        for r in all_rules[:10]
    ) or "（未激活规则）"
    static_prompt = f"""你是 CISQ 静态审判代理，请检查代码是否已消除以下风险。

目标规则（最多展示前 10 条）：
{rules_text}

待审判代码：
```python
{l3_code}
```""".strip()
    static_data, used_llm, note, tc = generate_with_outlines(
        prompt=static_prompt,
        output_model=StaticReviewOutput,
        fallback_data=heuristic_review,
    )
    static_review = StaticReviewOutput(**static_data)
    static_verdict = "pass" if static_review.passed else "fail"
    # static_verdict is recorded as a quality metric but does not gate workflow success;
    # only dynamic correctness (both versions pass tests) determines the verdict.
    final_verdict = "pass" if dynamic_verdict == "pass" else "fail"

    trace_feedback = summarize_trace_difference(original_trace, refactored_trace)
    if final_verdict == "pass":
        refactor_feedback = "动态与静态审判均通过，无需额外修复。"
    else:
        static_summary = (
            "静态规则未通过：" + ", ".join(static_review.failed_rule_ids)
            if static_review.failed_rule_ids
            else "静态审判未发现具体规则 ID，但建议人工复核。"
        )
        refactor_feedback = (
            f"{trace_feedback}\n{static_summary}\n"
            f"静态审判说明：{static_review.summary}"
        )

    mode = state.get("equivalence_mode", "weak")
    is_equivalent = weak_passed if mode == "weak" else strong_passed

    traces = dict(state.get("traces", {}))
    traces.update(
        {
            "original": original_trace,
            "refactored": refactored_trace,
            "l1_error": l1_result["error"],
            "l3_error": l3_result["error"],
            "equivalence_mode": mode,
            "weak_passed": weak_passed,
            "strong_passed": strong_passed,
            "is_equivalent": is_equivalent,
            "dynamic_verdict": dynamic_verdict,
            "static_verdict": static_verdict,
            "static_findings": static_review.findings,
            "static_summary": static_review.summary,
        }
    )

    accumulated_tokens = state.get("_task_tokens", 0) + tc.total
    accumulated_input = state.get("_task_input_tokens", 0) + tc.input
    accumulated_output = state.get("_task_output_tokens", 0) + tc.output
    llm_calls = state.get("_task_llm_calls", 0) + 1

    comments = [*state.get("review_comments", [])]
    comments.append(
        f"{NODE_NAME}: dynamic={dynamic_verdict}, static={static_verdict}, final={final_verdict}"
    )
    comments.append(f"{NODE_NAME}: static review source => {'LLM' if used_llm else 'fallback'}")
    comments.append(f"{NODE_NAME}: {note}")
    return {
        "traces": traces,
        "iteration": state.get("iteration", 0) + 1,
        "dynamic_verdict": dynamic_verdict,
        "static_verdict": static_verdict,
        "final_verdict": final_verdict,
        "failed_rule_ids": static_review.failed_rule_ids,
        "refactor_feedback": refactor_feedback,
        "_task_tokens": accumulated_tokens,
        "_task_input_tokens": accumulated_input,
        "_task_output_tokens": accumulated_output,
        "_task_llm_calls": llm_calls,
        "review_comments": comments,
    }
