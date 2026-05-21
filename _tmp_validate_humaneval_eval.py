import json
from pathlib import Path
from benchmark_inputs import load_humaneval_tasks
from utils.humaneval_official import extract_humaneval_completion, write_humaneval_samples, evaluate_humaneval_samples

task = load_humaneval_tasks(limit=1)[0]
completion = extract_humaneval_completion(task.reference_code, prompt=task.requirement, entry_point=task.entry_point)
out_path = Path('_tmp_humaneval_samples.jsonl')
write_humaneval_samples([{'task_id': task.task_id, 'completion': completion}], out_path)
result = evaluate_humaneval_samples(out_path, k_values=[1], timeout=3.0, n_workers=1)
print(json.dumps({'task_id': task.task_id, 'pass_metrics': result['pass_metrics'], 'passed_count': result['passed_count'], 'task_count': result['task_count']}, ensure_ascii=False, indent=2))
out_path.unlink(missing_ok=True)
