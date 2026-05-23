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
    - test_passed: 最近一次 pytest 是否通过。
    - test_error: 最近一次 pytest 错误摘要。
    - last_test_error: 上一次 pytest 错误摘要（用于比较是否重复）。
    - same_error_streak: 连续相同错误计数（防死循环）。
    - green_attempts: Green 生成尝试次数。
    - max_green_attempts: Green 最大尝试次数上限。
    - max_same_error_streak: 连续相同错误允许上限。
    - red_output: Red 结构化输出，约定字段 test_code/explanation。
    - green_output: Green 结构化输出，约定字段 code/explanation。
    - equivalence_mode: 轨迹判定模式，weak 或 strong。
    - l1_code: Green 阶段测试通过后的基线代码（L2 首次进入时冻结）。
    - l2_code: L2 工程加固后的代码快照。
    - l3_code: L3 架构优化后的代码快照（Evaluation 比对终态）。
    - requirement: 当前任务需求文本。
    - standard_constraints: RAR4IS 输出的标准约束 JSON（ISO 维度 + CISQ 规则）。
    - activated_rule_ids: 当前轮次激活的规则 ID。
    - activated_dimensions: 当前轮次激活的质量维度。
    - dynamic_verdict: LDB 动态仲裁结果。
    - static_verdict: CISQ 静态审判结果。
    - final_verdict: 综合动态/静态之后的最终判定。
    - failed_rule_ids: 静态审判未通过的规则 ID。
    - refactor_feedback: Evaluation 写回的失败上下文与修复建议。
    - entry_point: 当前主函数名，用于 LDB block tracing。
    - ldb_debug_context: Green 阶段 LDB 调试上下文摘要。
    - ldb_debug_report: 结构化 block 调试报告。
    - ldb_debug_sessions: 多轮 LDB debug history，会被 Green 连续消费。
    - last_failed_test: 最近一次失败测试原文。
    - last_real_output: 最近一次失败测试的真实输出。
    - profile_name: 当前实验配置名，例如 ours / b1_vanilla_ai_tdd。
    - run_id: 当前实验运行 ID，用于结果记录。
    - dataset_name: 当前样本所属数据集名。
    - task_id: 当前样本 ID。
    - workflow_status: 当前工作流状态，例如 running / success / failed。
    - stop_reason: 当前工作流停止原因，便于实验统计。
    """

    code: str
    test_cases: str
    pitfall_guide: dict[str, Any]
    review_comments: list[str]
    traces: dict[str, Any]
    iteration: int
    test_passed: bool
    test_error: str
    last_test_error: str
    same_error_streak: int
    green_attempts: int
    max_green_attempts: int
    max_same_error_streak: int
    red_output: dict[str, str]
    green_output: dict[str, str]
    equivalence_mode: str
    l1_code: str
    l2_code: str
    l3_code: str
    requirement: str
    standard_constraints: dict[str, Any]
    activated_rule_ids: list[str]
    activated_dimensions: list[str]
    dynamic_verdict: str
    static_verdict: str
    final_verdict: str
    failed_rule_ids: list[str]
    refactor_feedback: str
    entry_point: str
    ldb_debug_context: str
    ldb_debug_report: dict[str, Any]
    ldb_debug_sessions: list[str]
    last_failed_test: str
    last_real_output: str
    profile_name: str
    run_id: str
    dataset_name: str
    task_id: str
    workflow_status: str
    stop_reason: str
    hide_tests_in_green: bool
    original_test_cases: str
    code_review_report: dict[str, Any]   # CodeReviewReport from code_review_node
    cr_few_shot_examples: str             # retrieved high-quality examples for CR (retrieval module, step 2)
    _task_tokens: int
    _task_llm_calls: int
    wall_seconds: float


def build_initial_state(
    *,
    code: str = "",
    test_cases: str = "",
    pitfall_guide: dict[str, Any] | None = None,
    review_comments: list[str] | None = None,
    traces: dict[str, Any] | None = None,
    iteration: int = 0,
    test_passed: bool = False,
    test_error: str = "",
    last_test_error: str = "",
    same_error_streak: int = 0,
    green_attempts: int = 0,
    max_green_attempts: int = 5,
    max_same_error_streak: int = 2,
    red_output: dict[str, str] | None = None,
    green_output: dict[str, str] | None = None,
    equivalence_mode: str = "weak",
    l1_code: str = "",
    l2_code: str = "",
    l3_code: str = "",
    requirement: str = "",
    standard_constraints: dict[str, Any] | None = None,
    activated_rule_ids: list[str] | None = None,
    activated_dimensions: list[str] | None = None,
    dynamic_verdict: str = "unknown",
    static_verdict: str = "unknown",
    final_verdict: str = "unknown",
    failed_rule_ids: list[str] | None = None,
    refactor_feedback: str = "",
    entry_point: str = "solve",
    ldb_debug_context: str = "",
    ldb_debug_report: dict[str, Any] | None = None,
    ldb_debug_sessions: list[str] | None = None,
    last_failed_test: str = "",
    last_real_output: str = "",
    profile_name: str = "ours",
    run_id: str = "",
    dataset_name: str = "",
    task_id: str = "",
    workflow_status: str = "running",
    stop_reason: str = "",
    hide_tests_in_green: bool = False,
    original_test_cases: str = "",
    code_review_report: dict[str, Any] | None = None,
    cr_few_shot_examples: str = "",
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
        test_passed=test_passed,
        test_error=test_error,
        last_test_error=last_test_error,
        same_error_streak=same_error_streak,
        green_attempts=green_attempts,
        max_green_attempts=max_green_attempts,
        max_same_error_streak=max_same_error_streak,
        red_output=red_output or {},
        green_output=green_output or {},
        equivalence_mode=equivalence_mode,
        l1_code=l1_code,
        l2_code=l2_code,
        l3_code=l3_code,
        requirement=requirement,
        standard_constraints=standard_constraints or {},
        activated_rule_ids=activated_rule_ids or [],
        activated_dimensions=activated_dimensions or [],
        dynamic_verdict=dynamic_verdict,
        static_verdict=static_verdict,
        final_verdict=final_verdict,
        failed_rule_ids=failed_rule_ids or [],
        refactor_feedback=refactor_feedback,
        entry_point=entry_point,
        ldb_debug_context=ldb_debug_context,
        ldb_debug_report=ldb_debug_report or {},
        ldb_debug_sessions=ldb_debug_sessions or [],
        last_failed_test=last_failed_test,
        last_real_output=last_real_output,
        profile_name=profile_name,
        run_id=run_id,
        dataset_name=dataset_name,
        task_id=task_id,
        workflow_status=workflow_status,
        stop_reason=stop_reason,
        hide_tests_in_green=hide_tests_in_green,
        original_test_cases=original_test_cases or test_cases,
        code_review_report=code_review_report or {},
        cr_few_shot_examples=cr_few_shot_examples,
    )
