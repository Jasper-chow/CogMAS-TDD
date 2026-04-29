from __future__ import annotations

"""
RAR4IS 节点（项目“记忆检索”阶段）。

目标：
- 根据需求和历史上下文，构建 pitfall_guide（避坑指南）。
- 在完整版本中，这里通常会接向量库检索历史 Bug、Issue、提交记录等。
"""

from state import AgentState

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
    pitfall_guide = dict(state.get("pitfall_guide", {}))
    # setdefault 用于“缺失才补”，不会覆盖已有真实检索结果。
    pitfall_guide.setdefault("source", "placeholder")
    pitfall_guide.setdefault("items", [])
    return {
        "pitfall_guide": pitfall_guide,
        "review_comments": [
            *state.get("review_comments", []),
            f"{NODE_NAME}: pitfall guide refreshed",
        ],
    }
