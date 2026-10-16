import json
import os
from pathlib import Path

from openai import OpenAI

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"


def call_model(role: str, context: dict) -> dict:
    model = os.getenv(
        "OLLAMA_REVIEW_MODEL" if role == "reviewer" else "OLLAMA_MODEL",
        "llama3.1:8b" if role == "reviewer" else "qwen2.5:0.5b",
    )
    with OpenAI(
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        api_key="ollama",
        timeout=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "45")),
        max_retries=0,
    ) as client:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": (PROMPTS / f"{role}_prompt.txt").read_text(encoding="utf-8")},
                {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
            ],
            temperature=0.1,
            max_tokens=int(os.getenv(f"{role.upper()}_MAX_TOKENS", "1000")),
        )
    content = response.choices[0].message.content
    if not content or not content.strip():
        raise ValueError(f"{role} model returned empty output")
    if response.choices[0].finish_reason == "length":
        raise ValueError(f"{role} model output was truncated; increase its token limit")
    return {"status": "success", "agent": f"{role}_agent", "model": model, role: content.strip()}
