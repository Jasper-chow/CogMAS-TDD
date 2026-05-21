# LDB 源码迁移映射说明

## 1. 迁移目标
本文档说明如何把 `LLMDebugger` 中真正有价值的能力迁移到 `CogMAS-TDD`，而不是简单复制整个代码库。

迁移原则：

- 迁移“方法闭环”，不迁移整套实验工程；
- 优先迁移 `Green` 阶段最有价值的调试能力；
- 保留我们现有 `Evaluation` 的 L1/L3 仲裁能力；
- 最终形成“前置调试 + 后置仲裁”的双层 LDB 使用方式。

---

## 2. LLMDebugger 到 CogMAS-TDD 的文件映射

### 2.1 入口层
- `LLMDebugger/programming/main.py`
  - 作用：按策略选择 `simple / ldb`
  - 在我们项目中的对应物：[main.py](file:///F:/LLM/LLM_learning/main.py)
  - 迁移方式：不直接复用，吸收其“调试节点作为工作流中的一个可选阶段”的思想

### 2.2 核心调试主线
- `LLMDebugger/programming/ldb.py`
  - 作用：执行失败测试 -> 获取 trace -> 生成 debug 对话 -> 修复代码
  - 在我们项目中的对应物：
    - [test_runner_node.py](file:///F:/LLM/LLM_learning/agents/test_runner_node.py)
    - [ldb_debug_node.py](file:///F:/LLM/LLM_learning/agents/ldb_debug_node.py)
    - [green_node.py](file:///F:/LLM/LLM_learning/agents/green_node.py)
  - 迁移方式：拆成三个节点，而不是保留脚本式单文件调度

### 2.3 执行器
- `LLMDebugger/programming/executors/py_executor.py`
  - 作用：执行给定测试并拿失败样例 + 真实输出
  - 在我们项目中的对应物：[test_runner_node.py](file:///F:/LLM/LLM_learning/agents/test_runner_node.py)
  - 已迁移内容：
    - 测试失败后保留错误信息
    - 新增 `last_failed_test` 与 `last_real_output`

### 2.4 运行时追踪
- `LLMDebugger/programming/tracing/tracer.py`
  - 作用：静态分块、插桩、值采集、trace 组织
  - 在我们项目中的对应物：
    - [local_ldb.py](file:///F:/LLM/LLM_learning/utils/local_ldb.py)
    - [executor.py](file:///F:/LLM/LLM_learning/utils/executor.py)
  - 迁移方式：
    - `Green` 调试阶段：在 `local_ldb.py` 中本地化重写 `get_code_traces_block` 思路
    - `Evaluation` 仲裁阶段：继续使用我们自己的 `sys.settrace` 方案

### 2.5 调试提示协议
- `LLMDebugger/programming/generators/py_generate.py`
  - 作用：组织 block trace prompt，并要求模型按 block 输出判断
  - 在我们项目中的对应物：
    - [ldb_debug_node.py](file:///F:/LLM/LLM_learning/agents/ldb_debug_node.py)
    - [green_node.py](file:///F:/LLM/LLM_learning/agents/green_node.py)
  - 已迁移内容：
    - `block` 级调试报告结构
    - 可疑 block 摘要回传 Green

---

## 3. 当前迁移落地内容

### 3.1 新增状态字段
在 [state.py](file:///F:/LLM/LLM_learning/state.py) 中新增：

- `entry_point`
- `ldb_debug_context`
- `ldb_debug_report`
- `last_failed_test`
- `last_real_output`

作用：

- 让 `Green` 调试不再只依赖 `pytest` 报错字符串；
- 让 LDB 的 block 级调试信息成为正式状态的一部分。

### 3.2 新增本地化 LDB 实现
新增 [local_ldb.py](file:///F:/LLM/LLM_learning/utils/local_ldb.py)，作用如下：

- 参考 `LLMDebugger` 的 `get_code_traces_block` 思路做本地化重写
- 自己完成切块、运行时快照和 block 级渲染
- 不直接调用 `LLMDebugger` 的 tracing 执行链
- 对外提供：
  - `get_ldb_block_trace(...)`
  - `render_trace_blocks_for_prompt(...)`
  - `heuristic_ldb_block_report(...)`

这意味着我们没有把 `LLMDebugger` 整个 tracing 执行链硬搬进主项目，而是把它的核心方法翻译成了适合当前工作流的本地实现。

当前本地 tracer 的核心步骤是：

1. 用 `ast` 找到目标函数；
2. 将顺序语句与控制结构拆成轻量 block；
3. 在执行失败测试对应调用时，用 `sys.settrace` 收集 block 结束处的局部变量快照；
4. 输出 `List[List[str]]` 形式的 block trace，供 `ldb_debug_node` 生成结构化调试报告。

### 3.3 新增 LDB 调试节点
新增 [ldb_debug_node.py](file:///F:/LLM/LLM_learning/agents/ldb_debug_node.py)，职责是：

1. 读取失败测试、真实输出、当前代码；
2. 调用 `ldb_adapter` 获取 block trace；
3. 使用结构化协议生成调试报告；
4. 输出：
   - `ldb_debug_context`
   - `ldb_debug_report`

### 3.4 调整工作流
在 [main.py](file:///F:/LLM/LLM_learning/main.py) 中，原先失败后是：

`test_runner -> green`

现在升级为：

`test_runner -> ldb_debug_node -> green`

这样 `Green` 在修复前会先获得 block 级调试上下文。

### 3.5 Green 消费 LDB 调试信息
在 [green_node.py](file:///F:/LLM/LLM_learning/agents/green_node.py) 中，Prompt 现在会额外消费：

- `LDB 调试上下文`

这使得 `Green` 从“仅根据报错修复”升级为“根据 block 级调试报告修复”。

---

## 4. 为什么采用“前置调试 + 后置仲裁”
我们没有把 LDB 只放在一个地方，而是拆成两个用途：

### 4.1 Green 阶段：LDB 作为 Debugger
目的：

- 快速定位失败测试最可疑的 block；
- 提高 Green 阶段修复质量；
- 降低盲改与死循环概率。

### 4.2 Evaluation 阶段：LDB 作为 Arbiter
目的：

- 比较 `l1_code` 与 `l3_code` 的运行轨迹；
- 检查重构是否改变了逻辑语义；
- 作为重构回环的最终裁判。

这两个位置的角色不同：

- `Green` 用 LDB 找 bug
- `Evaluation` 用 LDB 防漂移

---

## 5. 为什么不直接复刻 LLMDebugger 的全部实现
原因有三个：

1. `LLMDebugger` 的代码是实验驱动的脚本式结构，不适合直接塞进 LangGraph 工作流；
2. 它的目标是“调试生成代码”，而我们的目标是“调试 + 分层重构 + 最终仲裁”；
3. 我们需要把 LDB 融合进状态驱动的多 Agent 系统，而不是单文件迭代脚本。

因此更合理的策略是：

- 保留其最强的 tracing / block-debug 思想；
- 将其能力拆成独立节点；
- 用状态流和路由规则重构成图工作流。

---

## 6. 当前版本还未迁移的部分
当前只迁移了最小闭环能力，还没有完全吸收这些高级部分：

- `py_generate.py` 里的完整 few-shot block 级示例对话
- `prompt.py` 里的原论文风格大样本调试模板
- `staticfg` 更细粒度的 line/function 级可配置策略
- `ldb.py` 里“随机选失败测试”的采样策略
- 完整 token 统计与实验日志记录

---

## 7. 下一步建议

### 第一阶段
- 把 `ldb_debug_node` 从当前的“结构化骨架 + fallback”升级为真正 few-shot prompt 驱动
- 直接借鉴 `LLMDebugger/prompt.py` 中 block 判错格式

### 第二阶段
- 让 `ldb_adapter.py` 支持：
  - `line`
  - `block`
  - `function`
  三种粒度切换

### 第三阶段
- 在 `Evaluation` 中引入 block 级差异定位，而不仅是整体 trace difference summary

### 第四阶段
- 把 `refactor_feedback` 与 `ldb_debug_report` 统一成一个可复用的调试/审判反馈 schema

---

## 8. 一句话总结
当前这版迁移的本质不是“复制 LLMDebugger”，而是把它最重要的核心贡献：

- `失败样例驱动`
- `block 级 trace`
- `结构化调试协议`

迁入到 `CogMAS-TDD` 的 `Green` 闭环中，同时保留我们自己的 `Evaluation` 仲裁体系，形成：

`LDB for Debugging + LDB for Refactor Validation`
