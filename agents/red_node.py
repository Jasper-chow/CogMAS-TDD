from __future__ import annotations

"""
Red 阶段节点（测试先行）。

目标：
- 基于需求与避坑指南生成可执行测试代码；
- 在 TDD 中先“让测试失败”，为后续 Green 提供明确目标。
"""

from pydantic import BaseModel

from state import AgentState
from utils.helpers import generate_with_outlines

NODE_NAME = "red_node"
PROMPT_TEMPLATE = """
你是 Red 阶段测试生成代理。
目标：根据需求与避坑指南生成可执行测试。
输出：更新 test_cases。
""".strip()


class RedNodeOutput(BaseModel):
    """Red 结构化输出：避免测试代码与实现代码字段混淆。"""

    test_code: str
    explanation: str = ""


async def run(state: AgentState) -> AgentState:
    """
    Red 节点执行函数（占位版）。

    输入：
    - state.test_cases: 可能已有的测试代码。

    输出：
    - red_output: 结构化结果（test_code/explanation）。
    - test_cases: 从 red_output.test_code 同步而来。
    - review_comments: 记录该阶段已完成。
    """
    existing_tests = state.get("test_cases", "")
    fallback_test_code = existing_tests or (
        "def test_placeholder():\n"
        "    assert True\n"
    )
    fallback = RedNodeOutput(
        test_code=fallback_test_code,
        explanation="占位实现：已生成最小可执行 pytest 用例。",
    )

    requirement = state.get("requirement", "")
    pitfall_guide = state.get("pitfall_guide", {})
    pitfall_items = pitfall_guide.get("items", [])
    pitfall_text = (
        "\n".join(f"- {item['rule_id']}: {item.get('title', '')}" for item in pitfall_items[:5])
        if pitfall_items
        else "无"
    )

    prompt = f"""你是 Red 阶段测试生成代理。
请根据需求生成 pytest 测试代码，输出必须符合结构化字段：
- test_code: 仅包含可执行 pytest 代码（函数名以 test_ 开头）
- explanation: 你的生成思路（简短）

需求描述：
{requirement or "（未提供需求）"}

质量注意事项（CISQ 规则提示）：
{pitfall_text}""".strip()

    data, used_llm, note, _token_count = generate_with_outlines(
        prompt=prompt,
        output_model=RedNodeOutput,
        fallback_data=fallback.model_dump(),
    )
    output = RedNodeOutput(**data)
    return {
        "red_output": output.model_dump(),
        "test_cases": output.test_code,
        "review_comments": [
            *state.get("review_comments", []),
            f"{NODE_NAME}: test cases prepared ({'LLM' if used_llm else 'fallback'})",
            f"{NODE_NAME}: {note}",
        ],
    }
