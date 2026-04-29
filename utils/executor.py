from __future__ import annotations

"""
LDB 执行引擎（简化版）。

这个文件提供两类能力：
1. 轨迹采集：用 sys.settrace 捕获函数逐行执行信息；
2. 轨迹比对：给出重构前后是否“足够一致”的判定。

注意：
- 当前是可运行的教学级实现，不是生产级语义等价证明器。
- 目的是先打通“可追踪、可比较、可回环”的技术闭环。
"""

import sys
from types import FrameType
from typing import Any, Callable

TraceRecord = dict[str, Any]


def trace_function(func: Callable[[], Any]) -> list[TraceRecord]:
    """
    采集一个函数调用过程中的轻量轨迹。

    返回记录包含：
    - function: 当前执行的函数名
    - line_no: 触发事件的行号
    - locals: 当下局部变量快照（浅拷贝）

    说明：
    - 这里只监听 line 事件，便于初学者理解执行路径。
    - 真实项目中可按需增加 call/return/exception 事件。
    """
    records: list[TraceRecord] = []

    def tracer(frame: FrameType, event: str, arg: Any):  # type: ignore[override]
        if event == "line":
            records.append(
                {
                    "function": frame.f_code.co_name,
                    "line_no": frame.f_lineno,
                    "locals": dict(frame.f_locals),
                }
            )
        return tracer

    # 保存旧 tracer，避免影响外部调试/追踪环境。
    previous_trace = sys.gettrace()
    try:
        sys.settrace(tracer)
        func()
    finally:
        sys.settrace(previous_trace)
    return records


def compare_traces(
    original_trace: list[TraceRecord], refactored_trace: list[TraceRecord]
) -> bool:
    """
    对比两份轨迹并给出“是否等价”的占位判定。

    当前判定规则（简化）：
    1. 轨迹长度必须一致；
    2. 每一步的函数名必须一致；
    3. 每一步局部变量的键集合必须一致。

    为什么先这样做：
    - 规则简单、可解释，便于搭框架；
    - 后续可扩展为关键节点对齐、值级比较、容差比较等策略。
    """
    if len(original_trace) != len(refactored_trace):
        return False

    for left, right in zip(original_trace, refactored_trace):
        if left["function"] != right["function"]:
            return False
        if set(left["locals"].keys()) != set(right["locals"].keys()):
            return False
    return True
