"""
实验 manifest 生成脚本。

产出物：
1. benchmark_manifests/baseline_extended_v1.json  — 25 题扩展基线集（无 seed）
2. benchmark_manifests/quality_subset_v1.json     — 30 题质量约束集（含 seed_code）

seed_code 要求：功能正确（通过测试）但含明显质量缺陷（CISQ 规则可检出）。
"""

from __future__ import annotations

import json
import sys
import types
import tempfile
from pathlib import Path
from typing import Any


# ──────────────────────────────────────────────
# 0. Seed 实现定义
# ──────────────────────────────────────────────

# 每条 seed_spec 格式：
#   (task_id, primary_cisq_issue, seed_code_str)

SEED_SPECS: list[tuple[str, str, str]] = [

# ─── 性能问题：CWE-407 ───────────────────────
("2", "CWE-407: O(n²) nested loops instead of set intersection",
"""def similar_elements(test_tup1, test_tup2):
    result = []
    for item in test_tup1:
        for item2 in test_tup2:
            if item == item2:
                already_in = False
                for existing in result:
                    if existing == item:
                        already_in = True
                        break
                if not already_in:
                    result.append(item)
    return tuple(result)
"""),

("9", "CWE-407: O(n²) rotation check instead of O(n) string-doubling trick",
"""def find_Rotations(s):
    n = len(s)
    for i in range(1, n + 1):
        rotated = ""
        for j in range(n):
            rotated += s[(i + j) % n]
        if rotated == s:
            return i
    return n
"""),

("88", "CWE-407: O(n²) frequency count instead of Counter",
"""def freq_count(list1):
    result = {}
    for item in list1:
        count = 0
        for other in list1:
            if item == other:
                count += 1
        result[item] = count
    return result
"""),

("130", "CWE-407: O(n²) max-occurrence search instead of Counter",
"""def max_occurrences(list1):
    max_count = 0
    max_item = list1[0]
    for item in list1:
        count = 0
        for other in list1:
            if item == other:
                count += 1
        if count > max_count:
            max_count = count
            max_item = item
    return max_item
"""),

("238", "CWE-407: O(n²) explicit loop instead of n*(n+1)/2 formula",
"""def number_of_substrings(str1):
    count = 0
    n = len(str1)
    for i in range(n):
        for j in range(i + 1, n + 1):
            count += 1
    return count
"""),

("395", "CWE-407: O(n²) first-non-repeating instead of single-pass dict",
"""def first_non_repeating_character(str1):
    for i in range(len(str1)):
        count = 0
        for j in range(len(str1)):
            if str1[i] == str1[j]:
                count += 1
        if count == 1:
            return str1[i]
    return None
"""),

("96", "CWE-407: O(n) divisor count instead of O(sqrt(n))",
"""def divisor(n):
    count = 0
    for i in range(1, n + 1):
        if n % i == 0:
            count += 1
    return count
"""),

("286", "CWE-407: O(n²k²) brute force instead of Kadane variant",
"""def max_sub_array_sum_repeated(a, n, k):
    extended = []
    for _ in range(k):
        for item in a:
            extended.append(item)
    total_len = n * k
    max_sum = extended[0]
    for i in range(total_len):
        current_sum = 0
        for j in range(i, total_len):
            current_sum += extended[j]
            if current_sum > max_sum:
                max_sum = current_sum
    return max_sum
"""),

("408", "CWE-407: generate all pairs + bubble sort instead of heap",
"""def k_smallest_pairs(nums1, nums2, k):
    all_pairs = []
    for x in nums1:
        for y in nums2:
            all_pairs.append([x, y])
    n = len(all_pairs)
    for i in range(n):
        for j in range(n - i - 1):
            if all_pairs[j][0] + all_pairs[j][1] > all_pairs[j+1][0] + all_pairs[j+1][1]:
                all_pairs[j], all_pairs[j+1] = all_pairs[j+1], all_pairs[j]
    return all_pairs[:k]
"""),

("123", "CWE-407: recomputes divisor sums without caching (double O(n) per pair)",
"""def amicable_numbers_sum(limit):
    def sum_divisors(n):
        total = 1
        for i in range(2, n):
            if n % i == 0:
                total += i
        return total

    result = 0
    for n in range(2, limit + 1):
        s = sum_divisors(n)
        if s != n and s <= limit:
            if sum_divisors(s) == n:
                result += n
    return result
"""),

# ─── 复杂度过高：CWE-1121 ────────────────────
("3", "CWE-1121: Excessive if/elif chain instead of loop for primality test",
"""def is_not_prime(n):
    if n <= 1:
        return True
    if n == 2:
        return False
    if n == 3:
        return False
    if n == 5:
        return False
    if n == 7:
        return False
    if n % 2 == 0:
        return True
    if n % 3 == 0:
        return True
    if n % 5 == 0:
        return True
    i = 7
    while i * i <= n:
        if n % i == 0:
            return True
        if n % (i + 4) == 0:
            return True
        if n % (i + 6) == 0:
            return True
        i += 10
    return False
"""),

("397", "CWE-1121: Many if/elif branches instead of sort+middle (8 branches for 3 numbers)",
"""def median_numbers(a, b, c):
    if a <= b <= c or c <= b <= a:
        return float(b)
    elif b <= a <= c or c <= a <= b:
        return float(a)
    elif a <= c <= b or b <= c <= a:
        return float(c)
    elif a == b and b == c:
        return float(a)
    elif a == b:
        return float(a)
    elif b == c:
        return float(b)
    elif a == c:
        return float(a)
    return float(-1)
"""),

("227", "CWE-1121: Nested if/elif instead of min() — high cyclomatic complexity",
"""def min_of_three(a, b, c):
    if a < b:
        if a < c:
            minimum = a
        else:
            if c < a:
                minimum = c
            else:
                minimum = a
    else:
        if b < c:
            minimum = b
        else:
            if c < b:
                minimum = c
            else:
                minimum = b
    return minimum
"""),

# ─── 循环内冗余资源消耗：CWE-1050 ────────────
("67", "CWE-1050: Recomputes sum of all prior rows in Bell triangle on each iteration",
"""def bell_number(n):
    triangle = []
    triangle.append([1])
    for i in range(1, n + 1):
        current_row = [triangle[i - 1][-1]]
        for j in range(len(triangle[i - 1])):
            current_row.append(current_row[-1] + triangle[i - 1][j])
        triangle.append(current_row)
        for prev_row in triangle[:-1]:
            _ = sum(prev_row)
    return triangle[n][0]
"""),

("68", "CWE-1050: Two separate full passes instead of one combined monotonicity check",
"""def is_Monotonic(A):
    is_inc = True
    is_dec = True
    for i in range(len(A) - 1):
        if A[i] > A[i + 1]:
            is_inc = False
    for i in range(len(A) - 1):
        if A[i] < A[i + 1]:
            is_dec = False
    return is_inc or is_dec
"""),

("84", "CWE-1050: Rebuilds full values array each call — no global memoization",
"""def sequence(n):
    if n == 1 or n == 2:
        return 1
    values = [0] * (n + 1)
    values[1] = 1
    values[2] = 1
    for i in range(3, n + 1):
        prev = values[i - 1]
        values[i] = values[prev] + values[i - prev]
    return values[n]
"""),

("65", "CWE-1050: Unnecessary type() check in inner loop instead of isinstance",
"""def recursive_list_sum(data_list):
    total = 0
    for item in data_list:
        if type(item) == list:
            total = total + recursive_list_sum(item)
        else:
            total = total + item
    return total
"""),

("247", "CWE-1050: DP table allocates full n×n even though n*(n+1)/2 suffices; dead verification loop",
"""def lps(s):
    n = len(s)
    table = [[0] * n for _ in range(n)]
    for i in range(n):
        table[i][i] = 1
    for cl in range(2, n + 1):
        for i in range(n - cl + 1):
            j = i + cl - 1
            if s[i] == s[j] and cl == 2:
                table[i][j] = 2
            elif s[i] == s[j]:
                table[i][j] = table[i + 1][j - 1] + 2
            else:
                table[i][j] = max(table[i][j - 1], table[i + 1][j])
    for i in range(n):
        if table[i][i] != 1:
            pass
    return table[0][n - 1]
"""),

("299", "CWE-1050: O(n²) — separate pass per unique name instead of single Counter pass",
"""def max_aggregate(stdata):
    names = []
    for name, _ in stdata:
        if name not in names:
            names.append(name)
    max_name = None
    max_total = None
    for name in names:
        total = 0
        for n2, val in stdata:
            if n2 == name:
                total += val
        if max_total is None or total > max_total:
            max_total = total
            max_name = name
    return (max_name, max_total)
"""),

# ─── 冗余代码：CWE-561 / CWE-1041 ────────────
("11", "CWE-1041: Three separate linear scans instead of single pass",
"""def remove_Occ(s, ch):
    if ch not in s:
        return s
    first_idx = -1
    for i in range(len(s)):
        if s[i] == ch:
            first_idx = i
            break
    last_idx = -1
    for i in range(len(s)):
        if s[i] == ch:
            last_idx = i
    result = ""
    for i in range(len(s)):
        if i == first_idx or i == last_idx:
            continue
        result += s[i]
    return result
"""),

("63", "CWE-1041: Builds intermediate list for diffs then scans again instead of single pass",
"""def max_difference(test_list):
    diffs = []
    for pair in test_list:
        a, b = pair[0], pair[1]
        if a > b:
            diffs.append(a - b)
        else:
            diffs.append(b - a)
    max_diff = 0
    for d in diffs:
        if d > max_diff:
            max_diff = d
    return max_diff
"""),

("66", "CWE-1041: Counts all three categories; only positive count needed — dead counters",
"""def pos_count(list1):
    count_positive = 0
    count_zero = 0
    count_negative = 0
    for num in list1:
        if num > 0:
            count_positive += 1
        elif num == 0:
            count_zero += 1
        else:
            count_negative += 1
    unused_total = count_positive + count_zero + count_negative
    return count_positive
"""),

("12", "CWE-1041: Recomputes row sum on every comparison instead of pre-computing; O(n^2*k) work",
"""def sort_matrix(M):
    result = [list(row) for row in M]
    # Pre-compute sums (but then ignores them and recomputes inline — dead work)
    _unused_sums = [sum(row) for row in result]
    for i in range(len(result)):
        for j in range(len(result) - i - 1):
            sum_j = 0
            for elem in result[j]:
                sum_j += elem
            sum_j1 = 0
            for elem in result[j + 1]:
                sum_j1 += elem
            if sum_j > sum_j1:
                result[j], result[j + 1] = result[j + 1], result[j]
    return result
"""),

("71", "CWE-1041: Uses temp variable swap + redundant sorted-flag check",
"""def comb_sort(alist):
    gap = len(alist)
    shrink = 1.3
    sorted_flag = False
    while not sorted_flag:
        gap = int(gap / shrink)
        if gap <= 1:
            gap = 1
            sorted_flag = True
        swapped = False
        for i in range(len(alist) - gap):
            if alist[i] > alist[i + gap]:
                temp = alist[i]
                alist[i] = alist[i + gap]
                alist[i + gap] = temp
                swapped = True
                sorted_flag = False
        if not swapped and gap == 1:
            sorted_flag = True
    return alist
"""),

# ─── 魔法数字：CWE-1052 ──────────────────────
("93", "CWE-1052: Hardcoded magic-number base cases instead of general loop",
"""def power(a, b):
    if b == 0:
        return 1
    if b == 1:
        return a
    if b == 2:
        return a * a
    if b == 3:
        return a * a * a
    if a == 0:
        return 0
    if a == 1:
        return 1
    result = 1
    for _ in range(b):
        result *= a
    return result
"""),

("246", "CWE-1052: Hardcoded magic convergence tolerance and iteration cap",
"""def babylonian_squareroot(number):
    MAX_ITER = 10000
    TOLERANCE = 0.0000001
    if number < 0:
        return -1
    if number == 0:
        return 0
    x = number / 2.0
    for _ in range(MAX_ITER):
        x_new = (x + number / x) / 2.0
        if abs(x_new - x) < TOLERANCE:
            break
        x = x_new
    return x
"""),

# ─── 缺少边界保护：CWE-476 / CWE-369 ─────────
("62", "CWE-476: No empty-list guard; will raise IndexError on empty input",
"""def smallest_num(s):
    current_min = s[0]
    for i in range(len(s)):
        if s[i] < current_min:
            current_min = s[i]
    return current_min
"""),

("82", "CWE-1052 + CWE-476: Uses truncated magic PI; no guard for negative radius",
"""def volume_sphere(r):
    pi_value = 3.14159
    volume = 4 * (1 / 3) * pi_value * r * r * r
    return round(volume, 2)
"""),

("137", "CWE-369: Division by non_zero_count with no guard — crashes if all elements are 0",
"""def zero_count(l):
    zero_cnt = 0
    non_zero_cnt = 0
    for item in l:
        if item == 0:
            zero_cnt += 1
        else:
            non_zero_cnt += 1
    return zero_cnt / non_zero_cnt
"""),

("248", "CWE-476: No guard for n <= 0; uses while loop instead of sum comprehension",
"""def harmonic_sum(n):
    total = 0
    current = 1
    while current <= n:
        total = total + 1.0 / current
        current = current + 1
    return total
"""),

]


# ──────────────────────────────────────────────
# 1. 验证 seed 函数通过对应测试
# ──────────────────────────────────────────────

def _validate_seed(task_id: str, seed_code: str, tasks_by_id: dict) -> tuple[bool, str]:
    """执行 seed_code + test_cases，返回 (passed, error_msg)。"""
    if task_id not in tasks_by_id:
        return False, f"task {task_id} not found"
    task = tasks_by_id[task_id]
    full_code = seed_code + "\n\n" + task.test_cases
    ns: dict = {}
    try:
        exec(compile(full_code, "<seed>", "exec"), ns)
        # 找到 test_ 函数并运行
        for name, obj in ns.items():
            if name.startswith("test_") and callable(obj):
                obj()
        return True, ""
    except Exception as e:
        return False, str(e)


# ──────────────────────────────────────────────
# 2. 生成 quality_subset_v1.json
# ──────────────────────────────────────────────

def _build_quality_items(
    seed_specs: list[tuple[str, str, str]],
    tasks_by_id: dict,
) -> list[dict[str, Any]]:
    items = []
    ok_count = 0
    fail_count = 0
    for task_id, issue, seed_code in seed_specs:
        passed, err = _validate_seed(task_id, seed_code, tasks_by_id)
        status = "OK" if passed else "FAIL"
        if passed:
            ok_count += 1
        else:
            fail_count += 1
            print(f"  [FAIL] task {task_id}: {err}", file=sys.stderr)
        print(f"  [{status}] task {task_id}: {issue[:60]}".encode("ascii", "replace").decode("ascii"))
        items.append(
            {
                "dataset": "mbpp",
                "task_id": task_id,
                "tags": ["quality", "seed_provided"],
                "seed_code": seed_code,
                "metadata": {
                    "quality_issue": issue,
                    "seed_validated": passed,
                    "source": "cogmas-tdd-generated",
                },
            }
        )
    print(f"\n  quality subset: {ok_count} passed, {fail_count} failed out of {len(seed_specs)}")
    return items


# ──────────────────────────────────────────────
# 3. 生成 baseline_extended_v1.json
# ──────────────────────────────────────────────

_EXTENDED_MBPP_IDS = [
    "4", "7", "8", "16",
    "62", "65", "68", "71",
    "82", "88", "99", "102",
    "105", "118", "130", "161",
    "222", "230", "246", "248",
]

_EXTENDED_HE_IDS = [
    "HumanEval/2", "HumanEval/3", "HumanEval/5",
    "HumanEval/13", "HumanEval/16",
]

_ALREADY_IN_BASELINE = {"2", "3", "HumanEval/0", "HumanEval/1"}


def _build_extended_items() -> list[dict[str, Any]]:
    items = []
    for tid in _EXTENDED_MBPP_IDS:
        if tid in _ALREADY_IN_BASELINE:
            continue
        items.append({"dataset": "mbpp", "task_id": tid, "tags": ["extended_baseline", "mbpp"]})
    for tid in _EXTENDED_HE_IDS:
        if tid in _ALREADY_IN_BASELINE:
            continue
        items.append({"dataset": "humaneval", "task_id": tid, "tags": ["extended_baseline", "humaneval"]})
    return items


# ──────────────────────────────────────────────
# 4. 主流程
# ──────────────────────────────────────────────

def main() -> None:
    from benchmark_inputs import load_benchmark_tasks

    print("Loading MBPP tasks for validation …")
    mbpp_tasks = load_benchmark_tasks("mbpp", limit=500)
    tasks_by_id = {t.task_id: t for t in mbpp_tasks}

    manifest_dir = Path(__file__).resolve().parent / "benchmark_manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)

    # ── quality subset ──
    print("\n=== Validating quality subset seed implementations ===")
    quality_items = _build_quality_items(SEED_SPECS, tasks_by_id)
    quality_manifest = {
        "name": "quality_subset_v1",
        "description": (
            "30-task MBPP quality-focused subset. "
            "Each task has a low-quality but functionally correct seed implementation "
            "containing at least one CISQ-detectable quality issue."
        ),
        "metadata": {
            "split": "quality_subset",
            "version": "v1",
            "owner": "cogmas-tdd",
            "seed_source": "manifest",
            "note": "Use --seed-source manifest when running this manifest.",
        },
        "items": quality_items,
    }
    quality_path = manifest_dir / "quality_subset_v1.json"
    quality_path.write_text(
        json.dumps(quality_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n[OK] Written: {quality_path}")

    # ── extended baseline ──
    print("\n=== Building extended baseline manifest ===")
    extended_items = _build_extended_items()
    extended_manifest = {
        "name": "baseline_extended_v1",
        "description": (
            "25-task extended baseline subset mixing 20 MBPP + 5 HumanEval tasks. "
            "Designed for statistically meaningful Experiment 1 results."
        ),
        "metadata": {
            "split": "extended_baseline",
            "version": "v1",
            "owner": "cogmas-tdd",
            "note": "Extends shared_baseline_subset_v1. Excludes tasks already in that manifest.",
        },
        "items": extended_items,
    }
    extended_path = manifest_dir / "baseline_extended_v1.json"
    extended_path.write_text(
        json.dumps(extended_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[OK] Written: {extended_path}")
    print(f"  Tasks: {len(extended_items)} ({sum(1 for i in extended_items if i['dataset']=='mbpp')} MBPP + "
          f"{sum(1 for i in extended_items if i['dataset']=='humaneval')} HumanEval)")


if __name__ == "__main__":
    main()
