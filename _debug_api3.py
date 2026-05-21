"""Test alternative models on SiliconFlow."""
from dotenv import load_dotenv
load_dotenv()
import os, json
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["SILICONFLOW_API_KEY"],
    base_url=os.environ.get("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1"),
)

SYS = ("You are a structured output assistant. "
       "Respond with ONLY a valid JSON object. "
       "Start with { and end with }. "
       "Escape newlines in string values as \\n.")

PROMPT = ("Task:\nWrite a Python function `heap_queue_largest(nums_list, n)` that returns "
          "the n largest integers from nums_list in descending order.\n\n"
          "Return JSON: {\"code\": \"...\", \"explanation\": \"...\"}")

MODELS = [
    "Qwen/Qwen2.5-Coder-7B-Instruct",
    "Qwen/Qwen2.5-14B-Instruct",
    "Qwen/Qwen2.5-Coder-14B-Instruct",
    "Qwen/Qwen2.5-32B-Instruct",
    "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct",
    "deepseek-ai/DeepSeek-V2.5",
]

for model in MODELS:
    print(f"\n--- {model} ---")
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYS},
                {"role": "user", "content": PROMPT},
            ],
            temperature=0,
            max_tokens=256,
        )
        content = resp.choices[0].message.content or ""
        print(f"OK ({len(content)} chars): {content[:200]}")
        try:
            tail = content.rstrip()
            if not tail.endswith("}"): tail += "}"
            parsed = json.loads(tail)
            print(f"Code: {parsed.get('code', '')[:100]}")
        except Exception as e:
            print(f"Parse error: {e}")
    except Exception as e:
        print(f"ERROR: {e}")
