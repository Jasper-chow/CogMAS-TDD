"""
CogMAS-TDD 实验结果分析与可视化 (完整版)
读取各 profile 最新的 164 题完整跑，输出对比表格和图表。
"""
import json
import numpy as np
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

for font in ["SimHei", "Microsoft YaHei", "PingFang SC", "DejaVu Sans"]:
    try:
        matplotlib.font_manager.findfont(font, fallback_to_default=False)
        plt.rcParams["font.family"] = font
        break
    except Exception:
        pass
plt.rcParams["axes.unicode_minus"] = False

RESULTS_DIR = Path(__file__).parent / "results" / "runs" / "humaneval_plus"
OUT_DIR = Path(__file__).parent / "results" / "analysis_charts"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_jsonl(path):
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def latest_records(profile_name):
    """Return records list from the most recent run directory for a profile."""
    profile_dir = RESULTS_DIR / profile_name
    if not profile_dir.exists():
        return []
    runs = sorted(profile_dir.iterdir(), reverse=True)
    for run in runs:
        rfile = run / "records.jsonl"
        if rfile.exists():
            return load_jsonl(rfile)
    return []


# ═══════════════════════════════════════════════════════════════════
# 1. Load all profiles
# ═══════════════════════════════════════════════════════════════════

PROFILES = [
    ("b0_direct_generation",  "B0 (直接生成)"),
    ("b2_error_feedback",     "B2 (错误反馈)"),
    ("b_cr_only",             "B_CR (仅CR)"),
    ("ablation_no_cr",        "消融: 无CR"),
    ("ablation_no_l2l3",      "消融: 无L2/L3"),
    ("ablation_no_eval",      "消融: 无Eval"),
    ("ours",                  "Ours (完整)"),
]

data = {}
for key, label in PROFILES:
    recs = latest_records(key)
    data[key] = {"label": label, "records": recs}

print("=== 数据加载 ===")
for key, label in PROFILES:
    n = len(data[key]["records"])
    print(f"  {label:20s}: {n} records")


# ═══════════════════════════════════════════════════════════════════
# 2. Per-profile statistics
# ═══════════════════════════════════════════════════════════════════

def stats(records):
    if not records:
        return {}
    n = len(records)
    passed = sum(1 for r in records if r.get("test_passed"))
    timeouts = sum(1 for r in records if r.get("stop_reason") == "per_task_timeout")
    wall_times = [r.get("wall_seconds", 0) for r in records]
    llm_calls = [r.get("llm_calls", 0) for r in records]
    stop_reasons = {}
    for r in records:
        sr = r.get("stop_reason", "unknown")
        stop_reasons[sr] = stop_reasons.get(sr, 0) + 1

    cr_overall  = [r["cr_overall_score"]        for r in records if r.get("cr_overall_score")        is not None]
    cr_sec      = [r["cr_security_score"]        for r in records if r.get("cr_security_score")       is not None]
    cr_rel      = [r["cr_reliability_score"]     for r in records if r.get("cr_reliability_score")    is not None]
    cr_main     = [r["cr_maintainability_score"] for r in records if r.get("cr_maintainability_score") is not None]
    cr_perf     = [r["cr_performance_score"]     for r in records if r.get("cr_performance_score")    is not None]

    return {
        "n": n,
        "passed": passed,
        "pass_rate": passed / n,
        "timeouts": timeouts,
        "avg_wall": np.mean(wall_times),
        "avg_llm_calls": np.mean(llm_calls),
        "stop_reasons": stop_reasons,
        "cr_overall": cr_overall,
        "cr_sec": cr_sec,
        "cr_rel": cr_rel,
        "cr_main": cr_main,
        "cr_perf": cr_perf,
    }

print("\n=== 完整对比表 (164题) ===")
print(f"{'Profile':<22} {'n':>4} {'Pass':>6} {'Pass%':>7} {'Timeouts':>9} {'AvgWall':>8} {'AvgLLM':>7}")
print("-" * 72)

profile_stats = {}
for key, label in PROFILES:
    s = stats(data[key]["records"])
    profile_stats[key] = s
    if s:
        print(f"{label:<22} {s['n']:>4} {s['passed']:>6} {s['pass_rate']*100:>6.1f}% "
              f"{s['timeouts']:>9} {s['avg_wall']:>7.1f}s {s['avg_llm_calls']:>6.1f}")
    else:
        print(f"{label:<22} {'N/A':>4}")

# Ablation deltas vs ours
ours_s = profile_stats.get("ours", {})
ours_pass = ours_s.get("pass_rate", 0)
print(f"\n=== 消融对比 (vs Ours {ours_pass*100:.1f}%) ===")
for key in ["ablation_no_cr", "ablation_no_l2l3", "ablation_no_eval"]:
    s = profile_stats.get(key, {})
    if s:
        delta = s["pass_rate"] - ours_pass
        label = data[key]["label"]
        print(f"  {label:<20}: {s['pass_rate']*100:.1f}%  (Δ {delta*100:+.1f}pp vs ours)")

# B0/B2/BCR vs ours
print(f"\n=== Baseline 对比 (vs Ours {ours_pass*100:.1f}%) ===")
for key in ["b0_direct_generation", "b2_error_feedback", "b_cr_only"]:
    s = profile_stats.get(key, {})
    if s:
        delta = s["pass_rate"] - ours_pass
        label = data[key]["label"]
        print(f"  {label:<22}: {s['pass_rate']*100:.1f}%  (Δ {delta*100:+.1f}pp vs ours)")

# CR scores
print(f"\n=== CR 分数 (有 CR 的 profile) ===")
for key in ["ours", "b_cr_only"]:
    s = profile_stats.get(key, {})
    if s and s.get("cr_overall"):
        label = data[key]["label"]
        scores = s["cr_overall"]
        print(f"  {label}: overall={np.mean(scores):.2f}±{np.std(scores):.2f} "
              f"(sec={np.mean(s['cr_sec']):.2f}, rel={np.mean(s['cr_rel']):.2f}, "
              f"main={np.mean(s['cr_main']):.2f}, perf={np.mean(s['cr_perf']):.2f})")

# Stop reason distribution for ours
print(f"\n=== Ours 终止原因分布 ===")
for sr, cnt in sorted(ours_s.get("stop_reasons", {}).items(), key=lambda x: -x[1]):
    pct = cnt / ours_s["n"] * 100
    print(f"  {sr:<35}: {cnt:>3}  ({pct:.1f}%)")


# ═══════════════════════════════════════════════════════════════════
# 3. Charts
# ═══════════════════════════════════════════════════════════════════

COLORS_MAP = {
    "b0_direct_generation":  "#4C72B0",
    "b2_error_feedback":     "#64B5CD",
    "b_cr_only":             "#8172B2",
    "ablation_no_cr":        "#CCB974",
    "ablation_no_l2l3":      "#C44E52",
    "ablation_no_eval":      "#DD8452",
    "ours":                  "#2ecc71",
}

fig, axes = plt.subplots(2, 3, figsize=(20, 12))
fig.suptitle("CogMAS-TDD 实验结果完整对比 (HumanEval+ 164题)", fontsize=16, fontweight="bold", y=0.99)


# ── 图1: 所有 profile 通过率柱状图 ──────────────────────────────
ax1 = axes[0, 0]
keys_ordered = [k for k, _ in PROFILES]
labels_ordered = [data[k]["label"] for k in keys_ordered]
pass_rates = [profile_stats[k].get("pass_rate", 0) * 100 for k in keys_ordered]
colors = [COLORS_MAP[k] for k in keys_ordered]

bars = ax1.bar(range(len(keys_ordered)), pass_rates, color=colors, alpha=0.85,
               edgecolor="white", linewidth=1.5)
for bar, val in zip(bars, pass_rates):
    ax1.text(bar.get_x() + bar.get_width() / 2, val + 0.8,
             f"{val:.1f}%", ha="center", va="bottom", fontsize=9, fontweight="bold")

ax1.set_xticks(range(len(keys_ordered)))
ax1.set_xticklabels(labels_ordered, fontsize=8.5, rotation=15, ha="right")
ax1.set_ylabel("测试通过率 (%)", fontsize=11)
ax1.set_title("所有 Profile 通过率对比", fontsize=13, fontweight="bold")
ax1.set_ylim(0, 105)
ax1.axhline(y=pass_rates[-1], color=COLORS_MAP["ours"], linestyle="--", alpha=0.5, linewidth=1.5)
ax1.spines["top"].set_visible(False)
ax1.spines["right"].set_visible(False)


# ── 图2: 消融对比 (ours vs ablations) ───────────────────────────
ax2 = axes[0, 1]
abl_keys  = ["ours", "ablation_no_cr", "ablation_no_l2l3", "ablation_no_eval"]
abl_labels = ["Ours\n(完整)", "消融:\n无CR", "消融:\n无L2/L3", "消融:\n无Eval"]
abl_rates = [profile_stats[k].get("pass_rate", 0) * 100 for k in abl_keys]
abl_colors = [COLORS_MAP[k] for k in abl_keys]

bars2 = ax2.bar(range(len(abl_keys)), abl_rates, color=abl_colors, alpha=0.85,
                edgecolor="white", linewidth=1.5, width=0.6)
for bar, val, key in zip(bars2, abl_rates, abl_keys):
    delta = val - abl_rates[0]
    label_str = f"{val:.1f}%"
    if key != "ours":
        label_str += f"\n({delta:+.1f}pp)"
    ax2.text(bar.get_x() + bar.get_width() / 2, val + 0.5,
             label_str, ha="center", va="bottom", fontsize=10, fontweight="bold")

ax2.set_xticks(range(len(abl_keys)))
ax2.set_xticklabels(abl_labels, fontsize=11)
ax2.set_ylabel("测试通过率 (%)", fontsize=11)
ax2.set_title("消融实验对比", fontsize=13, fontweight="bold")
ax2.set_ylim(0, 105)
ax2.axhline(y=abl_rates[0], color=COLORS_MAP["ours"], linestyle="--", alpha=0.5, linewidth=1.5)
ax2.spines["top"].set_visible(False)
ax2.spines["right"].set_visible(False)


# ── 图3: Baseline 阶梯对比 (b0 → b2 → b_cr → ours) ─────────────
ax3 = axes[0, 2]
ladder_keys   = ["b0_direct_generation", "b2_error_feedback", "b_cr_only", "ours"]
ladder_labels = ["B0\n直接生成", "B2\n错误反馈", "B_CR\n仅CR", "Ours\n完整"]
ladder_rates  = [profile_stats[k].get("pass_rate", 0) * 100 for k in ladder_keys]
ladder_colors = [COLORS_MAP[k] for k in ladder_keys]

bars3 = ax3.bar(range(len(ladder_keys)), ladder_rates, color=ladder_colors, alpha=0.85,
                edgecolor="white", linewidth=1.5, width=0.6)
for i, (bar, val) in enumerate(zip(bars3, ladder_rates)):
    if i > 0:
        delta = val - ladder_rates[i - 1]
        ax3.text(bar.get_x() + bar.get_width() / 2, val + 0.8,
                 f"{val:.1f}%\n({delta:+.1f}pp)", ha="center", va="bottom",
                 fontsize=10, fontweight="bold")
    else:
        ax3.text(bar.get_x() + bar.get_width() / 2, val + 0.8,
                 f"{val:.1f}%", ha="center", va="bottom", fontsize=10, fontweight="bold")

ax3.set_xticks(range(len(ladder_keys)))
ax3.set_xticklabels(ladder_labels, fontsize=11)
ax3.set_ylabel("测试通过率 (%)", fontsize=11)
ax3.set_title("Baseline 阶梯提升", fontsize=13, fontweight="bold")
ax3.set_ylim(0, 105)
ax3.spines["top"].set_visible(False)
ax3.spines["right"].set_visible(False)


# ── 图4: CR 四维度 (ours vs b_cr_only) ──────────────────────────
ax4 = axes[1, 0]
dims = ["Security", "Reliability", "Maintainability", "Performance"]
dim_keys_map = {"Security": "cr_sec", "Reliability": "cr_rel",
                "Maintainability": "cr_main", "Performance": "cr_perf"}

cr_profiles = [("ours", COLORS_MAP["ours"]), ("b_cr_only", COLORS_MAP["b_cr_only"])]
x = np.arange(len(dims))
w = 0.35

for idx, (ckey, ccolor) in enumerate(cr_profiles):
    s = profile_stats[ckey]
    means = [np.mean(s[dim_keys_map[d]]) if s.get(dim_keys_map[d]) else 0 for d in dims]
    offset = (idx - 0.5) * w
    bars_cr = ax4.bar(x + offset, means, w, color=ccolor, alpha=0.8,
                      label=data[ckey]["label"], edgecolor="white")
    for bar, val in zip(bars_cr, means):
        ax4.text(bar.get_x() + bar.get_width() / 2, val + 0.04,
                 f"{val:.2f}", ha="center", fontsize=9, fontweight="bold")

ax4.set_xticks(x)
ax4.set_xticklabels(dims, fontsize=11)
ax4.set_ylabel("CISQ 维度分数 (1-5)", fontsize=11)
ax4.set_title("CR 四维度代码质量\n(有CR的profile)", fontsize=12, fontweight="bold")
ax4.set_ylim(0, 5.8)
ax4.axhline(y=4.0, color="gray", linestyle="--", alpha=0.4)
ax4.legend(fontsize=10)
ax4.spines["top"].set_visible(False)
ax4.spines["right"].set_visible(False)


# ── 图5: Ours 终止原因饼图 ───────────────────────────────────────
ax5 = axes[1, 1]
stop_map = {
    "evaluation_passed":         "评估通过",
    "max_green_attempts":        "生成超限",
    "max_refactor_retries":      "重构超限",
    "finished_without_evaluation": "无评估完成",
    "per_task_timeout":          "超时",
}
ours_stop = ours_s.get("stop_reasons", {})
if ours_stop:
    sr_labels = [stop_map.get(k, k) for k in ours_stop]
    sr_values = list(ours_stop.values())
    sr_colors = []
    for k in ours_stop:
        if "passed" in k or "without" in k:
            sr_colors.append("#2ecc71")
        elif "green" in k:
            sr_colors.append("#9b59b6")
        elif "refactor" in k:
            sr_colors.append("#e74c3c")
        else:
            sr_colors.append("#e67e22")
    wedges, texts, autotexts = ax5.pie(
        sr_values, labels=sr_labels, colors=sr_colors,
        autopct="%1.0f%%", startangle=140,
        textprops={"fontsize": 10},
        wedgeprops={"edgecolor": "white", "linewidth": 2},
    )
    for at in autotexts:
        at.set_fontsize(11)
        at.set_fontweight("bold")
ax5.set_title(f"Ours 终止原因分布\n(n={ours_s.get('n', 0)}题)", fontsize=12, fontweight="bold")


# ── 图6: 平均 LLM 调用次数对比 ──────────────────────────────────
ax6 = axes[1, 2]
llm_keys = [k for k, _ in PROFILES]
llm_labels = [data[k]["label"] for k in llm_keys]
llm_means = [profile_stats[k].get("avg_llm_calls", 0) for k in llm_keys]
llm_colors = [COLORS_MAP[k] for k in llm_keys]

bars6 = ax6.bar(range(len(llm_keys)), llm_means, color=llm_colors, alpha=0.85,
                edgecolor="white", linewidth=1.5)
for bar, val in zip(bars6, llm_means):
    ax6.text(bar.get_x() + bar.get_width() / 2, val + 0.05,
             f"{val:.1f}", ha="center", va="bottom", fontsize=10, fontweight="bold")

ax6.set_xticks(range(len(llm_keys)))
ax6.set_xticklabels(llm_labels, fontsize=8.5, rotation=15, ha="right")
ax6.set_ylabel("平均 LLM 调用次数 / 题", fontsize=11)
ax6.set_title("LLM 调用效率", fontsize=13, fontweight="bold")
ax6.spines["top"].set_visible(False)
ax6.spines["right"].set_visible(False)


plt.tight_layout(rect=[0, 0, 1, 0.97])
out_path = OUT_DIR / "cogmas_tdd_full_analysis.png"
plt.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
print(f"\n[OK] 图表已保存: {out_path}")
plt.close()
