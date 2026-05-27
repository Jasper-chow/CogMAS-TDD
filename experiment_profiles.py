from __future__ import annotations

"""
实验配置中心。

新框架流程：
  Green → Test Runner → Code Review → L2 Refactor → L3 Refactor → Evaluation

Profile 对照表：
  b0          : 单次直接生成（single-shot baseline）
  b2          : TDD 错误反馈循环（pure TDD baseline）
  b_cr_only   : TDD + CR 报告（不重构，仅度量质量）
  ours        : 完整系统（TDD + CR + L2 + L3 + Eval）
  ablation_no_cr      : ours 去掉 CR（L2/L3 无 findings 直接跳过）
  ablation_no_l2l3    : ours 去掉 L2/L3 重构
  ablation_no_eval    : ours 去掉 Evaluation 验证
"""

from copy import deepcopy
from typing import Any


def _base_profile() -> dict[str, Any]:
    return {
        "llm": {
            "provider": "siliconflow",
            "model": "Qwen/Qwen2.5-14B-Instruct",
            "temperature": 0,
            "enabled": False,
        },
        "limits": {
            "max_green_attempts": 5,
            "max_same_error_streak": 2,
            "max_refactor_retries": 3,
        },
        "workflow": {
            "allow_green_retry_without_ldb": True,
            "hide_tests_in_green": False,
        },
        "agents": {
            "rar4is_node":      {"enabled": False},   # 新框架中由 CR 取代，默认关闭
            "red_node":         {"enabled": False},
            "green_node":       {"enabled": True},
            "ldb_debug_node":   {"enabled": False},
            "test_runner_node": {"enabled": True},
            "code_review_node": {"enabled": True},
            "l2_refactor_node": {"enabled": True},
            "l3_refactor_node": {"enabled": True},
            "evaluation_node":  {"enabled": True},
        },
    }


PROFILE_OVERRIDES: dict[str, dict[str, Any]] = {
    # ── 完整系统 ──────────────────────────────────────────────────────────────
    "ours": {},

    # ── Baselines ─────────────────────────────────────────────────────────────
    "b0_direct_generation": {
        # 单次生成，不看测试，不重试
        "agents": {
            "code_review_node": {"enabled": False},
            "l2_refactor_node": {"enabled": False},
            "l3_refactor_node": {"enabled": False},
            "evaluation_node":  {"enabled": False},
        },
        "workflow": {
            "allow_green_retry_without_ldb": False,
            "hide_tests_in_green": True,
        },
        "limits": {"max_green_attempts": 1},
    },
    "b0_post_hoc_cr": {
        # B0 风格生成 + 后验 CR 评估（不重构），用于对比 ours 的质量基线
        "agents": {
            "code_review_node": {"enabled": True},
            "l2_refactor_node": {"enabled": False},
            "l3_refactor_node": {"enabled": False},
            "evaluation_node":  {"enabled": False},
        },
        "workflow": {
            "allow_green_retry_without_ldb": False,
            "hide_tests_in_green": True,
        },
        "limits": {"max_green_attempts": 1},
    },
    "b2_error_feedback": {
        # 纯 TDD 错误反馈，无 CR，无重构
        "agents": {
            "code_review_node": {"enabled": False},
            "l2_refactor_node": {"enabled": False},
            "l3_refactor_node": {"enabled": False},
            "evaluation_node":  {"enabled": False},
        },
    },
    "b_cr_only": {
        # TDD + CR 报告（度量质量但不重构）
        "agents": {
            "l2_refactor_node": {"enabled": False},
            "l3_refactor_node": {"enabled": False},
            "evaluation_node":  {"enabled": False},
        },
    },

    # ── 消融实验 ──────────────────────────────────────────────────────────────
    "ablation_no_cr": {
        # 去掉 CR：L2/L3 无 findings，会直接跳过
        "agents": {"code_review_node": {"enabled": False}},
    },
    "ablation_no_l2l3": {
        # 去掉重构层
        "agents": {
            "l2_refactor_node": {"enabled": False},
            "l3_refactor_node": {"enabled": False},
        },
    },
    "ablation_no_eval": {
        # 去掉 Evaluation 验证
        "agents": {"evaluation_node": {"enabled": False}},
    },

    # ── 参考代码实验（从有技术债的canonical解作为起始点） ─────────────────────────
    "ours_from_ref": {
        # Start directly at test_runner with reference_code as seed (--seed-source reference).
        # green_node is disabled so the canonical solution passes through unchanged to CR/L2/L3.
        # On test failure the pipeline stops (no LLM repair loop).
        "agents": {
            "green_node": {"enabled": False},
        },
        "workflow": {
            "allow_green_retry_without_ldb": False,
        },
    },
}


def _deep_update(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_update(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def build_runtime_config(profile_name: str = "ours") -> dict[str, Any]:
    if profile_name not in PROFILE_OVERRIDES:
        available = ", ".join(sorted(PROFILE_OVERRIDES))
        raise ValueError(f"unknown profile: {profile_name}. available: {available}")
    config = _deep_update(_base_profile(), PROFILE_OVERRIDES[profile_name])
    config["profile_name"] = profile_name
    return config


def summarize_enabled_agents(config: dict[str, Any]) -> list[str]:
    return [
        name
        for name, settings in config.get("agents", {}).items()
        if settings.get("enabled", False)
    ]


# ── 路由函数 ──────────────────────────────────────────────────────────────────

def first_enabled_stage(config: dict[str, Any]) -> str:
    """工作流起始节点。rar4is 保留兼容但默认关闭。"""
    for node_name in ("rar4is_node", "red_node", "green_node", "test_runner_node"):
        if config["agents"][node_name]["enabled"]:
            return node_name
    raise ValueError("at least one of rar4is_node/red_node/green_node/test_runner_node must be enabled")


def next_after_rar4is(config: dict[str, Any]) -> str:
    if config["agents"]["red_node"]["enabled"]:
        return "red_node"
    return "green_node"


def next_after_test_pass(config: dict[str, Any]) -> str:
    """测试通过后：优先进入 CR，没有 CR 则看 L2/L3/Eval。"""
    for node_name in ("code_review_node", "l2_refactor_node", "l3_refactor_node", "evaluation_node"):
        if config["agents"][node_name]["enabled"]:
            return node_name
    return "END"


def next_after_cr(config: dict[str, Any]) -> str:
    """CR 完成后：进入 L2，没有 L2 则看 L3/Eval。"""
    for node_name in ("l2_refactor_node", "l3_refactor_node", "evaluation_node"):
        if config["agents"][node_name]["enabled"]:
            return node_name
    return "END"


def next_after_test_fail(config: dict[str, Any]) -> str:
    if config["agents"]["ldb_debug_node"]["enabled"]:
        return "ldb_debug_node"
    if config["workflow"].get("allow_green_retry_without_ldb", True):
        return "green_node"
    return "END"


def next_after_l2(config: dict[str, Any]) -> str:
    for node_name in ("l3_refactor_node", "evaluation_node"):
        if config["agents"][node_name]["enabled"]:
            return node_name
    return "END"


def next_after_l3(config: dict[str, Any]) -> str:
    if config["agents"]["evaluation_node"]["enabled"]:
        return "evaluation_node"
    return "END"
