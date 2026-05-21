from __future__ import annotations

"""
LDB-style prompt protocol helpers.

These helpers intentionally mirror the protocol shape used by LLMDebugger:
- task / code / failed assertion
- block-by-block execution trace
- [debug] ... [/debug] feedback history
- a final repair turn such as "Please fix the Python code."
"""

from typing import Any


LDB_TEXT2CODE_FEWSHOT = """# Write Python function to complete the task and pass the assertion tests.
### Task Start ###
# These are the assertions for your function:
assert find_char_long('Please move back to stream') == ['Please', 'move', 'back', 'stream']

def find_char_long(text):
    \"\"\" Write a function to find all words which are at least 4 characters long in a string by using regex. \"\"\"
    if text == "":
        return []
    pat = r"\\b\\w{4}\\b"
    res = re.findall(pat, text)
    return res

Feedback: With the above function, the assertion is `find_char_long('Please move back to stream') == ['Please', 'move', 'back', 'stream']` but the real execution output is `['move', 'back']`.
Debug the program trace block by block until find the incorrect block. Every block should have different feedbacks:
[BLOCK-1]
    # text="Please move back to stream"
    if text == "":
[BLOCK-2]
    # text="Please move back to stream"
    pat = r"\\b\\w{4}\\b"
    res = re.findall(pat, text)
    # text="Please move back to stream" pat="\\b\\w{4}\\b"  res=['move', 'back']
[debug]
[BLOCK-1]
Feedback: CORRECT. This block is correct. It checks if the input text is empty. If the input text is empty, it returns an empty list without doing regex matching.
[BLOCK-2]
Feedback: INCORRECT. This block defines a regular expression pattern `pat` with value r"\\b\\w{4}\\b". However, it only matches words that are exactly 4 characters long. The task requires words that are at least 4 characters long. Change the pattern to `r"\\b\\w{4,}\\b"`.
[/debug]
Please fix the Python code.
[python]
import re
def find_char_long(text):
    \"\"\" Write a function to find all words which are at least 4 characters long in a string by using regex. \"\"\"
    if text == "":
        return []
    pat = r"\\b\\w{4,}\\b"
    res = re.findall(pat, text)
    return res
[/python]
### Task End ###
""".strip()


def _render_blocks(trace_blocks: list[dict[str, Any]]) -> str:
    if not trace_blocks:
        return ""
    return "\n".join(block["rendered"] for block in trace_blocks)


def build_ldb_debug_protocol_prompt(
    *,
    failed_test: str,
    real_output: str,
    code: str,
    trace_blocks: list[dict[str, Any]],
) -> str:
    rendered_blocks = _render_blocks(trace_blocks)
    return f"""
You are an expert programming assistant following the LLMDebugger block-debugging protocol.

Follow the same style as the few-shot example:
- inspect the failed assertion and the real output
- read the execution trace block by block
- produce feedback FOR EACH BLOCK
- use the exact block names already provided
- write `Feedback: CORRECT.` or `Feedback: INCORRECT.` first
- when a block is incorrect, explain what is wrong and how to fix it

Your final output must be strict JSON matching the provided schema, but the content of each explanation should mirror the LDB few-shot style.

Few-shot protocol example:
{LDB_TEXT2CODE_FEWSHOT}

Now debug the current Python code.

Current code:
```python
{code or "# empty"}
```

Feedback: With the above function, the assertion is `{failed_test or "unknown assertion"}` but the real execution output is `{real_output or "unknown output"}`.
Debug the program trace block by block until find the incorrect block. Every block should have different feedbacks:
{rendered_blocks or "[BLOCK-0]\n# no trace blocks available"}
""".strip()


def build_ldb_debug_history(
    *,
    failed_test: str,
    real_output: str,
    trace_blocks: list[dict[str, Any]],
    block_feedback_text: str,
) -> str:
    rendered_blocks = _render_blocks(trace_blocks)
    return (
        "### Task Start ###\n"
        "# These are the assertions for your function:\n"
        f"{failed_test or 'assert unknown()'}\n\n"
        "Feedback: With the above function, the assertion is "
        f"`{failed_test or 'assert unknown()'}` but the real execution output is "
        f"`{real_output or 'unknown output'}`.\n"
        "Debug the program trace block by block until find the incorrect block. "
        "Every block should have different feedbacks:\n"
        f"{rendered_blocks or '[BLOCK-0]\\n# no trace blocks available'}\n"
        "[debug]\n"
        f"{block_feedback_text or '[BLOCK-0]\\nFeedback: INCORRECT. No detailed block feedback is available.'}\n"
        "[/debug]"
    )


def build_ldb_repair_prompt(
    *,
    requirement: str,
    code: str,
    test_cases: str,
    debug_history: str,
    suspicious_block: str,
) -> str:
    return f"""
You are an expert programming assistant.
Use the LLMDebugger repair protocol shown in the few-shot example.

Few-shot protocol example:
{LDB_TEXT2CODE_FEWSHOT}

Now fix the current task.

Task requirement / function prompt:
{requirement or "No explicit requirement provided."}

Current Python code:
```python
{code or "# empty"}
```

Available tests:
```python
{test_cases or "# no tests"}
```

LDB debug history:
{debug_history}

Most suspicious block: {suspicious_block or "unknown"}

Please fix the Python code.

Return strict JSON matching the schema:
- code: the full repaired Python code
- explanation: a concise repair summary grounded in the incorrect block feedback
""".strip()


def build_cumulative_ldb_history(
    debug_histories: list[str],
    *,
    max_histories: int = 3,
) -> str:
    histories = [item.strip() for item in debug_histories if item and item.strip()]
    if not histories:
        return ""
    selected = histories[-max_histories:]
    rendered = []
    for index, history in enumerate(selected, start=1):
        rendered.append(f"## Debug Round {index}\n{history}")
    return "\n\n".join(rendered)
