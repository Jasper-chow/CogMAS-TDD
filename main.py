from __future__ import annotations

"""
CogMAS-TDD 主入口。

当前版本的重点不再只是“演示流程能跑通”，而是支持论文实验：
- 同一套代码支持 baseline / ablation / ours；
- 所有实验通过 profile 切换，而不是手改节点；
- 统一输出结果记录，便于后续统计与画表。
"""

import argparse
import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any

from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from agents import NODE_REGISTRY
from experiment_profiles import (
    build_runtime_config,
    first_enabled_stage,
    next_after_cr,
    next_after_l2,
    next_after_l3,
    next_after_rar4is,
    next_after_test_fail,
    next_after_test_pass,
)
from state import AgentState, build_initial_state
from utils.helpers import resolve_llm_settings
from utils.experiment_logger import append_experiment_record, summarize_run

def build_llm(config: dict[str, Any]) -> ChatOpenAI:
    """
    使用 LangChain 初始化 ChatOpenAI 实例。

    为什么保留这个函数：
    - 目前骨架阶段虽未强依赖真实 LLM 调用，但后续 agents/ 中会逐步接入。
    - 统一由这里创建模型，方便后续扩展重试策略、超时、回调日志等。
    """
    llm_config = config["llm"]
    resolved = resolve_llm_settings(model_name=llm_config.get("model", ""))
    return ChatOpenAI(
        model=resolved["model_name"] or llm_config["model"],
        temperature=llm_config.get("temperature", 0),
        api_key=resolved["api_key"] or None,
        base_url=resolved["base_url"] or None,
    )


async def run_configured_node(
    node_name: str, state: AgentState, runtime_config: dict[str, Any]
) -> AgentState:
    """
    根据节点名调度并执行对应节点。

    执行逻辑：
    1. 从 runtime_config 读取节点开关；
    2. 若 disabled，则不执行节点，仅写入 review_comments；
    3. 若 enabled，则从 NODE_REGISTRY 找到模块并调用 module.run(state)。

    返回值：
    - 节点返回的是“状态增量”（partial state），由 LangGraph 合并进全局状态。
    """
    node_settings = runtime_config["agents"][node_name]
    if not node_settings["enabled"]:
        comments = [*state.get("review_comments", [])]
        comments.append(f"{node_name}: skipped by config")
        return {"review_comments": comments}

    module = NODE_REGISTRY[node_name]
    return await module.run(state)


def should_retry_refactor(state: AgentState, runtime_config: dict[str, Any]) -> str:
    """
    Evaluation 之后的分支路由函数。

    规则：
    - 如果 final_verdict 为 pass，说明动态与静态审判都通过，流程结束。
    - 如果不通过且 iteration < max_refactor_retries，则回到 L2/L3 继续重构。
    - 否则停止重试并结束，避免无限循环。
    """
    final_verdict = state.get("final_verdict", "unknown")
    if final_verdict == "pass":
        return "done"

    if state.get("iteration", 0) < runtime_config["limits"]["max_refactor_retries"]:
        return "retry"
    return "done"


def route_after_test(state: AgentState, runtime_config: dict[str, Any]) -> str:
    """
    Green 自修复循环路由（三件套退出条件）。

    规则顺序：
    1. 测试通过 => pass
    2. 达到最大尝试次数 => stop
    3. 连续相同错误达到上限 => stop
    4. 其他失败情况 => retry（返回 LDB Debug 或 Green）
    """
    if state.get("test_passed", False):
        return "pass"

    attempts = state.get("green_attempts", 0)
    max_attempts = runtime_config["limits"]["max_green_attempts"]
    if attempts >= max_attempts:
        return "stop"

    same_error_streak = state.get("same_error_streak", 0)
    max_same_error_streak = runtime_config["limits"]["max_same_error_streak"]
    if same_error_streak >= max_same_error_streak:
        return "stop"

    if next_after_test_fail(runtime_config) == "END":
        return "stop"
    return "retry"


def build_workflow(runtime_config: dict[str, Any]) -> Any:
    """
    构建并编译 LangGraph 工作流。

    当前版本支持 profile 化工作流：
    - 不同 baseline / ablation 通过开关决定是否经过某些节点；
    - 所有路由仍复用同一套节点实现，保证对比更公平。
    """
    graph = StateGraph(AgentState)

    async def rar4is(state: AgentState) -> AgentState:
        return await run_configured_node("rar4is_node", state, runtime_config)

    async def red(state: AgentState) -> AgentState:
        return await run_configured_node("red_node", state, runtime_config)

    async def green(state: AgentState) -> AgentState:
        return await run_configured_node("green_node", state, runtime_config)

    async def ldb_debug(state: AgentState) -> AgentState:
        return await run_configured_node("ldb_debug_node", state, runtime_config)

    async def test_runner(state: AgentState) -> AgentState:
        return await run_configured_node("test_runner_node", state, runtime_config)

    async def code_review(state: AgentState) -> AgentState:
        return await run_configured_node("code_review_node", state, runtime_config)

    async def l2_refactor(state: AgentState) -> AgentState:
        return await run_configured_node("l2_refactor_node", state, runtime_config)

    async def l3_refactor(state: AgentState) -> AgentState:
        return await run_configured_node("l3_refactor_node", state, runtime_config)

    async def evaluation(state: AgentState) -> AgentState:
        return await run_configured_node("evaluation_node", state, runtime_config)

    graph.add_node("rar4is_node", rar4is)
    graph.add_node("red_node", red)
    graph.add_node("green_node", green)
    graph.add_node("ldb_debug_node", ldb_debug)
    graph.add_node("test_runner_node", test_runner)
    graph.add_node("code_review_node", code_review)
    graph.add_node("l2_refactor_node", l2_refactor)
    graph.add_node("l3_refactor_node", l3_refactor)
    graph.add_node("evaluation_node", evaluation)

    graph.add_edge(START, first_enabled_stage(runtime_config))
    graph.add_conditional_edges(
        "rar4is_node",
        lambda _state: next_after_rar4is(runtime_config),
        {"red_node": "red_node", "green_node": "green_node"},
    )
    graph.add_edge("red_node", "green_node")
    graph.add_edge("green_node", "test_runner_node")

    post_test_target = next_after_test_pass(runtime_config)
    retry_target = next_after_test_fail(runtime_config)
    graph.add_conditional_edges(
        "test_runner_node",
        lambda state: route_after_test(state, runtime_config),
        {
            "pass": END if post_test_target == "END" else post_test_target,
            "retry": END if retry_target == "END" else retry_target,
            "stop": END,
        },
    )
    graph.add_edge("ldb_debug_node", "green_node")

    # code_review_node → L2 / L3 / Eval / END
    cr_next = next_after_cr(runtime_config)
    graph.add_conditional_edges(
        "code_review_node",
        lambda _state: cr_next,
        {
            "l2_refactor_node": "l2_refactor_node",
            "l3_refactor_node": "l3_refactor_node",
            "evaluation_node": "evaluation_node",
            "END": END,
        },
    )
    graph.add_conditional_edges(
        "l2_refactor_node",
        lambda _state: next_after_l2(runtime_config),
        {
            "l3_refactor_node": "l3_refactor_node",
            "evaluation_node": "evaluation_node",
            "END": END,
        },
    )
    graph.add_conditional_edges(
        "l3_refactor_node",
        lambda _state: next_after_l3(runtime_config),
        {"evaluation_node": "evaluation_node", "END": END},
    )
    graph.add_conditional_edges(
        "evaluation_node",
        lambda state: should_retry_refactor(state, runtime_config),
        {"retry": "l2_refactor_node", "done": END},
    )
    return graph.compile()


def _load_optional_text(file_path: str | None) -> str:
    if not file_path:
        return ""
    return Path(file_path).read_text(encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CogMAS-TDD experiment runner")
    parser.add_argument("--profile", default="ours", help="experiment profile name")
    parser.add_argument("--requirement", default="", help="requirement text")
    parser.add_argument("--task-id", default="", help="task id for experiment logging")
    parser.add_argument("--dataset-name", default="", help="dataset name for experiment logging")
    parser.add_argument("--entry-point", default="solve", help="entry function name")
    parser.add_argument("--code-file", default="", help="optional seed code file")
    parser.add_argument("--test-cases-file", default="", help="optional test file")
    parser.add_argument("--equivalence-mode", default="weak", choices=["weak", "strong"])
    parser.add_argument("--results-path", default="", help="JSONL result output path")
    parser.add_argument("--max-green-attempts", type=int, default=None)
    parser.add_argument("--max-same-error-streak", type=int, default=None)
    parser.add_argument("--max-refactor-retries", type=int, default=None)
    parser.add_argument("--print-final-state", action="store_true")
    return parser.parse_args()


def _apply_runtime_overrides(config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    if args.max_green_attempts is not None:
        config["limits"]["max_green_attempts"] = args.max_green_attempts
    if args.max_same_error_streak is not None:
        config["limits"]["max_same_error_streak"] = args.max_same_error_streak
    if args.max_refactor_retries is not None:
        config["limits"]["max_refactor_retries"] = args.max_refactor_retries
    return config


def _finalize_state(state: AgentState, runtime_config: dict[str, Any]) -> AgentState:
    finalized = AgentState(**state)

    if state.get("final_verdict") == "pass":
        finalized["workflow_status"] = "success"
        finalized["stop_reason"] = "evaluation_passed"
        return finalized

    if state.get("test_passed") and not runtime_config["agents"]["evaluation_node"]["enabled"]:
        finalized["workflow_status"] = "success"
        finalized["stop_reason"] = "finished_without_evaluation"
        return finalized

    if not state.get("test_passed", False):
        if state.get("green_attempts", 0) >= runtime_config["limits"]["max_green_attempts"]:
            finalized["workflow_status"] = "failed"
            finalized["stop_reason"] = "max_green_attempts"
            return finalized
        if state.get("same_error_streak", 0) >= runtime_config["limits"]["max_same_error_streak"]:
            finalized["workflow_status"] = "failed"
            finalized["stop_reason"] = "same_error_streak_limit"
            return finalized
        finalized["workflow_status"] = "failed"
        finalized["stop_reason"] = "test_failed"
        return finalized

    if (
        runtime_config["agents"]["evaluation_node"]["enabled"]
        and state.get("final_verdict") != "pass"
        and state.get("iteration", 0) >= runtime_config["limits"]["max_refactor_retries"]
    ):
        finalized["workflow_status"] = "failed"
        finalized["stop_reason"] = "max_refactor_retries"
        return finalized

    finalized["workflow_status"] = "finished"
    finalized["stop_reason"] = "workflow_completed"
    return finalized


async def run_experiment_once(
    *,
    profile: str = "ours",
    requirement: str = "",
    task_id: str = "",
    dataset_name: str = "",
    entry_point: str = "solve",
    code: str = "",
    test_cases: str = "",
    equivalence_mode: str = "weak",
    results_path: str = "",
    max_green_attempts: int | None = None,
    max_same_error_streak: int | None = None,
    max_refactor_retries: int | None = None,
) -> tuple[AgentState, dict[str, Any]]:
    """
    供 batch runner 直接调用的单次实验入口。
    """
    args_namespace = argparse.Namespace(
        profile=profile,
        requirement=requirement,
        task_id=task_id,
        dataset_name=dataset_name,
        entry_point=entry_point,
        code_file="",
        test_cases_file="",
        equivalence_mode=equivalence_mode,
        results_path=results_path,
        max_green_attempts=max_green_attempts,
        max_same_error_streak=max_same_error_streak,
        max_refactor_retries=max_refactor_retries,
        print_final_state=False,
    )
    config = _apply_runtime_overrides(build_runtime_config(profile), args_namespace)
    if config["llm"].get("enabled"):
        _ = build_llm(config)

    app = build_workflow(config)
    run_id = str(uuid.uuid4())
    start_time = time.time()
    initial_state = build_initial_state(
        code=code,
        test_cases=test_cases,
        requirement=requirement,
        equivalence_mode=equivalence_mode,
        max_green_attempts=config["limits"]["max_green_attempts"],
        max_same_error_streak=config["limits"]["max_same_error_streak"],
        entry_point=entry_point,
        profile_name=profile,
        run_id=run_id,
        dataset_name=dataset_name,
        task_id=task_id,
        hide_tests_in_green=config["workflow"].get("hide_tests_in_green", False),
    )
    result = await app.ainvoke(initial_state)
    finalized_result = _finalize_state(result, config)
    finalized_result["wall_seconds"] = round(time.time() - start_time, 3)

    resolved_results_path = results_path or str(
        Path("results") / "experiments" / f"{profile}.jsonl"
    )
    record = summarize_run(
        state=finalized_result,
        runtime_config=config,
        profile_name=profile,
    )
    append_experiment_record(record, resolved_results_path)
    return finalized_result, record


async def main() -> None:
    """
    统一实验运行入口。

    当前入口面向论文实验而设计：
    - 接收 profile 与样本元数据；
    - 运行工作流；
    - 输出统一 JSONL 结果记录。
    """
    args = _parse_args()
    config = _apply_runtime_overrides(build_runtime_config(args.profile), args)
    code = _load_optional_text(args.code_file)
    test_cases = _load_optional_text(args.test_cases_file)
    finalized_result, record = await run_experiment_once(
        profile=args.profile,
        requirement=args.requirement,
        task_id=args.task_id,
        dataset_name=args.dataset_name,
        entry_point=args.entry_point,
        code=code,
        test_cases=test_cases,
        equivalence_mode=args.equivalence_mode,
        results_path=args.results_path,
        max_green_attempts=args.max_green_attempts,
        max_same_error_streak=args.max_same_error_streak,
        max_refactor_retries=args.max_refactor_retries,
    )
    if args.print_final_state:
        print(json.dumps(finalized_result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
