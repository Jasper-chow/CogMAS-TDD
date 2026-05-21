# CogMAS-TDD 项目现状总览

> **最后更新**: 2026-05-18
> **整体目标**: 提出并验证一个 `AI + TDD + 认知分层 + LDB + 规则约束` 的自动化代码生成与重构框架
> **实验参考**: [EXPERIMENT_PLAN.md](file:///f:/LLM/LLM_learning/EXPERIMENT_PLAN.md)

---

## 1. 项目架构概览

```
LLM_learning/
├── agents/              ← 7 个工作流节点（认知分层多智能体）
│   ├── rar4is_node.py           # 规则检索与激活
│   ├── red_node.py              # 测试先行生成
│   ├── green_node.py            # 功能代码生成
│   ├── ldb_debug_node.py        # block 级调试
│   ├── test_runner_node.py      # pytest 执行器
│   ├── l2_refactor_node.py      # 工程加固层
│   ├── l3_refactor_node.py      # 架构优化层
│   └── evaluation_node.py       # 动态/静态双审判
├── utils/               ← 工具与基础设施层
│   ├── helpers.py               # LLM 调用、结构化生成、CISQ 规则
│   ├── local_ldb.py             # 本地化 LDB block tracer（AST + sys.settrace）
│   ├── ldb_adapter.py           # LLMDebugger 迁移适配层
│   ├── ldb_prompt_protocol.py   # LDB 风格 few-shot prompt 协议
│   ├── executor.py              # 轨迹采集与弱/强等价比对
│   ├── experiment_logger.py     # 统一 JSONL 结果记录
│   ├── result_layout.py         # 运行产物目录管理
│   └── humaneval_official.py    # HumanEval 官方 pass@k 评估
├── 实验基础设施
│   ├── main.py                  # LangGraph 工作流 + 单实验入口
│   ├── state.py                 # 全局共享状态定义
│   ├── experiment_profiles.py   # 9 个实验 profile（baseline + ablation + ours）
│   ├── run_benchmark.py         # 批量实验 CLI 入口
│   ├── benchmark_inputs.py      # MBPP/HumanEval 数据加载 + manifest 系统
│   └── aggregate_results.py     # 多维度结果聚合
├── 数据资产
│   ├── knowledge/               # CISQ/ISO 规则库
│   │   ├── CISQ_mapping.json            # 80+ 条 CISQ 规则（ISO 维度映射）
│   │   ├── cisq_rules_seed.json         # 8 条种子规则
│   │   └── CISQ_mapping_python_benchmark_subset.json
│   ├── benchmark_manifests/    # 实验任务清单
│   │   ├── shared_baseline_subset_v1.json  # 4 题共享子集 (MBPP+HumanEval)
│   │   ├── humaneval_smoke_v1.json         # 2 题 HumanEval smoke 集
│   │   ├── smoke_dual_dataset.json
│   │   └── quality_subset_template.json    # 质量约束子集模板（仅1题占位）
│   ├── human-eval/             # HumanEval 完整数据集 + 官方评估脚本
│   ├── MBPP/                   # MBPP 完整数据集
│   └── LLMDebugger/            # LDB 论文参考实现（含 tracer、执行器、数据集）
├── tests/
│   └── test_experiment_infra.py  # 4 个基础测试
└── results/
    ├── experiments/             # 扁平 JSONL 结果（跨运行合并）
    └── runs/                    # 结构化运行产物（按 dataset/profile/时间戳 组织）
```

---

## 2. 节点模块完成度评估

### 2.1 `rar4is_node` — 规则检索与激活

| 维度 | 状态 | 说明 |
|---|---|---|
| LLM 集成 | ✅ 通 | 读取文本触发词，调用 `detect_active_dimensions()` + `select_cisq_rules()` |
| 规则数据 | ✅ 有 | 8 条种子规则 + 80+ 条完整 CISQ 映射 |
| 下游消费 | ❌ 断链 | L2/L3 是空壳，规则激活后不产生实际代码变更 |
| **整体** | ⚠️ **70%** | 规则检索本身可用，但下游 L2/L3 不消费，规则约束链路断裂 |

### 2.2 `red_node` — 测试先行生成

| 维度 | 状态 | 说明 |
|---|---|---|
| LLM 集成 | ✅ 通 | 用 `generate_with_outlines()` 生成结构化 pytest 代码 |
| Fallback | ✅ 有 | LLM 不可用时生成 `def test_placeholder() -> assert True` |
| Profile 控制 | ✅ 通 | B0/B2 中自动禁用（通过 `experiment_profiles.py`） |
| 测试质量 | ⚠️ 基础 | 未接入 benchmark 的 ground-truth 测试，仅靠 prompt 生成 |
| **整体** | ✅ **90%** | 功能完整，唯一缺口是 benchmark 测试复用 |

### 2.3 `green_node` — 功能代码生成

| 维度 | 状态 | 说明 |
|---|---|---|
| LLM 集成 | ✅ 通 | `generate_with_outlines()` → `GreenNodeOutput(code, explanation)` |
| LDB 修复协议 | ✅ 有 | 支持 block debug history 传入 prompt 做定向修复 |
| `hide_tests_in_green` | ✅ 已修复 | B0 不再看到测试用例（2026-05-18 修复） |
| 重试控制 | ✅ 通 | `green_attempts` 计数，`max_green_attempts` 上限，`same_error_streak` 防死循环 |
| **整体** | ✅ **95%** | 核心功能完备 |

### 2.4 `ldb_debug_node` — Block 级调试

| 维度 | 状态 | 说明 |
|---|---|---|
| 本地 LDB tracer | ✅ 完整 | [local_ldb.py](file:///f:/LLM/LLM_learning/utils/local_ldb.py) AST 切块 + sys.settrace 追踪 |
| LLMDebugger 适配 | ✅ 完整 | [ldb_adapter.py](file:///f:/LLM/LLM_learning/utils/ldb_adapter.py) 可复用 LLMDebugger 原版 tracer |
| LDB Prompt 协议 | ✅ 完整 | [ldb_prompt_protocol.py](file:///f:/LLM/LLM_learning/utils/ldb_prompt_protocol.py) few-shot block 判错协议 |
| 多轮 debug 累积 | ✅ 有 | `ldb_debug_sessions` 保留最近 3 轮 debug history |
| 启发式 fallback | ✅ 有 | LLM 不可用时自动生成启发式 block report |
| **整体** | ✅ **95%** | 核心功能完备，与原版 LDB 论文协议对齐良好 |

### 2.5 `test_runner_node` — 测试执行器

| 维度 | 状态 | 说明 |
|---|---|---|
| pytest 执行 | ✅ 通 | 临时目录 + `subprocess.run(pytest ...)` |
| 错误解析 | ✅ 有 | 抽取 assert 行 + 真实输出摘要 |
| 连续相同错误检测 | ✅ 有 | `same_error_streak` 防死循环 |
| 超时保护 | ✅ 有 | 60s 超时 |
| **整体** | ✅ **100%** | 功能完整 |

### 2.6 `l2_refactor_node` — 工程加固层

| 维度 | 状态 | 说明 |
|---|---|---|
| 规则读取 | ✅ 有 | 从 `standard_constraints.rules_by_dimension` 读取 security/reliability 规则 |
| LLM 重构 | ❌ **空壳** | **不实际调用 LLM，不修改代码** |
| 输出 | ❌ 无 | 仅向 `review_comments` 写入日志 |
| **整体** | ❌ **10%** | 仅完成规则读取框架，核心重构逻辑缺失 |

### 2.7 `l3_refactor_node` — 架构优化层

| 维度 | 状态 | 说明 |
|---|---|---|
| 规则读取 | ✅ 有 | 从 `standard_constraints.rules_by_dimension` 读取 maintainability/performance 规则 |
| LLM 重构 | ❌ **空壳** | **不实际调用 LLM，不修改代码** |
| 输出 | ❌ 无 | 仅向 `review_comments` 写入日志，写入 `l3_code` 为当前代码快照 |
| **整体** | ❌ **10%** | 与 L2 同，仅完成规则读取框架 |

### 2.8 `evaluation_node` — 动态/静态双审判

| 维度 | 状态 | 说明 |
|---|---|---|
| 轨迹采集 | ✅ 通 | [executor.py](file:///f:/LLM/LLM_learning/utils/executor.py) `sys.settrace` 逐行采集 |
| 弱等价比对 | ✅ 通 | `compare_traces_weak()` 函数名 + 变量键集合一致 |
| 强等价比对 | ✅ 通 | `compare_traces_strong()` 行号 + 变量值 repr 一致 |
| 静态 CISQ 审判 | ✅ 通 | LLM 检查 failed_rule_ids + 启发式 fallback |
| 回环重试 | ✅ 通 | `should_retry_refactor()` → L2/L3 回环 |
| 实际效果 | ❌ **虚** | L2/L3 不修改代码，L1=L3，轨迹永远等价 |
| **整体** | ⚠️ **80%** | 机制完整，但因 L2/L3 空壳导致无实际意义 |

---

## 3. 实验基础设施完成度

| 组件 | 状态 | 说明 |
|---|---|---|
| `experiment_profiles.py` | ✅ | 9 个 profile：ours / B0-B4 / 4 个 ablation |
| `run_benchmark.py` | ✅ | 完整 CLI：`--profile --manifest-name --limit --seed-source` 等 |
| `benchmark_inputs.py` | ✅ | MBPP + HumanEval 双数据集加载 + manifest 系统 |
| `aggregate_results.py` | ✅ | 多维度聚合：profile、dataset、profile+dataset |
| `humaneval_official.py` | ✅ | 标准 pass@k 评估，含 Windows 兼容 |
| `result_layout.py` | ✅ | 按 dataset/profile/时间戳 组织运行目录 |
| MBPP 官方评估 | ❌ | 仅有 HumanEval 的 pass@k，MBPP 缺失对应脚本 |

---

## 4. 数据资产完成度

| 资产 | 状态 | 说明 |
|---|---|---|
| HumanEval (164 题) | ✅ | 完整数据集 + 官方评估脚本可用 |
| MBPP (~500 题) | ✅ | 完整数据集可用 (`sanitized-mbpp.json`) |
| CISQ 规则库 | ✅ | 8 条种子 + 80+ 条完整映射 + ISO 维度分类 |
| shared_baseline_subset_v1 (4 题) | ✅ | 当前主实验子集 |
| humaneval_smoke_v1 (2 题) | ✅ | 用于快速 smoke 验证 |
| **质量约束子集 (30-50 题)** | ❌ **缺失** | 仅有 `quality_subset_template.json` 含 1 个占位条目 |
| LDB 原文参考实现 | ✅ | `LLMDebugger/` 含 tracer、执行器、数据集、论文 |

---

## 5. 已完成修复记录

| 日期 | 修复项 | 影响 |
|---|---|---|
| 2026-05-18 | 添加 SiliconFlow 提供商支持 | `.env` 可切换模型 |
| 2026-05-18 | 添加 `.env` 自动加载 (`load_dotenv`) | `helpers.py` + `run_benchmark.py` |
| 2026-05-18 | B0 增加 `hide_tests_in_green: true` | 修复 B0 模型看到测试用例的公平性问题 |
| 2026-05-18 | `state.py` 增加 `hide_tests_in_green` 字段 | profile 控制是否在 Green 提示词中透露测试 |
| 2026-05-18 | `green_node.py` 按 flag 决定传不传 test_cases | B0 profile 激活时 prompt 不含测试用例 |
| 2026-05-14 | B0 HumanEval pass@k 评估打通 | Windows 兼容 `_check_correctness_compatible` |
| 2026-05-14 | `generate_with_outlines()` SDK fallback | outlines 失败时回退 OpenAI-compatible SDK |

---

## 6. 与 EXPERIMENT_PLAN 的差距总览

### 6.1 可以直接跑的

| 实验 | 需要的方法 | 状态 |
|---|---|---|
| Experiment 1 — B0 | Direct Generation | ✅ |
| Experiment 1 — B1 | Vanilla AI-TDD | ✅ |
| Experiment 1 — B2 | Error Feedback | ✅ |
| Experiment 1 — B3 | AI-TDD + LDB Debug | ✅ |
| Ablation A | w/o LDB Debug | ✅ |
| Ablation B | w/o Evaluation | ✅ |
| Ablation C | w/o CISQ/ISO | ✅ |
| Ablation D | w/o Layering | ✅ |

### 6.2 不能跑或结果无意义

| 内容 | 阻塞原因 | 优先级 |
|---|---|---|
| **B4** (Layered Refactor) | L2/L3 是空壳 | 🔴 高 |
| **Ours** (CogMAS-TDD) | L2/L3 空壳→Evaluation 无意义 | 🔴 高 |
| **Experiment 2** (质量实验) | 质量约束子集未构造 + L2/L3 空壳 | 🔴 高 |
| **Case 1** (LDB Debug) | 需要从全量运行中筛选典型案例 | 🟡 中 |
| **Case 2** (Evaluation拦截) | L2/L3 不工作导致无数据 | 🔴 高 |
| **Case 3** (规则约束) | L2/L3 不工作导致无数据 | 🔴 高 |
| **RQ3** (分层重构有效性) | 完全无法回答 | 🔴 高 |
| **RQ4** (规则约束有效性) | 完全无法回答 | 🔴 高 |
| 全量 HumanEval/MBPP | 需要更多 API 配额 + 运行时间 | 🟡 中 |
| MBPP pass@k 评估 | 需编写 MBPP 官方评估脚本 | 🟢 低 |

---

## 7. 最高优先级待办

### 🔴 阻塞级（不做就无法出论文数据）

1. **L2/L3 实际重构逻辑**
   - 文件：[l2_refactor_node.py](file:///f:/LLM/LLM_learning/agents/l2_refactor_node.py)、[l3_refactor_node.py](file:///f:/LLM/LLM_learning/agents/l3_refactor_node.py)
   - 现状：仅写 `review_comments` 日志，不调用 LLM，不修改代码
   - 目标：参考 green_node 的模式，调用 `generate_with_outlines()`，基于 activated 规则真正生成重构代码
   - 阻塞：Experiment 2、RQ3、RQ4、Case 2、Case 3

2. **质量约束子集构造**
   - 文件：[quality_subset_template.json](file:///f:/LLM/LLM_learning/benchmark_manifests/quality_subset_template.json)
   - 现状：仅 1 个占位条目
   - 目标：从 MBPP/HumanEval 中选 30-50 题，为每道题写低质量但可运行的 seed 实现
   - 阻塞：Experiment 2

### 🟡 高优先级

3. **experiment 1 扩量运行**
   - 从 `shared_baseline_subset_v1` (4 题) 扩展到更大的子集
   - 同时跑 B0/B1/B2/B3 得到第一组可对比的实验数据

4. **LDB debug_node 排除 B0 中的不必要调用**
   - 当前 B0 profile 中 ldb_debug_node 已 disabled，但 green_node 仍使用 LDB repair prompt 协议
   - B0 首次生成应使用更简洁的 prompt（无 test_cases + 无 LDB history）

### 🟢 中低优先级

5. 从全量运行日志中挑选 Case 1 案例
6. 编写 MBPP 官方 pass@k 评估脚本
7. 扩到全量 HumanEval (164 题) 和 MBPP (500 题)
8. 成本统计（token 数、运行时间）

---

## 8. 数据流完整性

```
输入: Benchmark 题目 (requirement + test_cases)
  │
  ├─ RAR4IS ──→ activated_rule_ids + standard_constraints  [✅]
  │
  ├─ Red ──→ test_cases / red_output                        [✅]
  │
  ├─ Green ──→ code / green_output                          [✅ 含 LDB repair 协议]
  │     │
  │     ├─ Test Runner ←→ Green (retry loop)                [✅]
  │     │     └─ LDB Debug ──→ ldb_debug_report
  │     │                       └─ Green (定向修复)         [✅]
  │     │
  │     └─ Test PASS ──→ L2 Refactor ──→ ❌ 不修改代码
  │                         └─ L3 Refactor ──→ ❌ 不修改代码
  │                                └─ Evaluation            [⚠️ 轨迹相同→无意义]
  │                                     ├─ pass → END
  │                                     └─ fail → L2 (retry loop)
  │
  └─ Result Logger (JSONL + summary + aggregate)            [✅]
```

图例：✅ 正常 / ⚠️ 机制通但效果差 / ❌ 断链

**核心断链点**：`L2 Refactor` → `L3 Refactor` → 代码不变 → `Evaluation` 永远等价 → RQ3/RQ4 无法验证。

---

## 9. 技术栈

| 层 | 技术 | 用途 |
|---|---|---|
| 工作流编排 | LangGraph + LangChain | StateGraph 有向图 + TypedDict 状态 |
| LLM 调用 | outlines + OpenAI SDK | 结构化 JSON 生成 + SDK fallback |
| 模型提供 | SiliconFlow / DeepSeek / OpenAI | 通过 `.env` 自由切换 |
| Block 调试 | AST + sys.settrace | 本地化 LDB tracer |
| 测试执行 | pytest + subprocess | 临时目录隔离 |
| 数据评估 | HumanEval 官方脚本 | pass@k 标准评估 |
| 结果管理 | JSONL + JSON | 兼容 pandas/Excel 后期分析 |

---

## 10. 一句话总结

> **实验基础设施 90% 就绪，B0-B3 + 4 个消融可以立即产出数据来回答 RQ1（TDD 主干）和 RQ2（LDB 调试）。但 L2/L3 重构节点是空壳、质量约束子集未构造，导致 RQ3（分层重构）和 RQ4（规则约束）完全无法验证。当前最高优先级是在完成 Experiment 1 数据收集后，立即补上 L2/L3 的 LLM 重构逻辑和质量子集。**
