import time, sys
t = time.time()
print("step1: importing", flush=True)
from evalplus.data.humaneval import get_human_eval_plus
print(f"step2: import done in {time.time()-t:.1f}s", flush=True)
t = time.time()
d = get_human_eval_plus()
print(f"step3: loaded {len(d)} tasks in {time.time()-t:.1f}s", flush=True)
