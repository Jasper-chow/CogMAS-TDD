"""Debug: raw API response for a simple code gen request."""
from dotenv import load_dotenv
load_dotenv()
import os, json
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["SILICONFLOW_API_KEY"],
    base_url=os.environ.get("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1"),
)
model = os.environ.get("SILICONFLOW_MODEL", "Qwen/Qwen2.5-7B-Instruct")
print(f"Model: {model}")

prompt = """You are an expert Python programmer.

Task:
Write a function to find the n largest integers from a given list of numbers, returned in descending order.
The function MUST be named `heap_queue_largest`.

Tests:
```python
def test_mbpp_task():
    assert heap_queue_largest( [25, 35, 22, 85, 14, 65, 75, 22, 58],3)==[85, 75, 65]
    assert heap_queue_largest( [25, 35, 22, 85, 14, 65, 75, 22, 58],2)==[85, 75]
```

Write a complete Python function that passes all tests.
Return strict JSON with:
- code: the complete Python implementation
- explanation: brief description of your approach"""

response = client.chat.completions.create(
    model=model,
    messages=[
        {"role": "system", "content": "You are a structured output assistant. Respond with ONLY a valid JSON object — no markdown, no code fences, no extra text. Start your response with { and end with }. Escape newlines in string values as \\n."},
        {"role": "user", "content": f"Task:\n{prompt}\n\nRespond with ONLY a JSON object matching this template (fill in actual values, keep the same keys):\n{{\"code\": \"...\", \"explanation\": \"...\"}}"},
    ],
    temperature=0,
    response_format={"type": "json_object"},
)

content = response.choices[0].message.content
print(f"\nRaw response ({len(content)} chars):")
print(content)
print("\n--- Parsed ---")
try:
    parsed = json.loads(content)
    code = parsed.get("code", "")
    print(f"code ({len(code)} chars):")
    print(code)
except Exception as e:
    print(f"JSON parse error: {e}")
