from pathlib import Path

from config.review_config import ModeConfig, ServiceConfig


class PromptRegistry:
    """Loads auto-discovered agent, area, and service prompt fragments."""

    def __init__(self, repo_root: Path):
        self.root = repo_root / "prompts"

    def _read(self, directory: str, filename: str) -> str:
        candidate = self.root / directory / filename
        if not candidate.is_file():
            raise FileNotFoundError(f"Missing prompt file: {candidate}")
        return candidate.read_text(encoding="utf-8").strip()

    def compose(self, agent: str, mode: ModeConfig, service: ServiceConfig) -> str:
        fragments = [
            self._read("agents", f"{agent}_prompt.txt"),
            self._read("areas", mode.prompt_name),
        ]
        fragments.append(self._read("services", f"{service.key}_prompt.txt"))
        values = {
            "{{AGENT_ROLE}}": agent,
            "{{REVIEW_AREA}}": mode.label,
            "{{SERVICE_NAME}}": service.label,
            "{{SERVICE_PATH}}": service.directory,
            "{{MCP_PATH}}": "mcp",
            "{{RAG_PATH}}": "rag-server"
        }
        combined = "\n\n".join(fragments)
        for placeholder, value in values.items():
            combined = combined.replace(placeholder, value)
        return combined
