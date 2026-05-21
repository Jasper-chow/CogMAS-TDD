"""Compare Qwen2.5-7B-Instruct vs Qwen2.5-Coder-7B-Instruct for code gen + repair."""
from dotenv import load_dotenv
load_dotenv()
import os, json
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["SILICONFLOW_API_KEY"],
    base_url=os.environ.get("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1"),
)

gen_prompt = """You are an expert Python programmer.

Task:
Write a function to find the n largest integers from a given list of numbers, returned in descending order.
The function MUST be named `heap_queue_largest`.

Tests:
```python
def test_mbpp_task():
    assert heap_queue_largest([25, 35, 22, 85, 14, 65, 75, 22, 58], 3) == [85, 75, 65]
    assert heap_queue_largest([25, 35, 22, 85, 14, 65, 75, 22, 58], 2) == [85, 75]
```

Return strict JSON with:
- code: the complete Python implementation
- explanation: brief description of your approach"""

repair_prompt = """You are an expert Python programmer. Fix the following code so it passes the tests.

Task:
Write a function to find the n largest integers from a given list of numbers, returned in descending order.
The function MUST be named `heap_queue_largest`.

Error from last run:
NameError: name 'numslist' is not defined

Current code:
```python
import heapq

def heap_queue_largest(nums_list, n):
    return heapq.nlargest(numslist, n)
```

Tests:
```python
def test_mbpp_task():
    assert heap_queue_largest([25, 35, 22, 85, 14, 65, 75, 22, 58], 3) == [85, 75, 65]
```

Return strict JSON with:
- code: the complete corrected Python implementation
- explanation: brief description of what you fixed"""

SYS = ("You are a structured output assistant. "
       "Respond with ONLY a valid JSON object — no markdown, no code fences, no extra text. "
       "Start your response with { and end with }. "
       "Escape newlines in string values as \\n.")

for model in ["Qwen/Qwen2.5-7B-Instruct", "Qwen/Qwen2.5-Coder-7B-Instruct"]:
    print(f"\n{'='*60}")
    print(f"Model: {model}")
    for label, prompt in [("GENERATION", gen_prompt), ("REPAIR", repair_prompt)]:
        print(f"\n--- {label} ---")
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYS},
                    {"role": "user", "content": f"Task:\n{prompt}\n\nRespond with JSON: {{\"code\": \"...\", \"explanation\": \"...\"}}"},
                ],
                temperature=0,
                max_tokens=512,
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content or ""
            print(f"Response ({len(content)} chars):")
            # Show first 400 chars only
            print(content[:400])
            try:
                parsed = json.loads(content.rstrip() + ("}" if not content.rstrip().endswith("}") else ""))
                code = parsed.get("code", "")
                print(f"\nExtracted code ({len(code)} chars):")
                print(code[:300])
            except Exception as e:
                print(f"Parse error: {e}")
        except Exception as e:
            print(f"API error: {e}")
