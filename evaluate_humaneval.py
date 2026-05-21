from __future__ import annotations

import argparse
import json

from utils.humaneval_official import evaluate_humaneval_samples


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run official-style HumanEval evaluation")
    parser.add_argument("--sample-file", required=True)
    parser.add_argument("--problem-file", default="")
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--k", nargs="*", type=int, default=[1])
    parser.add_argument("--output-path", default="")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = evaluate_humaneval_samples(
        args.sample_file,
        problem_file=args.problem_file or None,
        k_values=args.k,
        timeout=args.timeout,
        n_workers=args.workers,
    )
    if args.output_path:
        with open(args.output_path, "w", encoding="utf-8") as file:
            json.dump(
                {
                    **result,
                    "detailed_result_count": len(result.get("detailed_results", [])),
                },
                file,
                ensure_ascii=False,
                indent=2,
            )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
