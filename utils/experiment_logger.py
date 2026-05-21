from __future__ import annotations

"""
实验结果记录工具。

目标：
- 为 baseline / ablation / ours 提供统一 JSONL 结果落盘；
- 让后续论文统计、画表、做消融不需要再从终端日志里手抄结果；
- 记录“配置 + 状态摘要 + 关键指标”，而不是整份大状态。
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from state import AgentState


def _extract_cr_metrics(cr_report: dict) -> dict[str, Any]:
    """从 CodeReviewReport 提取论文所需的质量指标。"""
    if not cr_report:
        return {
            "cr_overall_score": None,
            "cr_security_score": None,
            "cr_reliability_score": None,
            "cr_maintainability_score": None,
            "cr_performance_score": None,
            "cr_needs_refactoring": None,
            "cr_total_findings": None,
        }
    return {
        "cr_overall_score": cr_report.get("overall_score"),
        "cr_security_score": cr_report.get("security", {}).get("score"),
        "cr_reliability_score": cr_report.get("reliability", {}).get("score"),
        "cr_maintainability_score": cr_report.get("maintainability", {}).get("score"),
        "cr_performance_score": cr_report.get("performance_efficiency", {}).get("score"),
        "cr_needs_refactoring": cr_report.get("needs_refactoring"),
        "cr_total_findings": sum(
            len(cr_report.get(dim, {}).get("findings", []))
            for dim in ("security", "reliability", "maintainability", "performance_efficiency")
        ),
    }


def summarize_run(
    *,
    state: AgentState,
    runtime_config: dict[str, Any],
    profile_name: str,
) -> dict[str, Any]:
    """把最终状态压缩成适合实验统计的一条记录。"""
    traces = state.get("traces", {})
    comments = state.get("review_comments", [])
    cr_metrics = _extract_cr_metrics(state.get("code_review_report", {}))

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "profile_name": profile_name,
        "run_id": state.get("run_id", ""),
        "dataset_name": state.get("dataset_name", ""),
        "task_id": state.get("task_id", ""),
        "workflow_status": state.get("workflow_status", ""),
        "stop_reason": state.get("stop_reason", ""),
        "test_passed": state.get("test_passed", False),
        "green_attempts": state.get("green_attempts", 0),
        "same_error_streak": state.get("same_error_streak", 0),
        "iteration": state.get("iteration", 0),
        "dynamic_verdict": state.get("dynamic_verdict", "unknown"),
        "static_verdict": state.get("static_verdict", "unknown"),
        "final_verdict": state.get("final_verdict", "unknown"),
        "enabled_agents": [
            name
            for name, settings in runtime_config.get("agents", {}).items()
            if settings.get("enabled", False)
        ],
        "weak_passed": traces.get("weak_passed"),
        "strong_passed": traces.get("strong_passed"),
        "is_equivalent": traces.get("is_equivalent"),
        "has_l2_refactor": bool(state.get("l2_code")),
        "has_l3_refactor": bool(state.get("l3_code")),
        **cr_metrics,
        "last_review_comment": comments[-1] if comments else "",
        "all_review_comments": comments,
    }
    return summary


def append_experiment_record(record: dict[str, Any], output_path: str | Path) -> None:
    """把实验结果追加到 JSONL 文件。"""
    path = Path(output_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except FileNotFoundError:
        # Windows pathlib bug: mkdir(parents=True, exist_ok=True) can raise
        # FileNotFoundError on drive root even when the directory already exists.
        if not path.parent.exists():
            raise
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")
