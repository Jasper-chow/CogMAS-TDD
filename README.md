# CogMAS-TDD 项目说明

## 1. 这个项目是做什么的？
`CogMAS-TDD` 是一个“多智能体 + 测试驱动开发（TDD）”的自动化框架。

你可以把它理解成一个会“分工协作”的开发团队：
- 有的 Agent 负责先写测试（Red）；
- 有的 Agent 负责快速实现功能（Green）；
- 有的 Agent 负责工程加固（L2）；
- 有的 Agent 负责架构优化（L3）；
- 最后由评估 Agent（Evaluation/LDB）判断“重构后是否改变了原始语义”。

项目核心目标是：在持续重构中，尽量保证“代码越来越好，但行为不跑偏”。

---

## 2. 为什么这个项目有价值？
传统 AI 代码生成常见问题：
- 能写出代码，但不稳定；
- 改一次通过，下一次重构可能把逻辑改坏；
- 缺少可追踪的质量闭环。

本项目给出的方案是：
- 用 `TDD` 保证“先有可执行测试”；
- 用 `认知分层（L1/L2/L3）` 分阶段提升代码质量；
- 用 `LDB 轨迹对比` 判断重构前后语义是否一致；
- 用 `LangGraph` 把整套过程变成自动可回环的工作流。

---

## 3. 核心概念（先懂这几个就能看代码）

### 3.1 AgentState（共享状态）
所有节点都通过一个统一状态对象通信，定义在 `state.py`：
- `code`: 当前代码
- `test_cases`: 测试脚本
- `pitfall_guide`: 历史避坑指南（JSON）
- `review_comments`: 节点执行日志/审查意见
- `traces`: 运行轨迹与判定结果
- `iteration`: 当前迭代轮次

一句话：`AgentState` 就是整条流水线的“共享内存”。

### 3.2 Node（节点）
每个阶段是一个独立节点（独立文件）：
- `rar4is_node`
- `red_node`
- `green_node`
- `l2_refactor_node`
- `l3_refactor_node`
- `evaluation_node`

当前版本中，这些节点是“可运行占位实现”，便于先搭建工程骨架。

### 3.3 Graph（流程图）
在 `main.py` 中用 `LangGraph` 编排：
`START -> RAR4IS -> Red -> Green -> L2 -> L3 -> Evaluation`

其中 Evaluation 有条件分支：
- 语义一致：结束；
- 语义不一致：回到 `L2/L3` 继续重构（最多重试上限）。

---

## 4. 当前目录结构与职责

```text
.
├── main.py                 # LangGraph 工作流编排入口
├── state.py                # 全局状态定义 AgentState
├── agents/
│   ├── __init__.py         # 节点注册表 NODE_REGISTRY
│   ├── rar4is_node.py      # 记忆检索节点（占位）
│   ├── red_node.py         # 测试生成节点（占位）
│   ├── green_node.py       # 功能实现节点（占位）
│   ├── l2_refactor_node.py # 工程加固节点（占位）
│   ├── l3_refactor_node.py # 架构优化节点（占位）
│   └── evaluation_node.py  # 轨迹仲裁节点（占位）
├── utils/
│   ├── executor.py         # LDB 轨迹采集与对比（简化实现）
│   ├── helpers.py          # 通用工具函数
│   └── __init__.py         # 对外导出
└── pyproject.toml          # 项目依赖与元信息（uv 管理）
```

---

## 5. 每个阶段到底在做什么？

### 5.1 RAR4IS（记忆检索）
目标：把“过去踩过的坑”带到当前任务里。

真实版本通常会：
- 读取历史代码/Issue/提交信息；
- 做向量检索；
- 产出结构化避坑指南 `pitfall_guide`。

### 5.2 Red（先写测试）
目标：先把“要达成什么行为”写成测试。

真实版本通常会：
- 读取需求 + 避坑指南；
- 让 LLM 生成 `pytest`；
- 可结合 `Outlines` 做结构化输出约束。

### 5.3 Green（快速通过）
目标：先把测试跑通，不追求完美设计。

这是 L1 层：重点是“功能正确”。

### 5.4 L2 Refactor（工程加固）
目标：让代码更稳健（安全、异常、资源管理）。

这是工程层：关注可靠性和健壮性。

### 5.5 L3 Refactor（架构优化）
目标：让代码更易维护（复杂度、模块化、复用性）。

这是架构层：关注长期可演化能力。

### 5.6 Evaluation（动态仲裁）
目标：判断重构前后是否“语义一致”。

当前用 `sys.settrace` 采集轻量轨迹，再做简化比对。  
如果发现语义偏移，就自动回到重构阶段继续修正。

---

## 6. 运行方式（uv）

### 6.1 安装依赖
```bash
uv sync
```

### 6.2 启动主流程
```bash
uv run python main.py
```

### 6.3 常见验证命令
```bash
uv run python -m compileall main.py state.py agents utils
```

---

## 7. 新手如何开始二次开发？

建议按下面顺序改造（从易到难）：
1. 先改 `agents/red_node.py`：接入 LLM，生成结构化测试输出；
2. 再改 `agents/green_node.py`：让代码实现围绕测试反馈迭代；
3. 再改 `agents/l2_refactor_node.py` 和 `agents/l3_refactor_node.py`：加入规则化重构；
4. 最后改 `agents/evaluation_node.py` + `utils/executor.py`：接真实代码轨迹对比。

关键原则：
- 尽量只改 `agents/` 下的逻辑；
- 保持 `run(state) -> state_update` 接口不变；
- 所有阶段都把关键决策写入 `review_comments`，便于追踪。

---

## 8. 配置驱动思想（为什么这样设计）
你会看到 `main.py` 里有统一配置：
- LLM 的模型参数；
- 每个节点的开关（enabled）；
- 每个节点关联的 Prompt。

这么做的好处：
- 不改流程代码就能切换节点能力；
- 团队多人协作时，职责边界清晰；
- 便于未来做 A/B 实验（不同 Prompt / 不同 Agent 策略）。

---

## 9. 当前版本边界（非常重要）
这是一个“可运行骨架”，不是最终智能体系统。

已具备：
- 可执行的工作流框架；
- 可扩展的节点组织方式；
- 基础的轨迹采集与回环机制。

尚未完成：
- 真实业务需求驱动的 Prompt 策略；
- 完整的 LLM 调用链与错误恢复；
- 高可信度语义等价判定器。

你现在最该做的是：在不破坏骨架的前提下，逐步把占位节点替换成真实能力。

---

## 10. 一句话总结
`CogMAS-TDD` 不是“单次生成代码”的工具，而是一个“可持续迭代、可验证、可回环”的多智能体研发流水线基础设施。
