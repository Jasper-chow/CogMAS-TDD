"""Single-task smoke test: MBPP task 4 with 'ours' profile."""
import asyncio, json, sys
from dotenv import load_dotenv
load_dotenv()

from benchmark_inputs import load_mbpp_tasks
from main import run_experiment_once

async def main():
    tasks = load_mbpp_tasks(task_ids=["4"])
    t = tasks[0]
    print(f"[smoke] task={t.task_id} entry={t.entry_point}")
    print(f"[smoke] requirement: {t.requirement}")
    print(f"[smoke] test_cases:\n{t.test_cases}")
    print("[smoke] starting ours profile...")

    state, record = await run_experiment_once(
        profile="ours",
        requirement=t.requirement,
        task_id=t.task_id,
        dataset_name=t.dataset_name,
        entry_point=t.entry_point,
        test_cases=t.test_cases,
        equivalence_mode="weak",
        results_path="results/smoke_test.jsonl",
    )

    print("\n[smoke] ===== RESULT =====")
    print(f"  workflow_status : {state.get('workflow_status')}")
    print(f"  stop_reason     : {state.get('stop_reason')}")
    print(f"  test_passed     : {state.get('test_passed')}")
    print(f"  green_attempts  : {state.get('green_attempts')}")
    print(f"  has_l2_refactor : {state.get('has_l2_refactor')}")
    print(f"  has_l3_refactor : {state.get('has_l3_refactor')}")
    print(f"  final_verdict   : {state.get('final_verdict')}")
    print(f"  dynamic_verdict : {state.get('dynamic_verdict')}")
    print(f"  static_verdict  : {state.get('static_verdict')}")

    cr = state.get("code_review_report", {})
    if cr:
        print(f"\n[smoke] CR report:")
        print(f"  overall_score       : {cr.get('overall_score')}")
        print(f"  needs_refactoring   : {cr.get('needs_refactoring')}")
        print(f"  security score      : {cr.get('security', {}).get('score')}")
        print(f"  reliability score   : {cr.get('reliability', {}).get('score')}")
        print(f"  maintainability     : {cr.get('maintainability', {}).get('score')}")
        print(f"  performance         : {cr.get('performance_efficiency', {}).get('score')}")
        sec_findings = cr.get("security", {}).get("findings", [])
        rel_findings = cr.get("reliability", {}).get("findings", [])
        print(f"  security findings   : {sec_findings}")
        print(f"  reliability findings: {rel_findings}")

    print(f"\n[smoke] review_comments:")
    for c in state.get("review_comments", []):
        print(f"  {c}")

    code = state.get("code", "")
    l2 = state.get("l2_code", "")
    l3 = state.get("l3_code", "")
    print(f"\n[smoke] final code ({len(code)} chars):")
    print(code)
    if l2:
        print(f"\n[smoke] l2_code ({len(l2)} chars):")
        print(l2)
    if l3:
        print(f"\n[smoke] l3_code ({len(l3)} chars):")
        print(l3)

asyncio.run(main())
