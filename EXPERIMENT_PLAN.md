# CogMAS-TDD 论文实验设计与推进方案

## 1. 文档定位
本文档用于统一 `CogMAS-TDD` 的论文导向实验方案。

它不追求工业级工程完备性，而是服务于以下目标：

- 明确论文要证明的核心问题；
- 明确哪些模块必须做，哪些模块可以后置；
- 明确实验应该怎么设计、怎么比较、怎么写进论文；
- 明确数据集、baseline、指标、消融和案例分析的组织方式；
- 让后续代码开发围绕“支撑论文结论”来推进，而不是围绕“工程完美”来推进。

一句话总结：

> 我们现在做的是一个研究原型（research prototype），目标是提出架构并证明它有效，而不是交付工业级系统。

---

## 2. 论文目标重新定义
在论文导向前提下，我们的系统目标不是“做一个万能的 AI 开发平台”，而是：

1. 提出一个结合 `AI + TDD + 认知分层 + LDB + 规则约束` 的新框架；
2. 证明该框架在代码生成、调试、重构和质量约束方面优于更朴素的 AI-TDD 流程；
3. 通过实验说明：
   - LDB 风格调试有帮助；
   - 分层重构有帮助；
   - 动态仲裁有帮助；
   - 规则约束有帮助。

因此，论文最重要的不是“代码是否足够工程化”，而是：

- 方法是否清晰；
- 模块是否有贡献；
- 实验是否支撑结论；
- 对比是否公平；
- 消融是否说明问题。

---

## 3. 论文主张建议
建议把整篇论文的主张压缩成以下版本：

> 我们提出 CogMAS-TDD，一个结合认知分层多智能体、TDD 流程、CISQ/ISO 规则约束与 LDB 风格动态调试/仲裁的自动化代码生成与重构框架。  
> 相比普通 AI 代码生成流程和朴素 AI-TDD 流程，CogMAS-TDD 在功能成功率、调试效率、重构语义稳定性和质量约束满足度方面更具优势。

这个主张非常关键，因为它决定实验怎么设计。

如果主张过大，实验会散。
如果主张过小，创新点不够强。

当前最合适的平衡点是：

- 重点突出 `AI + TDD + LDB + Layered Refactor`
- 规则约束作为方法增强点
- 工程实现细节不作为主要卖点

---

## 4. 研究问题（Research Questions）
建议全文围绕 4 个核心研究问题展开。

### RQ1: TDD 主干是否有效？
与非 TDD 的 AI 代码生成流程相比，采用 Red-Green-Refactor 主干的 AI-TDD 是否更容易产生可通过测试的代码？

这个问题回答：

- 为什么要用 TDD，而不是直接让模型生成代码。

### RQ2: LDB 风格调试是否有效？
在 Green 阶段引入 LDB 风格 block-level 调试后，是否能降低盲目重试，提高修复成功率？

这个问题回答：

- 为什么要在 Green 阶段加入 LDB Debug，而不只是返回 pytest 报错。

### RQ3: 分层重构与动态仲裁是否有效？
在通过测试后，认知分层的 L2/L3 重构和 Evaluation 动态仲裁是否能降低语义漂移风险？

这个问题回答：

- 为什么要有 L2/L3；
- 为什么要有 LDB 风格动态仲裁。

### RQ4: 规则约束是否真正提升质量？
引入 `ISO 25010 + CISQ` 后，系统是否能更稳定地消除目标质量风险，而不是只做表面重构？

这个问题回答：

- 为什么要有 RAR4IS、规则检索和静态审判。

---

## 5. 方法版本与 baseline 设计
论文实验不能只有“我们的方法 vs 一个 baseline”，而应该构成一条逐步增强的链路。

建议如下。

### B0: Direct Generation
流程：

- 输入需求
- 直接生成代码
- 最后运行测试

特点：

- 没有 Red
- 没有 TDD
- 没有调试闭环

作用：

- 代表最朴素的 AI 代码生成基线；
- 用来回答 TDD 主干是否有价值。

### B1: Vanilla AI-TDD
流程：

- Red 生成测试
- Green 根据测试生成代码
- 测试失败则基于普通错误反馈重试
- 通过后做一次简单 Refactor

特点：

- 有标准 `Red-Green-Refactor`
- 没有 block-level LDB 调试
- 没有 L2/L3 分层
- 没有 CISQ/ISO
- 没有动态语义仲裁

作用：

- 这是最关键的“传统 AI-TDD” baseline；
- 用来回答：你的方法相比普通 AI-TDD 额外做的事情是否真的有用。

### B2: AI-TDD + Error Feedback
流程：

- Red
- Green
- 测试失败后只把 pytest 报错返回给 Green
- 不做 block debug

作用：

- 用来比较“普通错误反馈”和“LDB 风格调试”之间的差异。

### B3: AI-TDD + LDB Debug
流程：

- Red
- Green
- 测试失败后进入 `ldb_debug_node`
- Green 根据 block-level 调试信息修复
- 不做 L2/L3
- 不做规则约束
- 不做 Evaluation 仲裁

作用：

- 用来单独评估 LDB-style 调试的价值。

### B4: AI-TDD + Layered Refactor
流程：

- Red
- Green
- L2
- L3
- 但不加 CISQ/ISO 或者不加动态仲裁

作用：

- 用来测试“分层结构本身”是否有贡献。

### Ours: CogMAS-TDD
流程：

- RAR4IS
- Red
- Green
- LDB Debug
- L2
- L3
- Evaluation

包含：

- TDD 主干
- LDB 风格调试
- 认知分层重构
- CISQ/ISO 规则约束
- 动态/静态双重审判

---

## 6. 为什么一定要和传统 TDD 比
既然论文叙事是 `AI + TDD`，那么实验就必须回答：

- 你的方法相比“普通 AI-TDD”好在哪里？

这里的“传统 TDD”不建议理解为“人类程序员手工 TDD”，而应该理解为：

- `Vanilla AI-TDD`

也就是：

- 测试先行
- 生成功能代码
- 测试失败后重试
- 简单重构

但没有：

- LDB 风格调试
- 认知分层
- 动态仲裁
- CISQ/ISO 规则

因此，实验对比至少应包含：

- 非 TDD AI 流程
- 普通 AI-TDD
- 带 LDB Debug 的 AI-TDD
- 完整 CogMAS-TDD

否则审稿人会很自然地质疑：

- 你的提升究竟来自 TDD 本身，还是来自你额外加入的这些机制？

---

## 7. 数据集策略
数据集不能只靠“网上随便找一个跑一跑”，而要围绕研究问题来选。

建议采用“两层数据集 + 一个补充子集”的策略。

### 7.1 主功能实验数据集
建议使用：

- `HumanEval`
- `MBPP`

理由：

- 社区常见，审稿人熟悉；
- 与 LDB 原论文实验语境接近；
- 适合单函数代码生成与调试；
- 非常适合做 block-level trace。

建议角色分工：

- `HumanEval` 作为主实验数据集；
- `MBPP` 作为补充泛化实验。

### 7.2 质量约束实验子集
建议从 `HumanEval` / `MBPP` 中筛选一批题目，自建一个小型质量子集。

推荐规模：

- 30 到 50 题

构造方式：

- 先从题目中选出逻辑相对清晰、便于重构的任务；
- 为每个任务构造一个“功能基本可运行但质量存在问题”的初始实现；
- 再让 L2/L3 去处理这些问题。

建议覆盖的质量问题：

- 缺少空值处理
- 资源未正确释放
- 复杂度过高
- 函数过长
- 危险字符串拼接
- 缺少 timeout 或异常兜底

这个子集的论文价值非常高，因为它能直接支撑：

- `CISQ/ISO` 的质量约束实验；
- `L2/L3` 的重构实验；
- `Evaluation` 的语义稳定实验。

### 7.3 为什么不一开始追求大规模复杂工程数据集
因为当前论文重点不是：

- 大模型在真实工业仓库上的全能表现

而是：

- 证明 `CogMAS-TDD` 这个方法架构有效。

因此，现阶段更合理的实验设定是：

- Python
- 单函数任务
- 给定测试
- 可控环境

这与原版 LDB 论文的实验风格也是一致的。

---

## 8. 任务设定
建议把实验划分为两类任务。

### Task A: 代码生成与调试
输入：

- 自然语言需求/题目描述
- 测试集

输出：

- 通过测试的代码

主要验证：

- TDD 主干是否比直接生成更有效；
- Green 阶段的 LDB-style 调试是否能提高修复效率。

对应研究问题：

- RQ1
- RQ2

### Task B: 质量驱动重构
输入：

- 功能基本正确的代码
- 质量规则约束
- 测试集

输出：

- 通过测试且满足更多规则的重构代码

主要验证：

- L2/L3 是否有助于质量提升；
- Evaluation 是否能阻止语义漂移；
- 规则约束是否真的有效。

对应研究问题：

- RQ3
- RQ4

---

## 9. 指标设计
建议指标至少分为四类。

### 9.1 功能正确性指标
- `Final Pass Rate`
  - 最终通过测试的比例
- `Pass@k`
  - 如果后续采用多采样，可加入
- `Avg Iterations`
  - 平均修复/生成轮数

### 9.2 调试效率指标
- `Green Repair Success Rate`
  - Green 阶段修复成功率
- `Avg Green Attempts`
  - 平均 Green 尝试次数
- `Same Error Streak`
  - 连续相同错误次数
- `Avg Debug Turns`
  - 进入调试节点后的平均轮数

### 9.3 重构安全性指标
- `Dynamic Equivalence Pass Rate`
  - 动态仲裁通过率
- `Semantic Drift Detection Rate`
  - Evaluation 检出的语义漂移比例
- `Refactor Rollback Rate`
  - 被打回重构的比例

### 9.4 质量约束指标
- `Rule Resolution Rate`
  - 被激活规则中成功消除的比例
- `Static Verdict Pass Rate`
  - 静态审判通过率
- `Remaining Failed Rules`
  - 最终未修复规则数量
- `Complexity Reduction`
  - 如果后续可实现，可额外统计

### 9.5 成本指标（可选但建议有）
- `Avg Runtime`
- `Avg Tokens`
- `Avg Cost per Task`

即便论文不以成本为主，成本指标也可以帮助解释：

- 为什么某个方法更强；
- 以及是否值得付出额外复杂度。

---

## 10. 消融实验设计
消融实验必须围绕模块来设计，而不是随意删减。

建议至少做以下 4 个消融。

### Ablation A: w/o LDB Debug
删除：

- `ldb_debug_node`

保留：

- TDD 主干
- 分层结构
- 其他模块

验证：

- block-level 调试是否确实提高了修复效率。

### Ablation B: w/o Evaluation
删除：

- 动态仲裁

验证：

- 如果没有 Evaluation，语义漂移是否明显增加。

### Ablation C: w/o CISQ/ISO
删除：

- 规则约束与静态审判

验证：

- 分层重构如果没有明确规则约束，质量提升是否会变弱。

### Ablation D: w/o Layering
删除：

- L2/L3 分层

改为：

- 单一 Refactor agent

验证：

- 分层设计是否本身有贡献。

---

## 11. 主实验组织建议
建议整篇论文至少有三组主要实验。

### 实验 1：功能与调试主实验
数据集：

- `HumanEval`
- `MBPP`

比较方法：

- `B0`
- `B1`
- `B2`
- `B3`
- `Ours`

主要指标：

- `Final Pass Rate`
- `Avg Iterations`
- `Avg Green Attempts`
- `Avg Debug Turns`

目标：

- 证明 TDD 主干和 LDB Debug 的价值。

### 实验 2：质量与语义稳定实验
数据集：

- 自建质量约束子集

比较方法：

- `B4`
- `Ours`

主要指标：

- `Rule Resolution Rate`
- `Dynamic Equivalence Pass Rate`
- `Static Verdict Pass Rate`
- `Rollback Rate`

目标：

- 证明 L2/L3 + CISQ/ISO + Evaluation 的价值。

### 实验 3：消融实验
数据集：

- `HumanEval/MBPP` 子集
- 质量约束子集

比较方法：

- Full
- w/o LDB Debug
- w/o Evaluation
- w/o CISQ
- w/o Layering

目标：

- 解释每个模块的贡献。

---

## 12. 案例分析建议
案例分析是论文说服力的重要组成部分，尤其在你做研究原型时非常关键。

建议至少准备 3 个案例。

### Case 1: LDB Debug 帮助定位错误 block
展示：

- 错误代码
- 失败测试
- block trace
- `ldb_debug_report`
- 修复后代码

作用：

- 直观展示 block-level 调试确实比只看报错更强。

### Case 2: Evaluation 拦截语义漂移
展示：

- L1 代码
- L3 重构代码
- 两者测试都通过
- 但轨迹在关键节点不一致
- Evaluation 输出 `refactor_feedback`

作用：

- 直观展示动态仲裁的必要性。

### Case 3: 规则约束引导质量重构
展示：

- 激活的 CISQ 规则
- L2/L3 前后的代码差异
- `failed_rule_ids` 的变化
- 最终静态审判通过

作用：

- 直观展示为什么规则约束不是“空话”。

---

## 13. 论文中的结果表建议
建议至少准备四张主表。

### 表 1：主功能实验结果
列建议：

- Method
- HumanEval Pass Rate
- MBPP Pass Rate
- Avg Iterations
- Avg Green Attempts

### 表 2：质量与语义稳定实验
列建议：

- Method
- Rule Resolution Rate
- Dynamic Equivalence Pass Rate
- Static Verdict Pass Rate
- Final Accept Rate

### 表 3：消融实验
列建议：

- Variant
- Pass Rate
- Rule Resolution
- Drift Detection
- Avg Iterations

### 表 4：成本统计
列建议：

- Method
- Avg Runtime
- Avg Tokens
- Avg Retry Count

---

## 14. 当前代码应做到什么程度才足够支撑论文
不需要把系统做成工业级产品，但至少要做到以下程度。

### 必须做
1. `Green` 阶段能够消费 block-level 调试上下文并迭代修复
2. `Evaluation` 能输出动态仲裁结果
3. `RAR4IS` 至少能给出一组结构化规则约束
4. `L2/L3` 至少能在小规模质量集上体现“规则驱动”的作用
5. 整体实验能够输出结果日志，便于统计

### 建议做
1. `ldb_debug_node` 引入更接近原版 LDB 的 few-shot block 判错协议
2. `Evaluation` 输出更结构化的 diff report
3. 对 `HumanEval/MBPP` 提供统一实验脚本

### 可以后置
1. 工业级日志系统
2. 完整异常恢复
3. 大规模真实仓库实验
4. 复杂多文件工程支持

---

## 15. 现阶段开发优先级建议
如果接下来以论文为中心推进，优先顺序建议如下。

### 第一优先级：实验最小闭环
目标：

- 在小规模数据子集上跑通从 Red 到 Evaluation 的完整流程

需要落实：

- 统一输入格式
- 统一日志格式
- 统一结果存储格式

### 第二优先级：baseline 实现
目标：

- 让 `B0/B1/B2/B3/Ours` 至少能在同一批题上对比

这是论文的基础，没有 baseline 就没有实验说服力。

### 第三优先级：质量约束子集构造
目标：

- 构造 30~50 题的质量集

这是你方法区别于纯 LDB 或纯 AI-TDD 的关键。

### 第四优先级：案例与消融
目标：

- 在主实验能跑通后，补足最有论文价值的图表和案例

---

## 16. 推荐的近期时间安排
这里给出一个更务实的 4 周版本。

### 第 1 周：定实验设定
- 确定 `RQ1-RQ4`
- 确定 baseline
- 确定指标
- 确定主数据集和质量子集构造原则

### 第 2 周：打通主实验小子集
- 从 `HumanEval/MBPP` 各取一小部分题
- 跑通 `B0/B1/B2/B3/Ours`
- 检查结果日志是否完整

### 第 3 周：加入质量实验
- 构造小规模质量约束子集
- 跑通 `B4/Ours`
- 观察 `Evaluation` 和 `CISQ/ISO` 的效果

### 第 4 周：补消融与案例
- 跑消融
- 整理结果表
- 做案例分析
- 同步写论文实验章节

---

## 17. 最大风险与应对建议
当前最值得警惕的不是“工程代码不够优雅”，而是下面这些论文风险。

### 风险 1：研究问题太散
表现：

- 什么都想做，最后什么都讲不清。

建议：

- 始终围绕 `TDD + LDB + Layered Refactor + Rules + Evaluation` 这一主线。

### 风险 2：实验很多，但不能回答问题
表现：

- 表很多，结果不少，但审稿人不知道你到底证明了什么。

建议：

- 每张表都要服务于某个 RQ。

### 风险 3：实现过度工程化，拖慢论文进度
表现：

- 大量时间花在边角鲁棒性，而不是实验本身。

建议：

- 优先实现“足以验证方法”的能力，不追求工程完美。

### 风险 4：没有合适 baseline
表现：

- 只有“我们的方法”，对比不成立。

建议：

- 尽早实现 `Vanilla AI-TDD` 和 `Error Feedback` baseline。

---

## 18. 对当前项目代码的直接建议
结合当前已有代码，建议开发重点如下。

### 18.1 继续保留的模块
- [main.py](file:///F:/LLM/LLM_learning/main.py)
- [state.py](file:///F:/LLM/LLM_learning/state.py)
- [evaluation_node.py](file:///F:/LLM/LLM_learning/agents/evaluation_node.py)
- [ldb_debug_node.py](file:///F:/LLM/LLM_learning/agents/ldb_debug_node.py)
- [local_ldb.py](file:///F:/LLM/LLM_learning/utils/local_ldb.py)

这些已经构成了论文原型的主骨架。

### 18.2 优先加强的模块
- [red_node.py](file:///F:/LLM/LLM_learning/agents/red_node.py)
  - 真正面向 benchmark 生成测试
- [green_node.py](file:///F:/LLM/LLM_learning/agents/green_node.py)
  - 真正消费 `ldb_debug_report`
- [rar4is_node.py](file:///F:/LLM/LLM_learning/agents/rar4is_node.py)
  - 规则激活更可控
- [l2_refactor_node.py](file:///F:/LLM/LLM_learning/agents/l2_refactor_node.py)
- [l3_refactor_node.py](file:///F:/LLM/LLM_learning/agents/l3_refactor_node.py)
  - 让规则约束真正影响代码

### 18.3 暂时不需要过度投入的部分
- 工业级错误恢复
- 复杂多文件项目支持
- 大规模仓库级 benchmark
- 生产监控类能力

---

## 19. 一句话总结
接下来我们的实验推进思路应当是：

> 以论文问题为核心，以 `HumanEval + MBPP + 小型质量约束子集` 为实验载体，以 `非 TDD AI / Vanilla AI-TDD / LDB Debug / CogMAS-TDD` 为对比主线，逐步验证 TDD 主干、LDB 调试、分层重构、动态仲裁和规则约束的独立贡献。

---

## 20. 最终建议
如果只保留一句行动建议，那就是：

> 先把“小规模、可比较、可复现”的实验闭环跑通，再扩展方法复杂度；先证明架构有效，再追求工程优雅。

这最符合当前的论文目标，也最符合你现在的推进节奏。
