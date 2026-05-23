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
        f"You are a security and reliability engineer. Refactor the following Python code "
        f"to fix the specific issues identified by code review.\n\n"
        f"Original code:\n```python\n{l1_code}\n```\n\n"
        f"Issues to fix (Security & Reliability):\n{issues_text}\n\n"
        f"Rules:\n"
        f"- Fix ONLY the listed issues. Do not change unrelated logic.\n"
        f"- Preserve the original function signature and behavior.\n"
        f"- Do not add unnecessary complexity.\n\n"
        f"Return strict JSON:\n"
        f"- code: the refactored Python implementation\n"
        f"- explanation: what you changed and why\n"
        f"- applied_fixes: list of issue descriptions you addressed"
    )

    data, used_llm, note, token_count = generate_with_outlines(
        prompt=prompt,
        output_model=L2RefactorOutput,
        fallback_data=fallback.model_dump(),
    )
    output = L2RefactorOutput(**data)
    accumulated_tokens = state.get("_task_tokens", 0) + token_count
    llm_calls = state.get("_task_llm_calls", 0) + 1

    has_change = bool(output.code.strip()) and output.code.strip() != l1_code.strip()

    # Verify refactored code still passes tests; roll back on failure to prevent semantic drift.
    if has_change and test_cases:
        verify = execute_code_with_trace(output.code, test_cases)
        if not verify["passed"]:
            comments.append(
                f"{NODE_NAME}: refactored code failed tests ({verify['error']!r}), rolling back to l1_code"
            )
            output = fallback
            has_change = False

    comments.append(
        f"{NODE_NAME}: {'applied' if has_change else 'no'} security/reliability fixes "
        f"({'LLM' if used_llm else 'fallback'}), {note}"
    )

    return {
        "code": output.code if has_change else l1_code,
        "l1_code": l1_code,
        "l2_code": output.code if has_change else "",
        "l3_code": "",  # clear stale l3_code from any previous retry iteration
        "has_l2_refactor": has_change,
        "_task_tokens": accumulated_tokens,
        "_task_llm_calls": llm_calls,
        "review_comments": comments,
    }
