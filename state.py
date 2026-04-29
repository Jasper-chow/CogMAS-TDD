from __future__ import annotations

"""
全局共享状态定义文件。

在 LangGraph 中，所有节点都通过一个统一状态对象通信。
你可以把它理解为“项目上下文内存”：
- 上游节点写入的内容，会成为下游节点的输入；
- 每个节点只需返回自己更新的字段，不需要返回完整状态。
"""

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """
    图中所有节点共享的状态结构（TypedDict）。

    total=False 表示键是可选的，适合“增量更新”模式。
    字段说明：
    - code: 当前待评估/待重构的代码文本。
    - test_cases: Red 阶段产出的测试脚本文本。
    - pitfall_guide: RAR4IS 检索得到的历史避坑知识（JSON 结构）。
    - review_comments: 各节点写入的审查建议/运行日志。
    - traces: LDB 轨迹数据（原始、重构后、是否等价等）。
    - iteration: 当前循环轮次计数，用于控制重试上限。
    """

    code: str
    test_cases: str
    pitfall_guide: dict[str, Any]
    review_comments: list[str]
    traces: dict[str, Any]
    iteration: int


def build_initial_state(
    *,
    code: str = "",
    test_cases: str = "",
    pitfall_guide: dict[str, Any] | None = None,
    review_comments: list[str] | None = None,
    traces: dict[str, Any] | None = None,
    iteration: int = 0,
) -> AgentState:
    """
    构造工作流初始状态。

    设计要点：
    - 所有可变字段都给出安全默认值（例如列表/字典不为 None）；
    - 便于 main.py 一键启动，也便于测试时注入定制初始状态。
    """
    return AgentState(
        code=code,
        test_cases=test_cases,
        pitfall_guide=pitfall_guide or {},
        review_comments=review_comments or [],
        traces=traces or {},
        iteration=iteration,
    )
