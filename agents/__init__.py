"""
Agent 模块注册中心。

职责：
- 统一导入所有节点模块；
- 提供 NODE_REGISTRY（节点名 -> 模块对象）的映射；
- 让 main.py 可以按名字动态调度节点，而不耦合具体实现细节。
"""

from . import (
    evaluation_node,
    green_node,
    l2_refactor_node,
    l3_refactor_node,
    rar4is_node,
    red_node,
)

NODE_REGISTRY = {
    # 键必须与主图中的节点名一致
    "rar4is_node": rar4is_node,
    "red_node": red_node,
    "green_node": green_node,
    "l2_refactor_node": l2_refactor_node,
    "l3_refactor_node": l3_refactor_node,
    "evaluation_node": evaluation_node,
}
