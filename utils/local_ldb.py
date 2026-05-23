from __future__ import annotations

"""
本地化 LDB block tracer。

设计目标：
- 参考 LLMDebugger 的核心思想：切块 -> 运行时快照 -> block 级调试输入；
- 不直接复用对方的 tracer.py 执行链；
- 使用当前项目更容易维护的 Python 标准库实现。

当前实现不是完整 CFG basic block 求解器，而是一个“面向调试”的轻量近似：
- 用 AST 找到目标函数；
- 把顺序语句聚合为一个 block；
- 把 if/for/while/with/try 等控制结构的头部与分支体拆成独立 block；
- 用 sys.settrace 在 block 结束处捕获局部变量快照；
- 输出与 LLMDebugger 相近的 `List[List[str]]` 结构，供 Prompt 消费。
"""

import ast
import ctypes
import sys
import threading
from dataclasses import dataclass
from types import FrameType
from typing import Any

_LDB_TRACE_TIMEOUT: float = 30.0


def _force_stop_thread(thread: threading.Thread) -> None:
    """向目标线程异步注入 SystemExit，终止纯 Python 死循环。"""
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
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(tid), None)


CONTROL_NODES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.Match,
)


@dataclass
class BlockSpec:
    """描述一个逻辑 block。"""

    block_id: str
    start_line: int
    end_line: int
    lines: list[str]


def _safe_repr(value: Any, *, limit: int = 80) -> str:
    text = repr(value)
    if len(text) > limit:
        return text[:40] + "..." + text[-20:]
    return text


def _normalize_failed_test(failed_test: str) -> str:
    """把 pytest 输出中的失败断言整理成可执行调用表达式。"""
    line = failed_test.strip()
    if "assert " in line:
        line = line.split("assert ", 1)[1]

    comparison_tokens = [" == ", " != ", " <= ", " >= ", " < ", " > "]
    for token in comparison_tokens:
        if token in line:
            line = line.split(token, 1)[0].strip()
            break
    return line.strip()


def _iter_nested_bodies(node: ast.stmt) -> list[list[ast.stmt]]:
    bodies: list[list[ast.stmt]] = []
    if isinstance(node, ast.If):
        bodies.extend([node.body, node.orelse])
    elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
        bodies.extend([node.body, node.orelse])
    elif isinstance(node, (ast.With, ast.AsyncWith)):
        bodies.append(node.body)
    elif isinstance(node, ast.Try):
        bodies.extend([node.body, node.orelse, node.finalbody])
        bodies.extend(handler.body for handler in node.handlers)
    elif isinstance(node, ast.Match):
        bodies.extend(case.body for case in node.cases)
    return [body for body in bodies if body]


def _append_grouped_block(
    blocks: list[BlockSpec],
    group: list[ast.stmt],
    source_lines: list[str],
    counter: int,
) -> int:
    if not group:
        return counter

    start_line = group[0].lineno
    end_line = max(getattr(stmt, "end_lineno", stmt.lineno) for stmt in group)
    lines = source_lines[start_line - 1 : end_line]
    blocks.append(
        BlockSpec(
            block_id=f"BLOCK-{counter}",
            start_line=start_line,
            end_line=end_line,
            lines=lines,
        )
    )
    return counter + 1


def _collect_blocks_from_body(
    body: list[ast.stmt],
    source_lines: list[str],
    blocks: list[BlockSpec],
    counter: int,
) -> int:
    current_group: list[ast.stmt] = []

    for stmt in body:
        if isinstance(stmt, CONTROL_NODES):
            counter = _append_grouped_block(blocks, current_group, source_lines, counter)
            current_group = []

            control_end = stmt.lineno
            if isinstance(stmt, ast.If):
                first_body_line = stmt.body[0].lineno if stmt.body else stmt.lineno
                control_end = first_body_line - 1
            elif isinstance(stmt, (ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith)):
                first_body_line = stmt.body[0].lineno if stmt.body else stmt.lineno
                control_end = first_body_line - 1
            elif isinstance(stmt, ast.Try):
                first_body_line = stmt.body[0].lineno if stmt.body else stmt.lineno
                control_end = first_body_line - 1

            control_end = max(control_end, stmt.lineno)
            blocks.append(
                BlockSpec(
                    block_id=f"BLOCK-{counter}",
                    start_line=stmt.lineno,
                    end_line=control_end,
                    lines=source_lines[stmt.lineno - 1 : control_end],
                )
            )
            counter += 1

            for nested_body in _iter_nested_bodies(stmt):
                counter = _collect_blocks_from_body(nested_body, source_lines, blocks, counter)
        else:
            current_group.append(stmt)
            if isinstance(stmt, ast.Return):
                counter = _append_grouped_block(blocks, current_group, source_lines, counter)
                current_group = []

    return _append_grouped_block(blocks, current_group, source_lines, counter)


def split_code_into_blocks(code: str, entry_point: str) -> list[BlockSpec]:
    """按目标函数生成 block 列表。"""
    tree = ast.parse(code)
    source_lines = code.splitlines()

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == entry_point:
            blocks: list[BlockSpec] = []
            _collect_blocks_from_body(node.body, source_lines, blocks, 0)
            return blocks
    raise ValueError(f"entry point `{entry_point}` not found")


def _build_snapshot(locals_dict: dict[str, Any]) -> str:
    pairs = [
        f"{name}={_safe_repr(value)}"
        for name, value in locals_dict.items()
        if not name.startswith("__")
    ]
    return "\t".join(pairs)


def _safe_locals_copy(locals_dict: dict[str, Any]) -> dict[str, Any]:
    """把 frame locals 转成可安全保存的普通字典。"""
    copied: dict[str, Any] = {}
    for name, value in dict(locals_dict).items():
        if name.startswith("__"):
            continue
        copied[name] = _safe_repr(value)
    return copied


def _capture_block_snapshots(
    *,
    code: str,
    call_expr: str,
    entry_point: str,
    block_end_lines: set[int],
) -> tuple[list[int], dict[int, list[str]]]:
    namespace: dict[str, Any] = {}
    exec(compile(code, "<ldb_local>", "exec"), namespace, namespace)

    executed_lines: list[int] = []
    snapshots: dict[int, list[str]] = {}
    previous_line: int | None = None
    previous_locals: dict[str, Any] | None = None
    target_depth = 0

    def tracer(frame: FrameType, event: str, arg: Any):  # noqa: ANN001
        nonlocal previous_line, previous_locals, target_depth
        if frame.f_code.co_name != entry_point and target_depth == 0:
            return tracer

        if frame.f_code.co_name == entry_point:
            if event == "call":
                target_depth += 1
                previous_line = None
                previous_locals = None
                return tracer

            if event == "line":
                current_line = frame.f_lineno
                if previous_line is not None and previous_line in block_end_lines and previous_locals is not None:
                    snapshots.setdefault(previous_line, []).append(_build_snapshot(previous_locals))
                executed_lines.append(current_line)
                previous_line = current_line
                previous_locals = _safe_locals_copy(frame.f_locals)
                return tracer

            if event == "return":
                return_line = previous_line or frame.f_lineno
                snapshots.setdefault(return_line, []).append(_build_snapshot(frame.f_locals))
                target_depth = max(0, target_depth - 1)
                previous_line = None
                previous_locals = None
                return tracer

        return tracer

    previous_trace = sys.gettrace()
    try:
        sys.settrace(tracer)
        eval(call_expr, namespace, namespace)
    finally:
        sys.settrace(previous_trace)

    return executed_lines, snapshots


def get_code_traces_block(code: str, failed_test: str, entry_point: str) -> list[list[str]]:
    """
    本地化 block trace 主入口。

    输出格式与 LLMDebugger 保持相近：
    [
      ["line1", "line2", "# a=1\tb=2"],
      ...
    ]
    """
    if not code.strip():
        raise ValueError("code is empty")

    call_expr = _normalize_failed_test(failed_test)
    if not call_expr:
        raise ValueError(f"cannot parse failed test: {failed_test!r}")

    blocks = split_code_into_blocks(code, entry_point)
    block_end_lines = {block.end_line for block in blocks}
    executed_lines, snapshots = _capture_block_snapshots(
        code=code,
        call_expr=call_expr,
        entry_point=entry_point,
        block_end_lines=block_end_lines,
    )

    executed_line_set = set(executed_lines)
    rendered_blocks: list[list[str]] = []
    for block in blocks:
        if not any(line_no in executed_line_set for line_no in range(block.start_line, block.end_line + 1)):
            continue

        block_lines = list(block.lines)
        snapshot_items = snapshots.get(block.end_line, [])
        if snapshot_items:
            block_lines.append("# " + snapshot_items[-1])
        rendered_blocks.append(block_lines)

    return rendered_blocks


def get_ldb_block_trace(*, code: str, failed_test: str, entry_point: str) -> dict[str, Any]:
    """兼容当前节点调用方式的包装器，带超时保护防止死循环卡住。"""
    result_box: list[dict[str, Any]] = []
    saved_sys_path = list(sys.path)

    def _worker() -> None:
        try:
            trace_blocks = get_code_traces_block(code, failed_test, entry_point)
            result_box.append({"ok": True, "trace_blocks": trace_blocks, "error": ""})
        except Exception as exc:  # noqa: BLE001
            result_box.append({"ok": False, "trace_blocks": [], "error": f"local ldb error: {exc}"})

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join(timeout=_LDB_TRACE_TIMEOUT)

    if thread.is_alive():
        _force_stop_thread(thread)
        thread.join(timeout=3)  # 等待 SystemExit 生效
        sys.path[:] = saved_sys_path
        return {
            "ok": False,
            "trace_blocks": [],
            "error": f"ldb trace timeout after {_LDB_TRACE_TIMEOUT:.0f}s (likely infinite loop in generated code)",
        }

    return result_box[0] if result_box else {
        "ok": False,
        "trace_blocks": [],
        "error": "ldb trace worker completed without result",
    }


def render_trace_blocks_for_prompt(
    trace_blocks: list[list[str]], *, max_blocks: int = 8, max_lines_per_block: int = 12
) -> str:
    """把 block trace 渲染成适合提示词消费的文本。"""
    if not trace_blocks:
        return ""

    selected_blocks = trace_blocks
    if len(selected_blocks) > max_blocks:
        half = max_blocks // 2
        selected_blocks = selected_blocks[:half] + selected_blocks[-half:]

    rendered: list[str] = []
    for index, block in enumerate(selected_blocks):
        block_lines = block[:max_lines_per_block]
        if len(block) > max_lines_per_block:
            block_lines = block_lines + ["..."]
        rendered.append(f"[BLOCK-{index}]\n" + "\n".join(block_lines))
    return "\n".join(rendered)


def build_structured_trace_blocks(trace_blocks: list[list[str]]) -> list[dict[str, Any]]:
    """把原始 trace blocks 转成更适合调试与提示词消费的结构。"""
    structured: list[dict[str, Any]] = []
    for index, lines in enumerate(trace_blocks):
        code_lines = [line for line in lines if not line.lstrip().startswith("#")]
        snapshot_lines = [line for line in lines if line.lstrip().startswith("#")]
        structured.append(
            {
                "block": f"BLOCK-{index}",
                "lines": list(lines),
                "code": "\n".join(code_lines).strip(),
                "snapshot": snapshot_lines[-1].lstrip("# ").strip() if snapshot_lines else "",
                "rendered": f"[BLOCK-{index}]\n" + "\n".join(lines),
            }
        )
    return structured


def select_focus_trace_blocks(
    trace_blocks: list[list[str]],
    *,
    max_blocks: int = 10,
    max_lines_per_block: int = 16,
) -> list[dict[str, Any]]:
    """
    模拟 LLMDebugger 对长 trace 的裁剪策略：
    - block 数过多时保留前半和后半；
    - 单个 block 过长时保留头尾。
    """
    structured = build_structured_trace_blocks(trace_blocks)
    selected = structured
    if len(selected) > max_blocks:
        half = max_blocks // 2
        selected = selected[:half] + selected[-half:]

    trimmed: list[dict[str, Any]] = []
    for item in selected:
        lines = item["lines"]
        if len(lines) > max_lines_per_block:
            head = max_lines_per_block // 2
            tail = max_lines_per_block - head
            lines = lines[:head] + ["..."] + lines[-tail:]
        trimmed.append(
            {
                **item,
                "lines": lines,
                "rendered": f"[{item['block']}]\n" + "\n".join(lines),
            }
        )
    return trimmed


def choose_suspicious_block(trace_blocks: list[list[str]]) -> str:
    """在无 LLM 或解析失败时，启发式选择最可疑 block。"""
    if not trace_blocks:
        return "BLOCK-0"

    signal_tokens = ("return", "raise", "==", "!=", "<", ">", "if ", "elif ", "while ", "for ")
    for index in range(len(trace_blocks) - 1, -1, -1):
        block = trace_blocks[index]
        joined = "\n".join(line for line in block if not line.lstrip().startswith("#"))
        if any(token in joined for token in signal_tokens):
            return f"BLOCK-{index}"
    return f"BLOCK-{len(trace_blocks) - 1}"


def render_block_reports_for_prompt(
    block_reports: list[dict[str, Any]],
    *,
    max_reports: int = 6,
) -> str:
    """把 block 诊断结果渲染成更接近 LDB few-shot 风格的反馈文本。"""
    if not block_reports:
        return ""

    selected = block_reports[:max_reports]
    rendered: list[str] = []
    for item in selected:
        verdict = "CORRECT" if item.get("correct") else "INCORRECT"
        rendered.append(
            f"[{item.get('block', 'BLOCK-0')}]\n"
            f"Feedback: {verdict}. {str(item.get('explanation', '')).strip()}"
        )
    return "\n".join(rendered)


def heuristic_ldb_block_report(
    *,
    failed_test: str,
    real_output: str,
    trace_blocks: list[list[str]],
) -> dict[str, Any]:
    """在 LLM 不可用时提供一个最小可运行的 block 调试报告。"""
    if not trace_blocks:
        return {
            "failed_test": failed_test,
            "real_output": real_output,
            "suspicious_block": "BLOCK-0",
            "block_reports": [
                {
                    "block": "BLOCK-0",
                    "correct": False,
                    "explanation": "未获取到可用 block trace，请先检查失败测试与入口函数。",
                }
            ],
            "summary": "本地 LDB block trace 不可用，建议回退到错误信息驱动修复。",
        }

    suspicious_block = choose_suspicious_block(trace_blocks)
    structured = build_structured_trace_blocks(trace_blocks)
    block_reports: list[dict[str, Any]] = []
    for block in structured:
        is_suspicious = block["block"] == suspicious_block
        block_reports.append(
            {
                "block": block["block"],
                "correct": not is_suspicious,
                "explanation": (
                    "该 block 位于失败路径上，且最接近条件判断、变量更新或返回结果。"
                    " 请优先核对其中的条件、局部变量变化和返回值。"
                    if is_suspicious
                    else "该 block 出现在失败执行路径中，但当前没有发现比可疑块更强的错误信号。"
                ),
            }
        )

    return {
        "failed_test": failed_test,
        "real_output": real_output,
        "suspicious_block": suspicious_block,
        "block_reports": block_reports,
        "summary": "已生成本地化 LDB 调试报告，请优先检查可疑 block。",
    }
