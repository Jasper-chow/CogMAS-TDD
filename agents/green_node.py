from __future__ import annotations

"""
Green 阶段节点（功能实现）。

目标：
- 尽快让 Red 阶段测试通过；
- 当前不强调架构优雅，重点是功能可用。
"""

from state import AgentState

NODE_NAME = "green_node"
PROMPT_TEMPLATE = """
你是 Green 阶段实现代理。
目标：最短路径通过测试，不做过度优化。
输出：更新 code。
""".strip()


async def run(state: AgentState) -> AgentState:
    """
    Green 节点执行函数（占位版）。

    输入：
    - state.code: 当前代码。

    输出：
    - code: 若为空则生成最小可执行实现。
    - iteration: 迭代轮次 +1，供 Evaluation 回环决策使用。
    - review_comments: 写入阶段日志。
    """
    code = state.get("code", "")
    if not code:
        code = "def placeholder_impl() -> bool:\n    return True\n"
    return {
        "code": code,
        "iteration": state.get("iteration", 0) + 1,
        "review_comments": [
            *state.get("review_comments", []),
            f"{NODE_NAME}: baseline implementation updated",
        ],
    }
