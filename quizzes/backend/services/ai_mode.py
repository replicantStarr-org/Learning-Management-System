"""AI-Mode switch for the quizzes backend.

AI-Mode covers the two features that call the local model: quiz generation and
AI attempt feedback. It is on by default for local use and switched off with
AI_MODE_ENABLED=false (CI and the cloud deployment), where no model is available.
"""

import os


TRUE_VALUES = {"1", "true", "yes", "on"}
DISABLED_MESSAGE = "AI-Mode is disabled."


def ai_mode_is_enabled():
    return os.getenv("AI_MODE_ENABLED", "true").strip().lower() in TRUE_VALUES
