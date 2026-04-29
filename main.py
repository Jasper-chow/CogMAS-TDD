from __future__ import annotations

"""
CogMAS-TDD 的主入口文件（流程编排层）。

这个文件只做三件事：
1. 定义运行配置（模型参数、节点开关、Prompt 映射）；
2. 用 LangGraph 把各阶段节点串成可执行工作流；
3. 启动一次异步执行并输出最终状态。

设计原则：
- 流程编排和业务逻辑解耦：具体 Agent 逻辑全部在 agents/ 目录。
- 配置优先：节点是否启用、使用什么 Prompt 由配置控制。
- 可回环：Evaluation 失败后自动返回重构阶段重试。
"""

import asyncio
from typing import Any

from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from agents import NODE_REGISTRY
from state import AgentState, build_initial_state

MAX_REFACTOR_RETRIES = 3


def build_runtime_config() -> dict[str, Any]:
    """
    构建运行时配置。

    返回结构说明：
    - llm: 模型相关配置（供应商、模型名、温度、是否启用）
    - agents: 各节点配置
      - enabled: 是否启用该节点
      - prompt: 从节点模块中读取的 PROMPT_TEMPLATE

    说明：
    - 这里把 prompt 抽到配置里，是为了后续统一管理和热更新。
    - 当前 llm.enabled=False，表示主流程会跑占位逻辑，不会实际请求模型。
    """
    return {
        "llm": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "temperature": 0,
            "enabled": False,
        },
        "agents": {
            name: {
                "enabled": True,
                "prompt": getattr(module, "PROMPT_TEMPLATE", ""),
            }
            for name, module in NODE_REGISTRY.items()
        },
    }

def build_llm(config: dict[str, Any]) -> ChatOpenAI:
    """
    使用 LangChain 初始化 ChatOpenAI 实例。

    为什么保留这个函数：
    - 目前骨架阶段虽未强依赖真实 LLM 调用，但后续 agents/ 中会逐步接入。
    - 统一由这里创建模型，方便后续扩展重试策略、超时、回调日志等。
    """
    llm_config = config["llm"]
    return ChatOpenAI(
        model=llm_config["model"],
        temperature=llm_config.get("temperature", 0),
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


def should_retry_refactor(state: AgentState) -> str:
    """
    Evaluation 之后的分支路由函数。

    规则：
    - 如果 traces.is_equivalent 为 True，说明重构前后语义一致，流程结束。
    - 如果不一致且 iteration < MAX_REFACTOR_RETRIES，则回到 L2/L3 继续重构。
    - 否则停止重试并结束，避免无限循环。
    """
    trace_payload = state.get("traces", {})
    is_equivalent = trace_payload.get("is_equivalent", False)
    if is_equivalent:
        return "done"

    if state.get("iteration", 0) < MAX_REFACTOR_RETRIES:
        return "retry"
    return "done"


def build_workflow(runtime_config: dict[str, Any]) -> Any:
    """
    构建并编译 LangGraph 工作流。

    节点顺序（主链路）：
    START -> RAR4IS -> Red -> Green -> L2 -> L3 -> Evaluation

    条件回环：
    Evaluation --retry--> L2
    Evaluation --done--> END

    注意：
    - 这里的内部 async 函数仅是薄包装，真正逻辑都在 agents/*.py。
    - 这种写法让你只改 agents/ 就能迭代智能体能力。
    """
    graph = StateGraph(AgentState)

    async def rar4is(state: AgentState) -> AgentState:
        return await run_configured_node("rar4is_node", state, runtime_config)

    async def red(state: AgentState) -> AgentState:
        return await run_configured_node("red_node", state, runtime_config)

    async def green(state: AgentState) -> AgentState:
        return await run_configured_node("green_node", state, runtime_config)

    async def l2_refactor(state: AgentState) -> AgentState:
        return await run_configured_node("l2_refactor_node", state, runtime_config)

    async def l3_refactor(state: AgentState) -> AgentState:
        return await run_configured_node("l3_refactor_node", state, runtime_config)

    async def evaluation(state: AgentState) -> AgentState:
        return await run_configured_node("evaluation_node", state, runtime_config)

    graph.add_node("rar4is_node", rar4is)
    graph.add_node("red_node", red)
    graph.add_node("green_node", green)
    graph.add_node("l2_refactor_node", l2_refactor)
    graph.add_node("l3_refactor_node", l3_refactor)
    graph.add_node("evaluation_node", evaluation)

    # 主流程边：按 TDD + 分层重构顺序执行
    graph.add_edge(START, "rar4is_node")
    graph.add_edge("rar4is_node", "red_node")
    graph.add_edge("red_node", "green_node")
    graph.add_edge("green_node", "l2_refactor_node")
    graph.add_edge("l2_refactor_node", "l3_refactor_node")
    graph.add_edge("l3_refactor_node", "evaluation_node")
    # 条件边：Evaluation 判定失败则返回重构阶段，否则结束
    graph.add_conditional_edges(
        "evaluation_node",
        should_retry_refactor,
        {
            "retry": "l2_refactor_node",
            "done": END,
        },
    )
    return graph.compile()


async def main() -> None:
    """
    项目运行入口（异步）。

    步骤：
    1. 构建配置；
    2. 按需初始化 LLM（当前默认关闭）；
    3. 编译工作流；
    4. 构建初始状态；
    5. 运行图并打印最终状态结果。
    """
    config = build_runtime_config()
    if config["llm"].get("enabled"):
        _ = build_llm(config)

    app = build_workflow(config)
    initial_state = build_initial_state()
    result = await app.ainvoke(initial_state)
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
