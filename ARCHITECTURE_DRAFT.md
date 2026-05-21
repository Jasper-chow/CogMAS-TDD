# CogMAS-TDD 正式架构设计文档草案

## 1. 文档目标
本文档用于定义 `CogMAS-TDD` 的下一阶段正式架构，目标是把原先偏抽象的 `ISO 25010 + TDD + LDB` 框架，升级为一个：

- 有明确质量目标的系统；
- 有可检索规则依据的系统；
- 有动态/静态双重审判的系统；
- 有失败反馈闭环的系统。

本文档既服务于代码实现，也服务于后续论文写作与实验设计。

---

## 2. 设计总纲
新的总体方法论如下：

- `ISO 25010` 负责给出顶层质量维度；
- `CISQ` 负责把质量维度落地成可执行规则；
- `RAR4IS` 负责按需激活规则与历史经验；
- `L2/L3` 负责按规则执行定向重构；
- `LDB` 负责动态语义等价验证；
- `Evaluation` 负责动态/静态双重审判；
- `refactor_feedback` 负责把失败上下文回传给下一轮重构。

一句话总结：

`ISO 给方向，CISQ 给靶点，LDB 给底线，Feedback 给修复路径。`

---

## 3. 系统目标
系统要解决的核心问题是：

1. AI 代码生成常常“能跑但不稳”；
2. 抽象质量标准很难直接驱动 LLM 做精确重构；
3. 重构后代码可能测试通过，但业务语义已经悄悄漂移；
4. 失败回环若没有上下文反馈，很容易陷入无效重试。

为此，本架构要求系统同时满足：

- 功能正确：测试通过；
- 规则合规：目标 CISQ 风险被消除；
- 语义稳定：L1 与 L3 的运行轨迹保持等价；
- 可回环修复：失败后能提供足够明确的反馈。

---

## 4. 顶层架构分层

### 4.1 知识层
负责从历史经验与标准规则中抽取当前任务真正需要的约束。

包含：

- 历史缺陷经验（未来可接提交历史、Issue、人工规则库）；
- CISQ 规则库（当前使用种子数据，未来扩展到完整 138 条）；
- ISO 25010 维度映射（安全性、可靠性、性能效率、可维护性）。

### 4.2 执行层
负责根据约束执行测试生成、实现生成和分层重构。

包含：

- `Red`：生成测试；
- `Green`：生成最小通过实现；
- `L2 Refactor`：按安全性/可靠性规则修复；
- `L3 Refactor`：按可维护性/性能规则优化。

### 4.3 审判层
负责从动态与静态两个角度判断重构是否有效。

包含：

- 动态审判：LDB 轨迹比较；
- 静态审判：CISQ 合规检查；
- 综合判定：`final_verdict`。

### 4.4 反馈层
负责在失败时生成精确可操作的上下文反馈。

包含：

- `trace diff` 摘要；
- 未通过的规则 ID；
- 静态审判发现；
- 下一轮建议修复方向。

---

## 5. 数据流主线
主流程如下：

1. 输入 `requirement`
2. `RAR4IS` 检索历史经验 + 激活相关 CISQ 规则
3. 输出 `standard_constraints`
4. `Red` 生成结构化测试
5. `Green` 生成结构化实现
6. `pytest` 运行，失败则回 Green
7. 测试通过后固化 `l1_code`
8. `L2` 按安全/可靠性规则重构
9. `L3` 按可维护性/性能规则重构，并固化 `l3_code`
10. `Evaluation` 执行动态/静态双重审判
11. 若失败，输出 `refactor_feedback` 后打回 L2
12. 若通过，输出最终代码与审查报告

---

## 6. 共享状态协议（AgentState）
当前推荐的关键字段如下：

- `requirement`: 当前需求说明
- `code`: 当前代码
- `test_cases`: 当前测试脚本
- `pitfall_guide`: 历史经验摘要
- `standard_constraints`: 规则约束 JSON
- `activated_rule_ids`: 本轮激活规则
- `activated_dimensions`: 本轮激活维度
- `review_comments`: 节点执行日志
- `test_passed`: 最近一次测试是否通过
- `test_error`: 最近一次错误信息
- `same_error_streak`: 连续相同错误次数
- `green_attempts`: Green 尝试次数
- `l1_code`: 测试通过后的基线实现
- `l3_code`: L3 重构后的代码
- `traces`: 轨迹数据
- `dynamic_verdict`: 动态仲裁结果
- `static_verdict`: 静态仲裁结果
- `final_verdict`: 综合判定结果
- `failed_rule_ids`: 静态未通过规则
- `refactor_feedback`: 失败反馈

---

## 7. Standard_Constraints 结构设计
`RAR4IS` 的输出不再停留在泛化的 `pitfall_guide`，而是升级为：

```json
{
  "dimensions": ["security", "reliability", "maintainability"],
  "rules_by_dimension": {
    "security": [
      {
        "rule_id": "CWE-89",
        "title": "SQL Injection",
        "risk_reason": "数据库查询若直接拼接用户输入，可能引发注入风险。",
        "repair_pattern": "使用参数化查询，避免动态拼接 SQL。",
        "priority": "high",
        "source": "cisq"
      }
    ]
  },
  "rules": []
}
```

字段说明：

- `dimensions`: 当前需求激活的质量维度；
- `rules_by_dimension`: 给 L2/L3 分层消费；
- `rules`: 平铺后的完整规则列表，方便 Evaluation 静态审判。

---

## 8. 按需激活（On-demand Activation）策略
为避免 138 条规则全量注入导致噪声过高，采用三步激活机制：

### 8.1 默认激活
- `maintainability` 默认启用；
- 原因：L3 架构优化需要稳定的最小约束集。

### 8.2 语义触发
根据需求关键词触发：

- `database/sql/input/user` => `security`
- `file/stream/socket/network/resource` => `reliability`
- `performance/cache/loop/latency` => `performance_efficiency`

### 8.3 未来扩展
后续可以增加：

- 基于历史 Bug 的优先级提升；
- 基于失败日志的规则反激活与再排序；
- 基于 embedding 的规则语义召回。

---

## 9. RAR4IS 节点设计
`RAR4IS` 的职责升级为：

1. 读取当前需求；
2. 激活 ISO 25010 维度；
3. 从 CISQ 规则库中选出相关规则；
4. 输出 `standard_constraints`；
5. 将规则摘要同时同步给 `pitfall_guide`，兼容旧流程。

当前实现阶段：

- 使用本地 `knowledge/cisq_rules_seed.json` 作为最小种子规则库；
- 未来替换为 `ChromaDB + embedding + metadata filtering`。

---

## 10. Red / Green 协议

### 10.1 Red
结构化输出：

```json
{
  "test_code": "...",
  "explanation": "..."
}
```

职责：

- 基于需求与约束生成测试；
- 尽量明确业务行为和边界条件。

### 10.2 Green
结构化输出：

```json
{
  "code": "...",
  "explanation": "..."
}
```

职责：

- 根据测试和上一轮错误，快速生成最小可通过实现；
- 只关注功能正确，不负责高层质量优化。

---

## 11. Green 自修复循环
测试回环的退出条件必须明确：

1. 测试通过，进入 L2；
2. 达到最大尝试次数，停止；
3. 连续相同错误达到阈值，提前停止。

目的：

- 防止 LLM 进入低价值重复修复；
- 给上层工作流一个可解释的停止条件。

---

## 12. L2 / L3 分层执行策略

### 12.1 L2 Refactor
消费维度：

- `security`
- `reliability`

典型目标：

- 消除 `CWE-89`、`CWE-404` 等风险；
- 增强空值检查、异常处理、资源释放、timeout、防注入。

### 12.2 L3 Refactor
消费维度：

- `maintainability`
- `performance_efficiency`

典型目标：

- 降低复杂度；
- 减少过长函数；
- 优化嵌套循环；
- 改善模块边界。

---

## 13. Evaluation 双重审判机制

### 13.1 动态审判（LDB）
比较对象：

- `l1_code`
- `l3_code`

过程：

1. 在同一组测试下执行两份代码；
2. 用 `sys.settrace` 捕获运行轨迹；
3. 比较关键节点、变量集合、变量值。

输出：

- `dynamic_verdict = pass/fail`

### 13.2 静态审判（CISQ）
比较对象：

- `l3_code`
- `standard_constraints.rules`

过程：

1. LLM 作为“检察官”审查是否真正消除了指定规则风险；
2. 若 LLM 不可用，使用本地启发式审查兜底；
3. 输出未解决规则列表。

输出：

- `static_verdict = pass/fail`
- `failed_rule_ids`

### 13.3 最终判定

```text
final_verdict = pass
仅当 dynamic_verdict == pass 且 static_verdict == pass
```

---

## 14. refactor_feedback 设计
当 Evaluation 失败时，系统不能只说“失败”，而必须回传：

- 关键轨迹差异
- 未解决的规则 ID
- 静态审判摘要

推荐结构：

```text
第 15 个关键节点变量 `result` 的值不同：L1 为 100，L3 为 0。
静态规则未通过：CWE-404, MAINT-002
静态审判说明：文件资源关闭模式仍不稳定，且复杂度未明显下降。
```

价值：

- 避免盲目重试；
- 为下一轮 L2/L3 提供定向修复提示；
- 提高回环成功率。

---

## 15. 当前实现与未来扩展的边界

### 15.1 当前已落地
- `standard_constraints` 状态字段；
- CISQ 种子规则库；
- RAR4IS 的规则激活骨架；
- L2/L3 的按维度定向消费骨架；
- Evaluation 的动态/静态双重审判骨架；
- `refactor_feedback` 的失败反馈字段。

### 15.2 未来需要补全
- 用 `ChromaDB` 替换本地 JSON 种子库；
- 扩充到完整 138 条 CISQ 规则；
- 用真实 Prompt 替换 L2/L3 占位逻辑；
- 引入 LangSmith 与本地 JSON 日志；
- 增加规则优先级调度和实验指标统计。

---

## 16. 推荐下一阶段开发顺序

1. 完成 `ChromaDB` 接入和规则 metadata 建模；
2. 扩展 `standard_constraints` 的 schema；
3. 让 `L2/L3` 真正按规则改代码，而不只记录日志；
4. 让静态审判输出更细粒度的 rule-level finding；
5. 为 Evaluation 增加 structured diff report；
6. 加入 LangSmith 与实验日志。

---

## 17. 论文表述建议
你可以把这套方法概括为：

> 我们提出了一种结合 `ISO 25010`、`CISQ` 与 `LDB` 的认知分层多智能体 TDD 框架。  
> 其中，ISO 25010 提供顶层质量目标，CISQ 提供可执行规则约束，LDB 提供动态语义等价保证。  
> 框架通过 `RAR4IS` 检索并激活相关约束，在 `L2/L3` 执行定向重构，并通过 `Evaluation` 的动态/静态双重审判与 `refactor_feedback` 实现可解释的闭环修复。

---

## 18. 一句话总结
这套升级后的 CogMAS-TDD，不再只是“会写代码的多 Agent”，而是一个：

- 有规则依据；
- 有质量目标；
- 有动态底线；
- 有失败反馈；
- 可用于论文与工程双落地的智能重构系统。
