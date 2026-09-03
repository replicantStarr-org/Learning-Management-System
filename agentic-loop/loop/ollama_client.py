"""The two model roles, and the prompt files behind them.

Both roles talk to the same local Ollama the rest of the application uses. They
differ only in which model answers and which prompt is loaded, so they share one
client. Every call is allowed to fail: a model being unavailable degrades the
report to its deterministic half rather than ending the run, because the
findings themselves are computed in Python and are the substance of the output.
"""

import os
from pathlib import Path

from ollama import Client, ResponseError

PROMPT_DIRECTORY = Path(__file__).resolve().parent.parent / "prompts"
PROMPT_SEPARATOR = "\n---\n"


class ModelError(RuntimeError):
    pass


def load_prompt(filename):
    """Everything after the first `---` in the named prompt file is the prompt.

    The same split the learning resource manager uses, so the notes above the
    separator can explain a prompt without being sent to the model.
    """
    path = PROMPT_DIRECTORY / filename
    try:
        document = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ModelError(f"{filename} could not be read.") from exc

    _, separator, prompt = document.partition(PROMPT_SEPARATOR)
    if not separator:
        raise ModelError(f"{filename} is missing its '---' separator.")

    prompt = prompt.strip()
    if not prompt:
        raise ModelError(f"{filename} has no prompt below the separator.")

    return prompt


class Agent:
    """One model with one job."""

    def __init__(self, role, model, settings):
        self.role = role
        self.model = model
        self._settings = settings
        self._client = Client(host=settings.host, timeout=settings.timeout_seconds)

    def ask(self, prompt_file, message):
        try:
            response = self._client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": load_prompt(prompt_file)},
                    {"role": "user", "content": message},
                ],
                options={
                    "temperature": self._settings.temperature,
                    "num_ctx": self._settings.context_tokens,
                    "num_predict": self._settings.reply_tokens,
                },
            )
        except (ResponseError, ConnectionError, TimeoutError, OSError) as exc:
            raise ModelError(f"{self.role} model {self.model} is unavailable: {exc}") from exc

        reply = (response.message.content or "").strip()
        if not reply:
            raise ModelError(f"{self.role} model {self.model} returned an empty response.")

        return reply


def build_agents(settings):
    """The implementation agent and the review agent, in that order."""
    return (
        Agent("implementation", settings.implementation_model, settings),
        Agent("review", settings.review_model, settings),
    )


def ollama_host_from_env(default):
    return os.getenv("OLLAMA_URL", default)
