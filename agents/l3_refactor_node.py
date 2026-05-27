from __future__ import annotations

"""
L3 重构节点（可维护性与性能优化层）。

目标：
- 消费 code_review_node 产出的 maintainability / performance_efficiency findings；
- 针对 CR 发现的具体问题定向优化，而非套用通用规则；
- 设置 l3_code 供 Evaluation 与 l1_code 进行语义等价比对。
"""

from pydantic import BaseModel

from state import AgentState
from utils.executor import execute_code_with_trace
from utils.helpers import generate_with_outlines

NODE_NAME = "l3_refactor_node"


class L3RefactorOutput(BaseModel):
    code: str
    explanation: str = ""
    applied_fixes: list[str] = []


def _extract_findings(code_review_report: dict) -> tuple[list[str], list[str]]:
    """从 CR 报告中提取 maintainability + performance_efficiency 的 findings 和 suggestions。"""
    findings: list[str] = []
    suggestions: list[str] = []
    for dim in ("maintainability", "performance_efficiency"):
        dim_report = code_review_report.get(dim, {})
        findings.extend(dim_report.get("findings", []))
        suggestions.extend(dim_report.get("suggestions", []))
    return findings, suggestions


async def run(state: AgentState) -> AgentState:
    current_code = state.get("code", "")
    comments = list(state.get("review_comments", []))
    test_cases = state.get("test_cases", "")

    cr_report = state.get("code_review_report", {})
    findings, suggestions = _extract_findings(cr_report)

    if not findings or not current_code:
        msg = (
            "no maintainability/performance findings from CR, skipping"
            if cr_report
            else "no CR report available, skipping"
        )
        comments.append(f"{NODE_NAME}: {msg}")
        # Explicit pass-through: l3_code = current_code (L2 output or l1_code), no LLM call.
        return {"l3_code": current_code, "review_comments": comments}

    issues_text = "\n".join(
        f"- Issue: {f}\n  Fix: {s}" for f, s in zip(findings, suggestions or [""] * len(findings))
    )

    fallback = L3RefactorOutput(
        code=current_code,
        explanation="L3 fallback: code unchanged (LLM unavailable or parse error)",
        applied_fixes=[],
    )

    prompt = (
        f"You are a software architect focused on code quality. Refactor the following Python function "
        f"to fix the specific maintainability and performance issues identified by code review.\n\n"
        f"Code to refactor:\n```python\n{current_code}\n```\n\n"
        f"Issues to fix (Maintainability & Performance):\n{issues_text}\n\n"
        f"CRITICAL RULES — violating any of these means the refactor is rejected:\n"
        f"1. Fix ONLY the listed issues. Do not change unrelated logic, variable names, or function signatures.\n"
        f"2. Start from the original code. Apply the minimum edit needed to address each listed issue.\n"
        f"3. Preserve ALL existing import statements, helper functions, and type annotations.\n"
        f"4. Do not add new imports, new functions, or new abstractions unless a finding explicitly demands it.\n"
        f"5. The refactored code must compile and pass the same tests as the original.\n"
        f"6. For complexity (CWE-1121): the ONLY acceptable fix is replacing a long if-elif chain "
        f"(5+ branches) with a dictionary lookup. Do NOT use guard clauses, early returns, or any other "
        f"restructuring — adding new 'if' or 'continue' statements increases cognitive complexity.\n"
        f"7. For performance: hoist an invariant expression out of a loop by assigning it to a variable "
        f"before the loop. Do NOT change correct O(n) code to a different O(n) implementation.\n"
        f"8. Do NOT replace idiomatic Python (list comprehensions, built-in max/min/sum/sorted) with "
        f"verbose loop equivalents.\n"
        f"9. Do NOT add input validation, try/except, or raise statements.\n"
        f"10. Do NOT rename variables that are already clear and correctly used.\n"
        f"11. If the code contains a manual loop that exactly replicates a Python builtin "
        f"(a loop to find max/min, sum all elements, or check if any/all satisfy a condition), "
        f"replace it with the builtin (max(), min(), sum(), any(), all()). "
        f"Only do this when the builtin captures the intent with no behavioural change.\n"
        f"12. LINE COUNT GUARD: your refactored code must have the same number of lines or fewer "
        f"than the original. If applying a fix would require adding new lines, do NOT apply it — "
        f"return the original code unchanged for that finding.\n"
        f"13. BRANCH COUNT GUARD: do NOT add any new if/elif/else/for/while/with statement that "
        f"does not exist in the original code. Structural additions increase cognitive complexity.\n\n"
        f"Return strict JSON:\n"
        f"- code: the refactored Python implementation (complete, compilable code)\n"
        f"- explanation: what you changed and why (one sentence per fix)\n"
        f"- applied_fixes: list of issue descriptions you addressed (same count as findings if all fixed)"
    )

    data, used_llm, note, tc = generate_with_outlines(
        prompt=prompt,
        output_model=L3RefactorOutput,
        fallback_data=fallback.model_dump(),
    )
    output = L3RefactorOutput(**data)
    accumulated_tokens = state.get("_task_tokens", 0) + tc.total
    accumulated_input = state.get("_task_input_tokens", 0) + tc.input
    accumulated_output = state.get("_task_output_tokens", 0) + tc.output
    llm_calls = state.get("_task_llm_calls", 0) + 1

    has_change = bool(output.code.strip()) and output.code.strip() != current_code.strip()
    resolved_count = len(output.applied_fixes) if has_change else 0
    prev_resolved = state.get("cr_findings_resolved", 0) + resolved_count

    if has_change and test_cases:
        verify = execute_code_with_trace(output.code, test_cases)
        if not verify["passed"]:
            comments.append(
                f"{NODE_NAME}: refactored code failed tests ({verify['error']!r}), rolling back to pre-L3 code"
            )
            output.code = current_code
            has_change = False
            prev_resolved = state.get("cr_findings_resolved", 0)

    comments.append(
        f"{NODE_NAME}: {'applied' if has_change else 'no'} maintainability/performance fixes "
        f"({'LLM' if used_llm else 'fallback'}), resolved={resolved_count}/{len(findings)}, {note}"
    )

    return {
        "code": output.code if has_change else current_code,
        "l3_code": output.code if has_change else current_code,
        "has_l3_refactor": has_change,
        "cr_findings_resolved": prev_resolved,
        "_task_tokens": accumulated_tokens,
        "_task_input_tokens": accumulated_input,
        "_task_output_tokens": accumulated_output,
        "_task_llm_calls": llm_calls,
        "review_comments": comments,
    }
