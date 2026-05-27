from __future__ import annotations

"""
LDB 执行引擎（简化版）。

这个文件提供三类能力：
1. 轨迹采集：用 sys.settrace 捕获函数逐行执行信息；
2. 弱等价比对：关键节点与关键变量集合是否一致；
3. 强等价比对：在弱等价基础上进一步比较行级路径与变量值。

注意：
- 当前是可运行的教学级实现，不是生产级语义等价证明器。
- 目的是先打通"可追踪、可比较、可回环"的技术闭环。
"""

import ctypes
import os
import sys
import tempfile
import threading
import types
import uuid
from importlib import util as importlib_util
from pathlib import Path
from types import FrameType

# Force non-interactive matplotlib backend so BigCodeBench tasks that import
# matplotlib don't crash with "main thread is not in main loop" when executed
# from worker threads.
os.environ.setdefault("MPLBACKEND", "Agg")
from typing import Any, Callable

# LLM 生成的代码可能包含死循环，必须限制单次执行时长。
_TRACE_EXECUTION_TIMEOUT: float = 30.0


def _force_stop_thread(thread: threading.Thread) -> None:
    """向目标线程异步注入 SystemExit，终止纯 Python 死循环。

    原理：PyThreadState_SetAsyncExc 在下一条字节码执行时抛出异常，
    对 while True: pass 等纯 Python 死循环有效，对 C 扩展阻塞无效。
    """
    if not thread.is_alive():
        return
    tid = thread.ident
    if tid is None:
        return
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_ulong(tid),
        ctypes.py_object(SystemExit),
    )
    if res > 1:
        # 影响了多个线程，立即撤销
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(tid), None)

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


def _load_module_from_file(module_name: str, file_path: Path) -> types.ModuleType:
    """从文件路径动态加载模块。"""
    spec = importlib_util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module spec for {file_path}")
    module = importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ensure_test_imports(test_code: str) -> str:
    """若测试未导入 app 模块，则补充默认导入。"""
    if "from app import" in test_code or "import app" in test_code:
        return test_code
    return "from app import *\n\n" + test_code


def _execute_code_with_trace_inner(code: str, test_cases: str) -> dict[str, Any]:
    """内部实现，在独立线程中运行以支持超时取消。"""
    trace: list[TraceRecord] = []
    with tempfile.TemporaryDirectory(prefix="cogmas_trace_") as tmpdir:
        workspace = Path(tmpdir)
        app_path = workspace / "app.py"
        test_path = workspace / "test_app.py"
        app_path.write_text(code, encoding="utf-8")
        test_path.write_text(_ensure_test_imports(test_cases), encoding="utf-8")

        previous_sys_path = list(sys.path)
        app_module_name = f"app_{uuid.uuid4().hex}"
        test_module_name = f"test_app_{uuid.uuid4().hex}"
        try:
            sys.path.insert(0, str(workspace))
            app_module = _load_module_from_file(app_module_name, app_path)
            # 兼容测试中显式 import app 的情况，挂载别名。
            sys.modules["app"] = app_module
            test_module = _load_module_from_file(test_module_name, test_path)

            test_functions = [
                getattr(test_module, name)
                for name in dir(test_module)
                if name.startswith("test_") and callable(getattr(test_module, name))
            ]

            # Also collect unittest.TestCase subclasses (e.g. BigCodeBench format).
            import unittest as _unittest
            unittest_suite = _unittest.TestSuite()
            for _name in dir(test_module):
                _obj = getattr(test_module, _name)
                try:
                    if (
                        isinstance(_obj, type)
                        and issubclass(_obj, _unittest.TestCase)
                        and _obj is not _unittest.TestCase
                    ):
                        unittest_suite.addTests(_unittest.TestLoader().loadTestsFromTestCase(_obj))
                except TypeError:
                    pass

            if not test_functions and unittest_suite.countTestCases() == 0:
                return {
                    "passed": False,
                    "error": "no test_ functions found for trace execution",
                    "trace": [],
                }

            def _runner() -> None:
                for test_func in test_functions:
                    test_func()
                if unittest_suite.countTestCases() > 0:
                    runner = _unittest.TextTestRunner(stream=open(os.devnull, "w"), verbosity=0)
                    result = runner.run(unittest_suite)
                    if not result.wasSuccessful():
                        failures = result.failures + result.errors
                        msg = failures[0][1] if failures else "unittest failed"
                        raise AssertionError(msg)

            trace = trace_function(_runner)
            return {"passed": True, "error": "", "trace": trace}
        except Exception as exc:  # noqa: BLE001
            return {"passed": False, "error": repr(exc), "trace": trace}
        finally:
            sys.path = previous_sys_path
            sys.modules.pop("app", None)
            sys.modules.pop(app_module_name, None)
            sys.modules.pop(test_module_name, None)


def execute_code_with_trace(
    code: str, test_cases: str, timeout: float = _TRACE_EXECUTION_TIMEOUT
) -> dict[str, Any]:
    """
    执行代码与测试并捕获真实运行轨迹，带超时保护。

    返回：
    - passed: 是否通过执行
    - error: 错误摘要（为空表示成功）
    - trace: 轨迹记录列表

    超时处理：
    - 在独立 daemon 线程中运行；超时后主线程立即返回并尽力恢复全局状态。
    - 卡住的线程会在进程退出时自动清理（daemon=True）。
    """
    if not code or not test_cases:
        return {
            "passed": False,
            "error": "missing code or test_cases for trace execution",
            "trace": [],
        }

    # 快照全局状态，超时时在主线程中恢复，避免污染后续任务。
    saved_sys_path = list(sys.path)
    saved_app_module = sys.modules.get("app")

    result_box: list[dict[str, Any]] = []

    def _worker() -> None:
        try:
            result_box.append(_execute_code_with_trace_inner(code, test_cases))
        except Exception as exc:  # noqa: BLE001
            result_box.append({"passed": False, "error": repr(exc), "trace": []})

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        # 超时：强制终止死循环线程，然后恢复全局状态。
        _force_stop_thread(thread)
        thread.join(timeout=3)  # 等待 SystemExit 生效
        sys.path[:] = saved_sys_path
        if saved_app_module is not None:
            sys.modules["app"] = saved_app_module
        else:
            sys.modules.pop("app", None)
        return {
            "passed": False,
            "error": f"execution timeout after {timeout:.0f}s",
            "trace": [],
        }

    return result_box[0] if result_box else {
        "passed": False,
        "error": "worker thread completed without result",
        "trace": [],
    }


def compare_traces_weak(
    original_trace: list[TraceRecord], refactored_trace: list[TraceRecord]
) -> bool:
    """
    对比两份轨迹并给出"是否等价"的占位判定。

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


def compare_traces_strong(
    original_trace: list[TraceRecord], refactored_trace: list[TraceRecord]
) -> bool:
    """
    强等价比较：在弱等价通过后，再比对路径与变量值。

    当前规则：
    1. 先要求 weak 通过；
    2. 每一步 line_no 必须一致；
    3. 每一步 locals 的值表示（repr）必须一致。
    """
    if not compare_traces_weak(original_trace, refactored_trace):
        return False

    for left, right in zip(original_trace, refactored_trace):
        if left["line_no"] != right["line_no"]:
            return False
        left_locals = {k: repr(v) for k, v in left["locals"].items()}
        right_locals = {k: repr(v) for k, v in right["locals"].items()}
        if left_locals != right_locals:
            return False
    return True


def compare_traces(
    original_trace: list[TraceRecord],
    refactored_trace: list[TraceRecord],
    *,
    mode: str = "weak",
) -> bool:
    """统一比较入口：mode=weak 或 strong。"""
    if mode == "strong":
        return compare_traces_strong(original_trace, refactored_trace)
    return compare_traces_weak(original_trace, refactored_trace)


def summarize_trace_difference(
    original_trace: list[TraceRecord], refactored_trace: list[TraceRecord]
) -> str:
    """
    生成面向 Agent 的轨迹差异反馈。

    目标不是完整证明，而是给下一轮重构一个足够具体的修复线索。
    """
    if not original_trace and not refactored_trace:
        return "两侧均未产生运行轨迹，请检查测试是否真正执行。"
    if len(original_trace) != len(refactored_trace):
        return (
            f"轨迹长度不一致：L1 为 {len(original_trace)} 步，"
            f"L3 为 {len(refactored_trace)} 步。"
        )

    for index, (left, right) in enumerate(zip(original_trace, refactored_trace), start=1):
        if left["function"] != right["function"]:
            return (
                f"第 {index} 个关键节点函数不同："
                f"L1 为 {left['function']}，L3 为 {right['function']}。"
            )
        if left["line_no"] != right["line_no"]:
            return (
                f"第 {index} 个关键节点行号不同："
                f"L1 在第 {left['line_no']} 行，L3 在第 {right['line_no']} 行。"
            )

        left_keys = set(left["locals"].keys())
        right_keys = set(right["locals"].keys())
        if left_keys != right_keys:
            return (
                f"第 {index} 个关键节点局部变量集合不同："
                f"L1 为 {sorted(left_keys)}，L3 为 {sorted(right_keys)}。"
            )

        for key in sorted(left_keys):
            if repr(left["locals"][key]) != repr(right["locals"][key]):
                return (
                    f"第 {index} 个关键节点变量 `{key}` 的值不同："
                    f"L1 为 {left['locals'][key]!r}，L3 为 {right['locals'][key]!r}。"
                )

    return "未检测到关键轨迹差异。"
