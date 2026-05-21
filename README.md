# CogMAS-TDD

> Cognition-guided Multi-Agent System with Test-Driven Development —  
> 一个"**生成 → 审查 → 定向加强**"的自动化代码生成与质量保障框架。

---

## 1. 这个项目解决什么问题？

当前 AI 代码生成存在一个核心矛盾：

- 模型能生成**功能正确**的代码，但**质量参差不齐**（安全隐患、资源泄漏、复杂度过高）；
- 传统 TDD 流程能保证功能通过测试，但对代码质量几乎没有约束力；
- 如果引入质量约束，又可能破坏功能正确性——**质量提升和功能保证往往互斥**。

CogMAS-TDD 的核心主张是：

> **在不影响通过率的前提下（甚至提升通过率），让模型生成代码的质量显著优于普通 AI-TDD。**

实现方式是：在 TDD 流程中嵌入一个**认知分层代码审查节点**，用 CISQ/ISO 标准对通过测试的代码做多维度打分，下游 L2（安全可靠性）和 L3（可维护性性能）重构节点精准消费审查发现的问题，最后由 Evaluation 节点验证重构没有破坏功能。

---

## 2. 核心工作流

```
    Green（生成/修复功能代码）
        ↓
    Test Runner（pytest 功能验证）
        ↓ 失败 → LDB Debug（block 级调试）→ 回到 Green
        ↓ 通过
    Code Review Agent（认知分层四维度审查 + 幻觉过滤）
        ↓ 输出: 结构化审查报告（分数/问题/改进建议）
    L2 Refactor（消费 security + reliability findings）
        ↓
    L3 Refactor（消费 maintainability + performance findings）
        ↓
    Evaluation（动态轨迹比对 + 静态 CISQ 审判）
        ↓ 不通过 → 回到 L2
        ↓ 通过 → END
```

### 关键设计决策

| 决策 | 说明 |
|---|---|
| CR 在 Test Runner 之后 | 只审查功能正确的代码，避免"垃圾进垃圾出" |
| L2/L3 定向消费 CR findings | 不用通用规则，而是精准修复审查发现的**具体问题** |
| Evaluation 双审判 | 动态轨迹比对（保证行为不变）+ 静态 CISQ 审判（保证规则不漏） |
| 幻觉过滤 | CR 的每个 finding 都经 Evaluation Agent 核验代码中真实存在再输出 |

---

## 3. 完整目录结构与文件职责

```
LLM_learning/
│
├── main.py                          ← LangGraph 工作流编排入口 + 单实验 CLI
├── state.py                         ← 全局共享状态 AgentState 定义
├── experiment_profiles.py           ← 实验 profile 系统（baseline/ablation/ours）
├── run_benchmark.py                 ← 批量实验 CLI（MBPP/HumanEval）
├── benchmark_inputs.py              ← 数据集加载适配层 + manifest 系统
├── aggregate_results.py             ← 多维度结果聚合（profile/dataset 分组）
├── generate_cisq_python_benchmark_subset.py  ← CISQ Python 专项子集生成
├── .env                             ← API Key 与模型配置（不提交到 Git）
│
├── agents/                          ← ★ 工作流节点实现 ★
│   ├── __init__.py                  # NODE_REGISTRY 节点注册表
│   ├── green_node.py                # 功能代码生成（首次/修复两种 prompt）
│   ├── test_runner_node.py          # pytest 执行器 + 错误解析
│   ├── ldb_debug_node.py            # LDB 风格 block 级调试
│   ├── code_review_node.py          # ★ 认知分层四维度代码审查 ★
│   ├── l2_refactor_node.py          # 安全/可靠性定向加强（消费 CR findings）
│   ├── l3_refactor_node.py          # 可维护性/性能定向加强（消费 CR findings）
│   ├── evaluation_node.py           # 动态仲裁 + 静态 CISQ 双审判
│   ├── rar4is_node.py               # 规则检索与激活（预留）
│   └── red_node.py                  # 测试先行生成（预留）
│
├── utils/                           ← 工具与基础设施层
│   ├── helpers.py                   # LLM 调用（outlines + OpenAI SDK fallback）、CISQ 审计
│   ├── local_ldb.py                 # 本地化 LDB block tracer（AST + sys.settrace）
│   ├── ldb_prompt_protocol.py       # LDB 风格 few-shot block 判错 prompt 协议
│   ├── ldb_adapter.py               # LLMDebugger 迁移适配
│   ├── executor.py                  # 轨迹采集 + 弱/强等价比对
│   ├── experiment_logger.py         # 统一 JSONL 实验记录（含 CR 指标抽取）
│   ├── result_layout.py             # 运行产物目录管理
│   └── humaneval_official.py        # HumanEval 官方 pass@k 评估（Windows 兼容）
│
├── knowledge/                       ← CISQ/ISO 规则知识库
│   ├── CISQ_mapping.json            # 80+ 条完整 CISQ 规则（ISO 25010 维度映射）
│   ├── CISQ_mapping_python_benchmark_subset.json  # Python 专项 CISQ 规则子集（CR 直接加载）
│   └── cisq_rules_seed.json         # 8 条高质量种子规则
│
├── benchmark_manifests/             ← 实验任务清单
│   ├── shared_baseline_subset_v1.json   # 4 题共享子集（2 MBPP + 2 HumanEval）
│   ├── baseline_extended_v1.json        # 25 题扩展基线（20 MBPP + 5 HumanEval）
│   ├── quality_subset_v1.json           # 30 题质量约束子集（含低质量 seed 实现）
│   ├── humaneval_plus_20.json           # HumanEval+ 20 题 dev 子集
│   ├── humaneval_plus_full.json         # HumanEval+ 全集
│   ├── humaneval_smoke_v1.json          # HumanEval 2 题 smoke 快速验证
│   └── smoke_dual_dataset.json          # 双数据集 smoke
│
├── human-eval/                      # HumanEval 完整数据集 + 官方评估脚本
├── MBPP/                            # MBPP 完整数据集
├── LLMDebugger/                     # LDB 论文参考实现（tracer、执行器、数据集）
├── tests/
│   └── test_experiment_infra.py     # 4 个基础设施测试
└── results/                         # 实验产物
    ├── experiments/                 # 扁平 JSONL 结果（跨运行聚合用）
    └── runs/                        # 结构化运行产物（dataset/profile/时间戳）
```

---

## 4. 每个核心文件的详细说明

### 4.1 `main.py` — 工作流编排

用 **LangGraph StateGraph** 构建整个工作流图：

```
START → Red → Green → Test Runner
                    ↓ test_passed?
                    ↓ YES
              Code Review Node → L2 → L3 → Evaluation
                                              ↓ fail? → 回到 L2
                                              ↓ pass  → END
                    ↓ NO
              LDB Debug → 回到 Green
```

关键功能：
- `build_workflow(runtime_config)` — 根据 profile 动态构建图（某些节点可被禁用）
- `route_after_test()` — 三件套退出条件：通过 / 超限 / 连续相同错误
- `should_retry_refactor()` — Evaluation 不通过时的回环路由
- `run_experiment_once()` — 单次实验入口（CLI + benchmark 共享）

### 4.2 `state.py` — 全局共享状态

定义 `AgentState(TypedDict)`，包含 ~50 个字段，是关键数据流载体：

| 类别 | 关键字段 |
|---|---|
| 代码演进 | `code`, `l1_code`, `l2_code`, `l3_code` |
| 测试与调试 | `test_cases`, `test_passed`, `test_error`, `last_failed_test` |
| 代码审查 | `code_review_report`, `cr_few_shot_examples` |
| CISQ 规则 | `standard_constraints`, `activated_rule_ids`, `activated_dimensions` |
| 仲裁判定 | `dynamic_verdict`, `static_verdict`, `final_verdict`, `failed_rule_ids` |
| 实验元数据 | `profile_name`, `run_id`, `dataset_name`, `task_id` |
| 控制字段 | `workflow_status`, `stop_reason`, `hide_tests_in_green` |

### 4.3 `experiment_profiles.py` — 实验配置系统

通过 profile 叠加机制实现不同基线/消融，不修改代码：

```python
_base_profile()    # 全功能默认配置
    +
PROFILE_OVERRIDES  # 每个 profile 的差异配置
    ↓
build_runtime_config("b0_direct_generation")  # 运行时自动合并
```

当前 7 个 profile：

| Profile | 说明 | 禁用节点 |
|---|---|---|
| `ours` | 完整系统 | rar4is, ldb_debug |
| `b0_direct_generation` | 最朴素基线 | red, code_review, l2, l3, eval |
| `b2_error_feedback` | TDD + 纯错误反馈 | code_review, l2, l3, eval |
| `b_cr_only` | TDD + CR 打分（不重构） | l2, l3, eval |
| `ablation_no_cr` | 去掉 CR | code_review |
| `ablation_no_l2l3` | 去掉重构层 | l2, l3 |
| `ablation_no_eval` | 去掉验证 | evaluation |

路由函数（`next_after_cr`, `next_after_test_pass` 等）根据 profile 决定图中边走向。

### 4.4 `agents/code_review_node.py` — ★ 认知分层代码审查 ★

这是整个框架区别于普通 AI-TDD 的核心节点。

**四维度独立 Review**

| 维度 | ISO 25010 映射 | 关注点 | 下游消费 |
|---|---|---|---|
| Security | 安全性 | 注入漏洞、硬编码密钥、不安全输入 | **L2** |
| Reliability | 可靠性 | 未处理异常、空值、边界条件 | **L2** |
| Maintainability | 可维护性 | 复杂度、死代码、命名、重复逻辑 | **L3** |
| Performance Efficiency | 性能效率 | 嵌套循环、重复计算、低效数据结构 | **L3** |

每个维度由一个**独立 Reviewer** 审查，注入该维度的 CISQ 标准规则作为参考。

**幻觉过滤机制**

代码审查模型（尤其是小模型）经常"看到"不存在的问题。CR 节点对每个维度的 findings 做批量核验 —— Evaluation Agent 逐条检查代码中是否真的有对应证据，只保留能够在代码中定位的发现。

**输出结构**

```python
CodeReviewReport:
    security: DimensionReview      # score 1-5, findings[], suggestions[], severity, needs_refactoring
    reliability: DimensionReview
    maintainability: DimensionReview
    performance_efficiency: DimensionReview
    overall_score: float           # 四维度平均分
    needs_refactoring: bool
    review_summary: str
```

### 4.5 `agents/green_node.py` — 功能代码生成

两种模式：

| 场景 | Prompt 策略 |
|---|---|
| **首次生成** | 直接生成 prompt（含 requirement + test_cases，B0 中测试被隐藏） |
| **修复重试** | LDB repair prompt（含 test error + LDB block trace + 可疑代码块） |

关键控制：
- `hide_tests_in_green: true` → B0 不透露测试用例，保证公平对比
- 支持 `green_attempts` 重试上限

### 4.6 `agents/ldb_debug_node.py` — Block 级调试

参考 [LDB 论文](https://arxiv.org/abs/2312.15108) 的 block 判错协议：

1. 用 `local_ldb.py` 的 AST + sys.settrace 对代码分块并采集执行轨迹
2. 构造 few-shot block 判错 prompt
3. LLM 逐 block 判断逻辑是否正确
4. 产出 `suspicious_block` + `block_reports` → 回传给 Green 定向修复

### 4.7 `agents/l2_refactor_node.py` — 安全/可靠性定向加强

消费 `code_review_report.security` + `.reliability` 的 findings/suggestions，**只修复审查发现的特定问题**，不套通用规则。L1 代码基线在此冻结，供 Evaluation 做语义比对。

### 4.8 `agents/l3_refactor_node.py` — 可维护性/性能定向加强

消费 `code_review_report.maintainability` + `.performance_efficiency` 的 findings/suggestions，优化代码结构和效率。L3 输出代码供 Evaluation 与 L1 基线比对。

### 4.9 `agents/evaluation_node.py` — 双重审判

| 审判 | 方式 | 判定依据 |
|---|---|---|
| 动态仲裁 | sys.settrace 轨迹采集 → weak/strong 比对 | L1 与 L3 代码均通过测试 |
| 静态审判 | LLM 检查 CISQ 规则是否消除 | failed_rule_ids 为空则通过 |

只有两个审判都 pass，`final_verdict` 才为 `pass`。

### 4.10 `agents/test_runner_node.py` — 测试执行

在临时目录执行 pytest，解析错误输出，维护连续相同错误计数防止死循环。

### 4.11 `run_benchmark.py` — 批量实验入口

完整 CLI：
```bash
uv run python run_benchmark.py \
  --manifest-name shared_baseline_subset_v1 \
  --profile b0_direct_generation
```

自动完成：HumanEval pass@k 评估、结果 JSONL 记录、summary.json 汇总、aggregate.json 聚合。

### 4.12 `benchmark_inputs.py` — 数据集适配层

统一 MBPP 和 HumanEval 的输入格式为 `BenchmarkTask`（requirement + test_cases + entry_point）。支持 manifest 文件定义任务子集。

### 4.13 `knowledge/` — CISQ 规则库

- `CISQ_mapping_python_benchmark_subset.json` — CR 节点在**模块加载时**读取，按四维度分组注入每个 Reviewer 的 prompt
- `CISQ_mapping.json` — 完整 80+ 条 CISQ 规则（ISO 25010 维度映射）
- `cisq_rules_seed.json` — 8 条精选规则，用于 L3 prompt 加固

---

## 5. 快速开始

### 5.1 环境准备

```bash
# 安装依赖
uv sync

# 配置 API Key（硅基流动）
# 编辑 .env 文件，填入你的 SILICONFLOW_API_KEY
```

`.env` 文件格式：
```
SILICONFLOW_API_KEY=sk-你的key
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
SILICONFLOW_MODEL=Qwen/Qwen2.5-7B-Instruct
```

支持切换任意 OpenAI 兼容 API，只需修改 `.env` 中的 key/url/model。

### 5.2 运行单个实验

```bash
uv run python run_benchmark.py --manifest-name shared_baseline_subset_v1 --profile b0_direct_generation
```

### 5.3 运行全量实验

```bash
# Baseline 对比组
uv run python run_benchmark.py --manifest-name shared_baseline_subset_v1 --profile b0_direct_generation
uv run python run_benchmark.py --manifest-name shared_baseline_subset_v1 --profile b2_error_feedback
uv run python run_benchmark.py --manifest-name shared_baseline_subset_v1 --profile b_cr_only
uv run python run_benchmark.py --manifest-name shared_baseline_subset_v1 --profile ours

# 消融实验
uv run python run_benchmark.py --manifest-name shared_baseline_subset_v1 --profile ablation_no_cr
uv run python run_benchmark.py --manifest-name shared_baseline_subset_v1 --profile ablation_no_l2l3
uv run python run_benchmark.py --manifest-name shared_baseline_subset_v1 --profile ablation_no_eval
```

### 5.4 结果查看

```bash
# 单运行查看
cat results/runs/<dataset>/<profile>/<timestamp>/summary.json

# 跨运行聚合
uv run python aggregate_results.py
```

---

## 6. 论文实验体系

### 6.1 实验对照逻辑

| 对比维度 | 对比组 | 说明 |
|---|---|---|
| TDD 主干效果 | B0 vs B2 | 直接生成 vs TDD + 错误反馈 |
| CR 系统效果 | B2 vs b_cr_only | TDD vs TDD + CR 评分 |
| CR + 重构联合效果 | b_cr_only vs ours | 仅打分不重构 vs 打分后定向加强 |
| CR 贡献（消融） | ours vs ablation_no_cr | 去掉 CR → L2/L3 失去修复目标 |
| 重构层贡献（消融） | ours vs ablation_no_l2l3 | 去掉 L2/L3 → 无质量提升 |
| 验证层贡献（消融） | ours vs ablation_no_eval | 去掉 Evaluation → 无语义漂移保护 |

### 6.2 数据集策略

| 数据集 | 规模 | 用途 |
|---|---|---|
| `shared_baseline_subset_v1` | 4 题 | 开发调试验证 |
| `baseline_extended_v1` | 25 题 | 主实验统计 |
| `quality_subset_v1` | 30 题 | 质量实验（含低质量 seed 实现） |
| `humaneval_plus_full` | 164 题 | HumanEval+ 全量 |

### 6.3 关键评估指标

| 类别 | 指标 | 来源 |
|---|---|---|
| **功能正确性** | Final Pass Rate, pass@1 | test_runner + HumanEval 官方评估 |
| **代码质量** | CR 四维度分数 (Security/Reliability/Maintainability/Performance) | code_review_node |
| **修复精准度** | 被修复的 findings 数量 / 总 findings | L2/L3 applied_fixes |
| **语义稳定性** | Dynamic Equivalence Pass Rate | evaluation_node |
| **规则合规** | Static Verdict Pass Rate, Remaining Failed Rules | evaluation_node |

### 6.4 指标在日志中的存储

每条实验记录 JSONL 包括 `final_pass` 和 `cr_*` 前缀的六个 CR 指标（overall_score, security_score, reliability_score, maintainability_score, performance_score, total_findings）。这些字段在 `experiment_logger.py` 的 `summarize_run()` 中自动抽取。

---

## 7. 技术栈

| 层 | 技术 | 用途 |
|---|---|---|
| 工作流 | LangGraph StateGraph | 有向图编排 + 条件路由 |
| LLM 调用 | outlines（主） + OpenAI SDK（fallback） | 结构化 JSON 生成 |
| LLM 模型 | SiliconFlow / DeepSeek / OpenAI | .env 自由切换 |
| 结构化输出 | Pydantic BaseModel | 所有节点的输出 schema |
| Block 调试 | AST + sys.settrace | 本地化 LDB tracer |
| 轨迹比对 | sys.settrace | 弱/强语义等价判定 |
| 测试执行 | pytest + subprocess | 临时目录隔离 |
| 结果评估 | HumanEval 官方 pass@k | 标准评估 |
| 日志 | JSONL + JSON | 兼容 pandas 后续分析 |

---

## 8. 代码编写原则

项目内部遵循以下约定：

1. **所有节点实现 `async def run(state: AgentState) -> AgentState` 接口**，返回增量状态
2. **所有结构化输出用 Pydantic BaseModel 定义**，`generate_with_outlines(prompt, output_model, fallback_data)` 保证不会因 LLM 失败而中断
3. **每个节点都写 review_comments 日志**，方便追踪决策链路
4. **profile 控制节点开关**，不在代码里 hardcode 流程差异
5. **CR → L2/L3 的数据流**：CR 输出 `code_review_report`，L2 读 security/reliability，L3 读 maintainability/performance_efficiency
6. **不接受用纯规则替换 LLM 审查**：CR 节点的语义理解必须经 LLM，L2/L3 的修复也必须经 LLM

---

## 9. 当前状态

| 节点 | 状态 | 说明 |
|---|---|---|
| green_node | ✅ 完整 | 首次生成 + LDB 修复两种 prompt |
| test_runner_node | ✅ 完整 | pytest + 错误解析 + 死循环防护 |
| ldb_debug_node | ✅ 完整 | AST 切块 + block 判错 + 多轮累积 |
| **code_review_node** | ✅ **完整** | 四维度独立审查 + 幻觉过滤 |
| l2_refactor_node | ✅ 完整 | 消费 security/reliability findings 定向修复 |
| l3_refactor_node | ✅ 完整 | 消费 maintainability/performance findings 定向修复 |
| evaluation_node | ✅ 完整 | 动态轨迹比对 + 静态 CISQ 审判 |
| red_node | ⚠️ 默认禁用 | LLM 生成测试，当前优先用数据集 ground-truth |
| rar4is_node | ⚠️ 默认禁用 | 规则激活逻辑完整，但 upstream L2/L3 不直接消费 |

数据流完整度：**全部节点链路已贯通**，CR → L2 → L3 → Evaluation 形成完整的"审查→定向加强→验证"闭环。

---

## 10. 新手导航

建议按以下顺序理解项目：

1. 先读 `state.py` — 理解数据如何在节点间流动
2. 再读 `main.py` — 理解工作流图和路由逻辑
3. 再读 `experiment_profiles.py` — 理解 profile 如何控制实验
4. 然后按数据流顺序读节点：
   - `green_node.py` → `test_runner_node.py` → `ldb_debug_node.py` → `code_review_node.py` → `l2_refactor_node.py` → `l3_refactor_node.py` → `evaluation_node.py`
5. 最后看 `run_benchmark.py` + `benchmark_inputs.py` — 理解实验如何批量运行

如果你想基于此框架做改进，优先改动点：
- **CR 维度定义**：在 `code_review_node.py` 的 `_DIMENSION_GUIDES` 中调整各维度关注点
- **L2/L3 重写策略**：在 `_extract_findings()` 中选择性地消费 CR 输出
- **新 profile**：在 `experiment_profiles.py` 的 `PROFILE_OVERRIDES` 中新增
