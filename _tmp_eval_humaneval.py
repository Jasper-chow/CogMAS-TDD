import json
from pathlib import Path
from utils.humaneval_official import evaluate_humaneval_samples

sample_file = Path(r'F:\LLM\LLM_learning\results\runs\humaneval\b0_direct_generation\20260518_165217__b0_direct_generation__humaneval__humaneval_smoke_v1__official_eval_smoke\humaneval_samples.jsonl')
result = evaluate_humaneval_samples(sample_file, k_values=[1], timeout=3.0, n_workers=1)
print(json.dumps(result, ensure_ascii=False, indent=2))
