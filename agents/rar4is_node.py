from __future__ import annotations

"""
RAR4IS 节点（项目“记忆检索”阶段）。

目标：
- 根据需求和历史上下文，构建 pitfall_guide（避坑指南）。
- 在完整版本中，这里通常会接向量库检索历史 Bug、Issue、提交记录等。
"""

from pathlib import Path

from state import AgentState
from utils.helpers import (
    build_standard_constraints,
    detect_active_dimensions,
    load_cisq_rules,
    select_cisq_rules,
)

NODE_NAME = "rar4is_node"
PROMPT_TEMPLATE = """
你是 RAR4IS 检索代理。
目标：基于需求与历史上下文生成避坑指南（JSON）。
输出：更新 pitfall_guide。
""".strip()


async def run(state: AgentState) -> AgentState:
    """
    RAR4IS 节点执行函数（占位版）。

    输入：
    - state.pitfall_guide: 可能已有的历史数据。

    输出：
    - pitfall_guide: 至少保证含有 source、items 两个基本键。
    - review_comments: 写入一条执行日志，便于后续排查流程。
    """
    requirement = state.get("requirement", "")
    search_text = "\n".join(
        part
        for part in [
            requirement,
            state.get("test_cases", ""),
            str(state.get("pitfall_guide", {})),
        ]
        if part
    )
    knowledge_dir = Path(__file__).resolve().parent.parent / "knowledge"
    mapping_path = knowledge_dir / "CISQ_mapping.json"
    seed_path = knowledge_dir / "cisq_rules_seed.json"
    rules_path = mapping_path if mapping_path.exists() else seed_path
    cisq_rules = load_cisq_rules(rules_path)
    active_dimensions = detect_active_dimensions(search_text)
    selected_rules = select_cisq_rules(cisq_rules, search_text, active_dimensions)
    standard_constraints = build_standard_constraints(selected_rules, active_dimensions)

    pitfall_guide = dict(state.get("pitfall_guide", {}))
    pitfall_guide["source"] = f"rar4is+{rules_path.name}"
    pitfall_guide["items"] = [
        {
            "rule_id": rule["rule_id"],
            "title": rule["title"],
            "risk_reason": rule["risk_reason"],
        }
        for rule in selected_rules
    ]
    return {
        "pitfall_guide": pitfall_guide,
        "standard_constraints": standard_constraints,
        "activated_rule_ids": [rule["rule_id"] for rule in selected_rules],
        "activated_dimensions": active_dimensions,
        "review_comments": [
            *state.get("review_comments", []),
            f"{NODE_NAME}: standard constraints refreshed",
        ],
    }
