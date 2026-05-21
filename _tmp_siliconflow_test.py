from dotenv import load_dotenv
load_dotenv()

from utils.helpers import resolve_llm_settings, generate_with_outlines
from pydantic import BaseModel


class SimpleOutput(BaseModel):
    answer: str
    confidence: float


settings = resolve_llm_settings()
print("Provider:", settings["provider"])
print("Model:", settings["model_name"])
print("Base URL:", settings["base_url"])
print()

data, used_llm, note = generate_with_outlines(
    prompt='Answer this simple math question. Return valid JSON: {"answer": "4", "confidence": 0.95}',
    output_model=SimpleOutput,
    fallback_data={"answer": "fallback", "confidence": 0},
)
print("Used LLM:", used_llm)
print("Note:", note[:200])
print("Result:", data)
