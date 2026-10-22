import json
import os
from pathlib import Path

from openai import OpenAI

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"
# Small local models write long answers; a 1000-token cap cut them off mid-sentence.
DEFAULT_MAX_TOKENS = {"planner": 2000, "worker": 2500, "reviewer": 2500}


def call_model(role: str, context: dict) -> dict:
    model = os.getenv(
        "OPENAI_REVIEW_MODEL" if role == "reviewer" else "OPENAI_MODEL",
        os.getenv(
            "OLLAMA_REVIEW_MODEL" if role == "reviewer" else "OLLAMA_MODEL",
            "llama3.1:8b",
        ),
    )
    with OpenAI(
        base_url=os.getenv("OPENAI_BASE_URL", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")),
        api_key=os.getenv("OPENAI_API_KEY", "ollama"),
        timeout=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "90")),
        max_retries=0,
    ) as client:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": (PROMPTS / f"{role}_prompt.txt").read_text(encoding="utf-8")},
                {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
            ],
            temperature=0.1,
            max_tokens=int(os.getenv(f"{role.upper()}_MAX_TOKENS", DEFAULT_MAX_TOKENS.get(role, 1000))),
        )
    content = response.choices[0].message.content
    if not content or not content.strip():
        raise ValueError(f"{role} model returned empty output")
    if response.choices[0].finish_reason == "length":
        raise ValueError(f"{role} model output was truncated; increase its token limit")
    return {"status": "success", "agent": f"{role}_agent", "model": model, role: content.strip()}
