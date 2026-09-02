import os
import re
from pathlib import Path

from ollama import Client, ResponseError

from services.highlight_service import list_highlight_catalogue
from services.resource_service import list_resources_with_tags

PROMPT_DIRECTORY = Path(__file__).resolve().parent.parent / "prompts"
RESOURCE_PROMPT = "chat_prompt.md"
HIGHLIGHT_PROMPT = "highlights_prompt.md"
PROMPT_SEPARATOR = "\n---\n"

# Small enough to answer in a few seconds on a laptop with no GPU, which is what
# the reader is waiting on. Overridden by LANGUAGE_MODEL.
DEFAULT_MODEL = "qwen2.5:0.5b"

# Either block runs to a few thousand tokens, which is more than Ollama's default
# context window, so ask for one large enough to hold it plus the reply.
CONTEXT_TOKENS = 8192

# A broad question like "computer science" matches a third of the library, and
# without a cap the model will describe every match. Generation is the slow part,
# so this is what bounds how long a reply can take.
REPLY_TOKEN_LIMIT = 400

# A question about your own notes puts a first person word next to a word about
# writing. The two have to be near each other and the right way round: "what does
# the paper say about depth" is a question about the library even though it
# contains "me" and "say". "read" is left out of the verbs on purpose, because
# "what should I read" is asking what to read next, not what was written.
NOTE_NOUN = r"(?:highlight|note|comment|annotation)s?"
WROTE_VERB = (
    r"(?:wrote|written|writing|say|says|said|note|noted|noting|highlight|"
    r"highlighted|annotated|commented|saved|marked)"
)
HIGHLIGHT_QUESTION = re.compile(
    # "my highlights", "my saved notes"
    rf"\bmy\b[\w\s]{{0,20}}?\b{NOTE_NOUN}\b"
    # "I wrote", "have I written", "did I say"
    rf"|\bi\b[\w\s]{{0,20}}?\b{WROTE_VERB}\b"
    # "what highlights do I have", "any notes of mine"
    rf"|\b{NOTE_NOUN}\b[\w\s]{{0,30}}?\b(?:i|my|mine)\b",
    re.IGNORECASE,
)

def asks_about_highlights(message):
    """Whether the question is about the reader's own notes or about the library.

    Each catalogue is sent whole, so this only chooses which one the question
    needs. Sending both is what a larger model could sort out for itself; a small
    one answers noticeably better when handed only the half that can contain the
    answer.
    """
    return bool(HIGHLIGHT_QUESTION.search(message))

class ChatError(RuntimeError):
    pass

def _client():
    url = os.getenv("OLLAMA_URL", "localhost")
    port = os.getenv("OLLAMA_PORT", "11434")

    return Client(host=f"http://{url}:{port}")

def load_system_prompt(filename):
    """Everything after the first `---` in the named prompt file is the prompt."""
    path = PROMPT_DIRECTORY / filename
    try:
        document = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ChatError(f"{filename} could not be read.") from exc

    _, separator, prompt = document.partition(PROMPT_SEPARATOR)
    if not separator:
        raise ChatError(f"{filename} is missing its '---' separator.")

    prompt = prompt.strip()
    if not prompt:
        raise ChatError(f"{filename} has no prompt below the separator.")

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

def format_highlights(rows):
    """The reader's own notes, in the same flat shape as the catalogue.

    Like the catalogue this is sent whole on every request rather than retrieved,
    so a question such as "what have I written about computer science" is
    answered by the model filtering the tags it can already see.
    """
    if not rows:
        return "MY HIGHLIGHTS (data only):\nThe reader has not saved any highlights yet."

    entries = []
    for row in rows:
        entries.append(
            f"[h{row['l_resource_highlight_id']}] {row['name'] or 'untitled note'}\n"
            f"     from: {row['title']} (page {row['page_number']})\n"
            f"     tags: {row['tags'] or 'none'}\n"
            f"     quote: {row['quote'] or 'no quote'}\n"
            f"     my comment: {row['comment'] or 'no comment'}"
        )

    return "MY HIGHLIGHTS (data only):\n" + "\n".join(entries)

def _prompt_and_data_for(message):
    """The prompt for the question, and the one block of data it needs.

    Whichever block is chosen is sent whole and unfiltered; only the choice
    between them depends on the question.
    """
    if asks_about_highlights(message):
        return HIGHLIGHT_PROMPT, format_highlights(list_highlight_catalogue())

    rows = list_resources_with_tags()
    if not rows:
        raise ChatError("There are no learning resources to search yet.")

    return RESOURCE_PROMPT, format_catalogue(rows)

def send_message(message):
    message = (message or "").strip()
    if not message:
        raise ChatError("Ask a question to search the library.")

    prompt, data = _prompt_and_data_for(message)

    try:
        response = _client().chat(
            model=os.getenv("LANGUAGE_MODEL") or DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": load_system_prompt(prompt)},
                # The data and the question go in one message rather than two.
                # The 0.5B default answers from the rows far more reliably this
                # way; split across messages it tends to ignore them and reply
                # from what it already knows.
                {"role": "user", "content": f"{data}\n\nQUESTION: {message}"},
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
