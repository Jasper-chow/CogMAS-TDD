from __future__ import annotations

"""
Evaluation 节点（LDB 动态仲裁层）。

目标：
- 对比重构前后执行轨迹，判断是否发生语义偏移；
- 将判定结果写回 traces，供主图决定“通过”还是“回环重构”。
"""

from state import AgentState
from utils.executor import compare_traces, trace_function

NODE_NAME = "evaluation_node"
PROMPT_TEMPLATE = """
你是 LDB 动态评估代理。
目标：比较重构前后执行轨迹，判定是否语义等价。
输出：更新 traces 与 review_comments。
""".strip()


def _noop() -> None:
    """
    空函数占位。

    说明：
    - 当前骨架阶段仅演示 trace 采集与比对流程；
    - 后续应替换为“运行 L1 代码”和“运行 L3 代码”的真实入口函数。
    """
    return None


async def run(state: AgentState) -> AgentState:
    """
    Evaluation 节点执行函数（占位版）。

    处理步骤：
    1. 分别采集“原始实现”和“重构实现”的运行轨迹；
    2. 调用 compare_traces 做语义等价判定；
    3. 把轨迹和判定结果写回 state.traces；
    4. 写入 review_comments，标记 PASS 或 RETRY。
    """
    original_trace = trace_function(_noop)
    refactored_trace = trace_function(_noop)
    passed = compare_traces(original_trace, refactored_trace)

    traces = dict(state.get("traces", {}))
    traces.update(
        {
            "original": original_trace,
            "refactored": refactored_trace,
            "is_equivalent": passed,
        }
    )

    comments = [*state.get("review_comments", [])]
    comments.append(f"{NODE_NAME}: trace check => {'PASS' if passed else 'RETRY'}")
    return {"traces": traces, "review_comments": comments}
