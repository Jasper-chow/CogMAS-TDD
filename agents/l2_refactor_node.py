from __future__ import annotations

"""
L2 重构节点（安全与可靠性加固层）。

目标：
- 消费 code_review_node 产出的 security / reliability findings；
- 针对 CR 发现的具体问题定向修复，而非套用通用规则；
- 保存 l1_code 基线，供 Evaluation 做语义等价比对。
"""

from pydantic import BaseModel

from state import AgentState
from utils.executor import execute_code_with_trace
from utils.helpers import generate_with_outlines

NODE_NAME = "l2_refactor_node"


class L2RefactorOutput(BaseModel):
    code: str
    explanation: str = ""
    applied_fixes: list[str] = []


def _extract_findings(code_review_report: dict) -> tuple[list[str], list[str]]:
    """从 CR 报告中提取 security + reliability 的 findings 和 suggestions。"""
    findings: list[str] = []
    suggestions: list[str] = []
    for dim in ("security", "reliability"):
        dim_report = code_review_report.get(dim, {})
        findings.extend(dim_report.get("findings", []))
        suggestions.extend(dim_report.get("suggestions", []))
    return findings, suggestions


async def run(state: AgentState) -> AgentState:
    current_code = state.get("code", "")
    l1_code = state.get("l1_code") or current_code
    comments = list(state.get("review_comments", []))
    test_cases = state.get("test_cases", "")

    cr_report = state.get("code_review_report", {})
    findings, suggestions = _extract_findings(cr_report)

    if not findings or not current_code:
        msg = (
            "no security/reliability findings from CR, skipping"
            if cr_report
            else "no CR report available, skipping"
        )
        comments.append(f"{NODE_NAME}: {msg}")
        # Clear stale l3_code from any previous retry iteration.
        return {"l1_code": l1_code, "l3_code": "", "review_comments": comments}

    issues_text = "\n".join(
        f"- Issue: {f}\n  Fix: {s}" for f, s in zip(findings, suggestions or [""] * len(findings))
    )

    fallback = L2RefactorOutput(
        code=l1_code,
        explanation="L2 fallback: code unchanged (LLM unavailable or parse error)",
        applied_fixes=[],
    )

    prompt = (
        f"You are a reliability engineer. Refactor the following Python function "
        f"to fix the specific issues identified by code review.\n\n"
        f"Original code:\n```python\n{l1_code}\n```\n\n"
        f"Issues to fix (Reliability):\n{issues_text}\n\n"
        f"CRITICAL RULES — violating any of these means the refactor is rejected:\n"
        f"1. Fix ONLY the listed issues. Do not change unrelated logic, variable names, or function signatures.\n"
        f"2. Start from the original code. Apply the minimum edit needed to address each listed issue.\n"
        f"3. Preserve ALL existing import statements, helper functions, and type annotations.\n"
        f"4. Do not add new imports, new functions, or new abstractions unless a finding explicitly demands it.\n"
        f"5. The refactored code must compile and pass the same tests as the original.\n"
        f"6. Do NOT add input validation, try/except blocks, or raise statements unless a finding "
        f"explicitly identifies a missing guard for a bug that would occur with valid inputs.\n"
        f"7. Do NOT replace idiomatic Python (list comprehensions, built-in functions like max/min/sum) "
        f"with verbose loop equivalents — that worsens readability without fixing anything.\n"
        f"8. Do NOT rename variables or rewrite correct logic that is unrelated to the listed issues.\n"
        f"9. Do NOT use 'assert' as a runtime guard — assert statements are disabled when Python runs "
        f"with the -O flag and must not be used for correctness-critical checks. "
        f"If a finding requires removing an existing assert, replace it with a proper conditional check only "
        f"if the assert guards against a bug that can actually occur.\n\n"
        f"Return strict JSON:\n"
        f"- code: the refactored Python implementation (complete, compilable code)\n"
        f"- explanation: what you changed and why (one sentence per fix)\n"
        f"- applied_fixes: list of issue descriptions you addressed (same count as findings if all fixed)"
    )

    data, used_llm, note, tc = generate_with_outlines(
        prompt=prompt,
        output_model=L2RefactorOutput,
        fallback_data=fallback.model_dump(),
    )
    output = L2RefactorOutput(**data)
    accumulated_tokens = state.get("_task_tokens", 0) + tc.total
    accumulated_input = state.get("_task_input_tokens", 0) + tc.input
    accumulated_output = state.get("_task_output_tokens", 0) + tc.output
    llm_calls = state.get("_task_llm_calls", 0) + 1

    has_change = bool(output.code.strip()) and output.code.strip() != l1_code.strip()
    resolved_count = len(output.applied_fixes) if has_change else 0
    prev_resolved = state.get("cr_findings_resolved", 0) + resolved_count

    if has_change and test_cases:
        verify = execute_code_with_trace(output.code, test_cases)
        if not verify["passed"]:
            comments.append(
                f"{NODE_NAME}: refactored code failed tests ({verify['error']!r}), rolling back to l1_code"
            )
            output = fallback
            has_change = False
            prev_resolved = state.get("cr_findings_resolved", 0)

    comments.append(
        f"{NODE_NAME}: {'applied' if has_change else 'no'} security/reliability fixes "
        f"({'LLM' if used_llm else 'fallback'}), resolved={resolved_count}/{len(findings)}, {note}"
    )

    return {
        "code": output.code if has_change else l1_code,
        "l1_code": l1_code,
        "l2_code": output.code if has_change else "",
        "l3_code": "",
        "has_l2_refactor": has_change,
        "cr_findings_resolved": prev_resolved,
        "_task_tokens": accumulated_tokens,
        "_task_input_tokens": accumulated_input,
        "_task_output_tokens": accumulated_output,
        "_task_llm_calls": llm_calls,
        "review_comments": comments,
    }
