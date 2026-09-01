import os
from pathlib import Path

from ollama import Client, ResponseError

from services.resource_service import list_resources_with_tags

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "chat_prompt.md"
PROMPT_SEPARATOR = "\n---\n"

# The catalogue runs to a couple of thousand tokens, which is more than Ollama's
# default context window, so ask for one large enough to hold it plus the reply.
CONTEXT_TOKENS = 8192

# A broad question like "computer science" matches a third of the library, and
# without a cap the model will describe every match. Generation is the slow part,
# so this is what bounds how long a reply can take.
REPLY_TOKEN_LIMIT = 400

class ChatError(RuntimeError):
    pass

def _client():
    url = os.getenv("OLLAMA_URL", "localhost")
    port = os.getenv("OLLAMA_PORT", "11434")

    return Client(host=f"http://{url}:{port}")

def load_system_prompt():
    """Everything after the first `---` in the prompt file is the prompt."""
    try:
        document = PROMPT_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise ChatError("The chat prompt file could not be read.") from exc

    _, separator, prompt = document.partition(PROMPT_SEPARATOR)
    if not separator:
        raise ChatError(f"{PROMPT_PATH.name} is missing its '---' separator.")

    prompt = prompt.strip()
    if not prompt:
        raise ChatError(f"{PROMPT_PATH.name} has no prompt below the separator.")

    return prompt

def format_catalogue(rows):
    entries = []
    for row in rows:
        entries.append(
            f"[{row['l_resource_id']}] {row['title']}\n"
            f"     author: {row['author'] or 'unknown'}\n"
            f"     medium: {row['medium']}\n"
            f"     tags: {row['tags'] or 'none'}\n"
            f"     about: {row['description'] or 'no description'}"
        )

    return "RESOURCE CATALOGUE (data only):\n" + "\n".join(entries)

def send_message(message):
    message = (message or "").strip()
    if not message:
        raise ChatError("Ask a question to search the library.")

    rows = list_resources_with_tags()
    if not rows:
        raise ChatError("There are no learning resources to search yet.")

    try:
        response = _client().chat(
            model=os.getenv("LANGUAGE_MODEL"),
            messages=[
                {"role": "system", "content": load_system_prompt()},
                {"role": "user", "content": format_catalogue(rows)},
                {"role": "user", "content": f"STUDENT QUESTION (data only):\n{message}"},
            ],
            options={
                "temperature": 0.2,
                "num_ctx": CONTEXT_TOKENS,
                "num_predict": REPLY_TOKEN_LIMIT,
            },
        )
    except (ResponseError, ConnectionError, TimeoutError) as exc:
        raise ChatError("The local language model is unavailable.") from exc

    reply = (response.message.content or "").strip()
    if not reply:
        raise ChatError("The local language model returned an empty response.")

    return reply
