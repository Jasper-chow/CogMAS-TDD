from __future__ import annotations

"""
L3 重构节点（架构优化层）。

目标：
- 依据 ISO 25010 的模块化/可维护性相关子集做结构优化；
- 典型关注点：降低圈复杂度、函数拆分、提升复用与可测试性。
"""

from state import AgentState

NODE_NAME = "l3_refactor_node"
PROMPT_TEMPLATE = """
你是 L3 架构优化代理。
目标：降低复杂度、提升模块化与可复用性。
输出：更新 code。
""".strip()


async def run(state: AgentState) -> AgentState:
    """
    L3 节点执行函数（占位版）。

    当前仅记录审查信息，不改动代码。
    后续可在此实现：
    - 大函数拆分为小函数；
    - 抽象公共逻辑到 utils 或服务层；
    - 优化模块边界，减少耦合。
    """
    comments = [*state.get("review_comments", [])]
    comments.append(f"{NODE_NAME}: architecture refinement reviewed")
    return {"review_comments": comments}
