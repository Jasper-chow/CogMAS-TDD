from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


# 显式保留一批对 HumanEval / MBPP 更常见的通用编程问题。
KEEP_IDS = {
    "22",
    "23",
    "36",
    "77",
    "78",
    "88",
    "99",
    "129",
    "134",
    "252",
    "259",
    "321",
    "477",
    "502",
    "606",
    "789",
    "798",
    "390",
    "459",
    "665",
    "672",
    "682",
    "369",
    "703",
    "248",
    "391",
    "392",
    "835",
    "1077",
    "407",
    "480",
    "561",
    "570",
    "571",
    "783",
    "1041",
    "1052",
    "1095",
    "1121",
    "404",
    "772",
    "775",
    "1050",
}


# 这些主题对 Python benchmark 的单函数任务通常噪声较大。
DROP_KEYWORDS = {
    "web page",
    "html",
    "dom",
    "xss",
    "sql",
    "hibernate",
    "ldap",
    "xpath",
    "xquery",
    "xml",
    "dtd",
    "database",
    "query",
    "join",
    "materialized view",
    "connection pool",
    "data table",
    "dao",
    "data access object",
    "data manager",
    "remote resource",
    "network call",
    "ip address",
    "url",
    "authentication",
    "authorization",
    "upload",
    "mime",
    "magic numbers",
    "thread",
    "multithread",
    "lock",
    "deadlock",
    "synchron",
    "singleton",
    "object monitor",
    "shared mutable state",
    "pointer",
    "buffer",
    "memory",
    "sign extension",
    "signed",
    "unsigned",
    "dynamic_cast",
    "instanceof",
    "java",
    "c++",
    "destructor",
    "inheritance",
    "getter/setter",
    "single responsibility principle",
    "dependency injection",
    "layer",
    "classpath",
    "chmod",
    "cryptographic",
    "kms",
    "hsm",
    "vault",
}


# 某些虽然包含 file/resource 等字样，但仍可能对 benchmark 中的 Python 代码有用。
ALLOW_KEYWORDS = {
    "path traversal",
    "pathname",
    "file descriptor",
    "resource shutdown",
    "release of resource",
    "loop condition",
    "array index",
    "hard-coded",
    "operator",
    "dead code",
    "always false",
    "always true",
    "cyclomatic complexity",
    "incorrect calculation",
    "divide by zero",
    "exception",
    "infinite loop",
}


def build_text(item: dict[str, str]) -> str:
    return " ".join(
        [
            str(item.get("Characteristic", "")),
            str(item.get("Description", "")),
            str(item.get("Refactor_Advice", "")),
        ]
    ).lower()


def should_keep(item: dict[str, str]) -> tuple[bool, str]:
    cwe_id = str(item.get("CWE_ID", "")).strip()
    text = build_text(item)

    if cwe_id in KEEP_IDS:
        return True, "whitelist"

    if any(keyword in text for keyword in ALLOW_KEYWORDS):
        if not any(keyword in text for keyword in DROP_KEYWORDS):
            return True, "generic-keyword"

    if any(keyword in text for keyword in DROP_KEYWORDS):
        return False, "domain-noise"

    characteristic = str(item.get("Characteristic", "")).strip().lower()

    # 对剩余规则做保守保留：仅保留偏通用的可靠性/可维护性问题。
    generic_terms = (
        "logic",
        "condition",
        "calculation",
        "exception",
        "resource",
        "literal",
        "complexity",
        "loop",
        "error",
        "cleanup",
    )
    if characteristic in {"maintainability", "reliability"} and any(term in text for term in generic_terms):
        return True, "generic-fallback"

    return False, "filtered"


def deduplicate_rules(items: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for item in items:
        cwe_id = str(item.get("CWE_ID", "")).strip()
        if not cwe_id or cwe_id in seen_ids:
            continue
        seen_ids.add(cwe_id)
        deduped.append(item)
    return deduped


def generate_subset(source_path: Path) -> list[dict[str, str]]:
    raw_items = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(raw_items, list):
        raise ValueError("CISQ mapping must be a JSON array.")

    unique_items = deduplicate_rules(raw_items)
    subset: list[dict[str, str]] = []

    for item in unique_items:
        keep, _reason = should_keep(item)
        if keep:
            subset.append(item)

    return subset


def print_summary(items: list[dict[str, str]]) -> None:
    counts = Counter(str(item.get("Characteristic", "")).strip() for item in items)
    print(f"selected rules: {len(items)}")
    for name in sorted(counts):
        print(f"{name}: {counts[name]}")


def main() -> None:
    project_root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Generate Python benchmark CISQ subset.")
    parser.add_argument(
        "--source",
        type=Path,
        default=project_root / "knowledge" / "CISQ_mapping.json",
        help="Source CISQ mapping JSON file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=project_root / "knowledge" / "CISQ_mapping_python_benchmark_subset.json",
        help="Output subset JSON file.",
    )
    args = parser.parse_args()

    subset = generate_subset(args.source)
    args.output.write_text(json.dumps(subset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print_summary(subset)
    print(f"written to: {args.output}")


if __name__ == "__main__":
    main()
