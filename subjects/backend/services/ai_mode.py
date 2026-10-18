"""Environment variable switch for subject summaries and AI questions."""

import os


DISABLED_MESSAGE = "AI mode is disabled in this deployment."


def ai_mode_is_enabled():
    return os.getenv("AI_MODE_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
