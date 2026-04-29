from __future__ import annotations

"""
Red 阶段节点（测试先行）。

目标：
- 基于需求与避坑指南生成可执行测试代码；
- 在 TDD 中先“让测试失败”，为后续 Green 提供明确目标。
"""

from state import AgentState

NODE_NAME = "red_node"
PROMPT_TEMPLATE = """
你是 Red 阶段测试生成代理。
目标：根据需求与避坑指南生成可执行测试。
输出：更新 test_cases。
""".strip()


async def run(state: AgentState) -> AgentState:
    """
    Red 节点执行函数（占位版）。

    输入：
    - state.test_cases: 可能已有的测试代码。

    输出：
    - test_cases: 若为空则补一份最小 pytest 用例。
    - review_comments: 记录该阶段已完成。
    """
    existing_tests = state.get("test_cases", "")
    # 占位阶段先保证“有可运行测试脚本”，后续可替换为 LLM + Outlines 结构化输出。
    if not existing_tests:
        existing_tests = (
            "def test_placeholder():\n"
            "    assert True\n"
        )
    return {
        "test_cases": existing_tests,
        "review_comments": [
            *state.get("review_comments", []),
            f"{NODE_NAME}: test cases prepared",
        ],
    }
