from __future__ import annotations

"""
Code Review Node — 认知分层代码审查。

职责：
- 对功能测试通过的代码进行多维度质量审查（CISQ 四维度）；
- 每个维度由独立的 Reviewer 打分，给出具体 findings 与改进建议；
- Evaluation Agent 对所有 findings 做幻觉过滤，剔除代码里不存在的虚假发现；
- 输出结构化 CodeReviewReport，供下游 L2/L3 重构节点精准消费。

设计参考：
- 多维度独立 Reviewer 借鉴 CogMAS 的认知对齐多教师架构；
- 幻觉过滤借鉴 CogMAS 的 Evaluation Agent 推理路径核验；
- 每个 Reviewer 注入对应维度的 CISQ 标准规则（来自 Python 专项子集）；
- cr_few_shot_examples 字段预留给双阶段语义检索模块（第二步实现）。
"""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from state import AgentState
from utils.helpers import generate_with_outlines

NODE_NAME = "code_review_node"

# ── 维度映射：Characteristic 字段值 → 内部 key ─────────────────────────────────
_CHAR_TO_DIM: dict[str, str] = {
    "Security": "security",
    "Reliability": "reliability",
    "Maintainability": "maintainability",
    "Performance Efficiency": "performance_efficiency",
}

# ── 在模块加载时读取 CISQ Python 专项子集规则 ──────────────────────────────────────
def _load_cisq_rules() -> dict[str, list[dict[str, str]]]:
    """加载 Python 专项 CISQ 规则，按维度分组。"""
    rules_by_dim: dict[str, list[dict[str, str]]] = {
        "security": [],
        "reliability": [],
        "maintainability": [],
        "performance_efficiency": [],
    }
    subset_path = Path(__file__).parent.parent / "knowledge" / "CISQ_mapping_python_benchmark_subset.json"
    if not subset_path.exists():
        return rules_by_dim
    try:
        with subset_path.open(encoding="utf-8") as f:
            raw: list[dict[str, str]] = json.load(f)
        for item in raw:
            dim_key = _CHAR_TO_DIM.get(item.get("Characteristic", ""))
            if dim_key:
                rules_by_dim[dim_key].append(item)
    except Exception:
        pass
    return rules_by_dim


_CISQ_RULES: dict[str, list[dict[str, str]]] = _load_cisq_rules()


def _format_cisq_rules(dim: str) -> str:
    """将某维度的 CISQ 规则格式化为 Reviewer prompt 中可嵌入的文本块。"""
    rules = _CISQ_RULES.get(dim, [])
    if not rules:
        return ""
    lines = ["CISQ standard rules to check against (reference only — only flag issues you can see in the code):"]
    for r in rules:
        lines.append(f"  • CWE-{r['CWE_ID']} [{r['Description']}]: {r['Refactor_Advice']}")
    return "\n".join(lines)


_DIMENSION_GUIDES: dict[str, dict[str, str]] = {
    "security": {
        "label": "Security",
        "concerns": (
            "injection vulnerabilities, hardcoded secrets, unsafe input handling, "
            "sensitive data exposure, improper authentication or authorization checks"
        ),
    },
    "reliability": {
        "label": "Reliability",
        "concerns": (
            "unhandled exceptions, missing None or boundary checks, resource leaks, "
            "incorrect edge-case handling, fragile assumptions about input values"
        ),
    },
    "maintainability": {
        "label": "Maintainability",
        "concerns": (
            "high cyclomatic complexity, dead code, overly long functions, "
            "poor variable naming, duplicated logic, unexplained magic numbers"
        ),
    },
    "performance_efficiency": {
        "label": "Performance Efficiency",
        "concerns": (
            "unnecessary nested loops, repeated computation inside loops, "
            "inefficient data structures, redundant passes over the same data"
        ),
    },
}


class DimensionReview(BaseModel):
    score: int = 5                  # 1 (poor) → 5 (excellent, no issues)
    findings: list[str] = []        # specific issues referencing actual code lines/patterns
    suggestions: list[str] = []     # one concrete fix per finding
    severity: str = "none"          # "critical" | "moderate" | "minor" | "none"
    needs_refactoring: bool = False


class CodeReviewReport(BaseModel):
    security: DimensionReview = DimensionReview()
    reliability: DimensionReview = DimensionReview()
    maintainability: DimensionReview = DimensionReview()
    performance_efficiency: DimensionReview = DimensionReview()
    overall_score: float = 5.0
    needs_refactoring: bool = False
    review_summary: str = ""


async def _review_single_dimension(
    code: str,
    requirement: str,
    dimension: str,
    guide: dict[str, str],
    few_shot: str = "",
) -> tuple[DimensionReview, int]:
    """独立的单维度 Reviewer — 只关注自己负责的 CISQ 维度。"""
    few_shot_section = (
        f"\n\nHigh-quality reference for a similar task (use as calibration standard):\n{few_shot}"
        if few_shot
        else ""
    )

    cisq_section = _format_cisq_rules(dimension)
    cisq_block = f"\n\n{cisq_section}" if cisq_section else ""

    prompt = (
        f"You are a code quality reviewer specializing in {guide['label']}.\n\n"
        f"Task requirement: {requirement}\n\n"
        f"Code to review:\n```python\n{code}\n```"
        f"{few_shot_section}"
        f"{cisq_block}\n\n"
        f"Review ONLY for {guide['label']} issues.\n"
        f"Key concerns: {guide['concerns']}\n\n"
        f"Important rules:\n"
        f"- Each finding MUST reference a specific line or pattern visible in the code above.\n"
        f"- Do NOT invent issues that cannot be seen in the code.\n"
        f"- Score 5 = no issues found. Score 1 = critical problems.\n"
        f"- needs_refactoring should be true only if score is 3 or below.\n\n"
        f"Return strict JSON:\n"
        f"- score: integer 1-5\n"
        f"- findings: list of specific issues (empty list if none)\n"
        f"- suggestions: list of concrete fixes, same length as findings\n"
        f"- severity: 'critical', 'moderate', 'minor', or 'none'\n"
        f"- needs_refactoring: boolean"
    )

    fallback = DimensionReview(
        score=4, findings=[], suggestions=[], severity="none", needs_refactoring=False
    )
    data, _, _, token_count = generate_with_outlines(
        prompt=prompt,
        output_model=DimensionReview,
        fallback_data=fallback.model_dump(),
    )
    return DimensionReview(**data), token_count


async def _verify_findings(
    code: str,
    dimension_label: str,
    review: DimensionReview,
) -> tuple[DimensionReview, int]:
    """
    Evaluation Agent：对单个维度的 findings 做幻觉过滤。

    批量核验 — 一次 LLM 调用检查该维度所有 findings，
    只保留能在代码中找到具体证据的条目。
    """
    if not review.findings:
        return review, 0

    numbered = "\n".join(f"{i + 1}. {f}" for i, f in enumerate(review.findings))

    class VerificationResult(BaseModel):
        # 1-based indices of findings that genuinely exist in the code
        verified_indices: list[int] = []

    prompt = (
        f"You are verifying whether {dimension_label} findings actually exist in this code.\n\n"
        f"Code:\n```python\n{code}\n```\n\n"
        f"Findings to verify:\n{numbered}\n\n"
        f"For each finding number, decide: can you point to a specific line or pattern "
        f"in the code above that demonstrates this issue?\n"
        f"Return JSON with verified_indices: list of finding numbers (1-based) "
        f"that are genuinely present in the code. Omit numbers for findings you cannot verify."
    )

    # Conservative fallback: keep all findings (better to over-report than lose real ones)
    fallback = VerificationResult(verified_indices=list(range(1, len(review.findings) + 1)))
    data, _, _, token_count = generate_with_outlines(
        prompt=prompt,
        output_model=VerificationResult,
        fallback_data=fallback.model_dump(),
    )
    result = VerificationResult(**data)

    kept_idx = [i - 1 for i in result.verified_indices if 1 <= i <= len(review.findings)]
    verified_findings = [review.findings[i] for i in kept_idx]
    suggestions_src = (
        review.suggestions
        if len(review.suggestions) == len(review.findings)
        else [""] * len(review.findings)
    )
    verified_suggestions = [suggestions_src[i] for i in kept_idx]

    return DimensionReview(
        score=review.score,
        findings=verified_findings,
        suggestions=verified_suggestions,
        severity=review.severity if verified_findings else "none",
        needs_refactoring=bool(verified_findings) and review.score <= 3,
    ), token_count


async def run(state: AgentState) -> AgentState:
    """
    Code Review 主流程。

    输入：
    - state.code: 已通过功能测试的代码
    - state.requirement: 任务需求
    - state.cr_few_shot_examples: 检索到的高质量参考案例（可为空）

    输出：
    - code_review_report: 结构化四维度审查报告
    - review_comments: 各维度简报写入日志
    """
    code = state.get("code", "")
    requirement = state.get("requirement", "")
    comments = list(state.get("review_comments", []))

    if not code:
        comments.append(f"{NODE_NAME}: no code to review, skipping")
        return {"review_comments": comments}

    # cr_few_shot_examples 由检索模块填充（第二步），当前为空字符串
    few_shot = state.get("cr_few_shot_examples", "")

    accumulated_tokens = state.get("_task_tokens", 0)
    llm_calls = state.get("_task_llm_calls", 0)

    reviews: dict[str, DimensionReview] = {}
    for dim, guide in _DIMENSION_GUIDES.items():
        review_raw, tc_review = await _review_single_dimension(code, requirement, dim, guide, few_shot)
        accumulated_tokens += tc_review
        llm_calls += 1
        had_findings = bool(review_raw.findings)
        review_verified, tc_verify = await _verify_findings(code, guide["label"], review_raw)
        accumulated_tokens += tc_verify
        if had_findings:
            llm_calls += 1
        reviews[dim] = review_verified
        comments.append(
            f"{NODE_NAME}: [{guide['label']}] score={review_verified.score}, "
            f"findings={len(review_verified.findings)}, needs_refactor={review_verified.needs_refactoring}"
        )

    scores = [r.score for r in reviews.values()]
    overall = round(sum(scores) / len(scores), 2)
    needs_refactor = any(r.needs_refactoring for r in reviews.values())
    weak_dims = [_DIMENSION_GUIDES[d]["label"] for d, r in reviews.items() if r.needs_refactoring]

    summary = (
        f"Overall quality: {overall}/5. "
        + (f"Needs improvement in: {', '.join(weak_dims)}." if weak_dims else "No major issues found.")
    )
    comments.append(f"{NODE_NAME}: {summary}")

    report = CodeReviewReport(
        security=reviews["security"],
        reliability=reviews["reliability"],
        maintainability=reviews["maintainability"],
        performance_efficiency=reviews["performance_efficiency"],
        overall_score=overall,
        needs_refactoring=needs_refactor,
        review_summary=summary,
    )

    return {
        "code_review_report": report.model_dump(),
        "review_comments": comments,
        "_task_tokens": accumulated_tokens,
        "_task_llm_calls": llm_calls,
    }
