from __future__ import annotations

"""
通用工具函数集合。

当前只放了最基础的状态合并函数；
后续可扩展为：
- 文本清洗；
- JSON 安全解析；
- 日志格式化；
- 重试与退避策略等。
"""

from typing import Any


def merge_state(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    """
    以浅合并方式合并两个字典。

    规则：
    - 先复制 base；
    - 再用 updates 覆盖同名键；
    - 返回新字典，不原地修改入参。

    适用场景：
    - 节点返回了部分状态更新，需要和旧状态拼接时。
    """
    merged = dict(base)
    merged.update(updates)
    return merged
