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

    def compose(self, agent: str, mode: ModeConfig, service: ServiceConfig | None) -> str:
        if service is None and mode.requires_service:
            raise ValueError(f"Service is required for {mode.key}")
        fragments = [
            self._read("agents", f"{agent}_prompt.txt"),
            self._read("areas", mode.prompt_name),
        ]
        if service is not None:
            fragments.append(self._read("services", f"{service.key}_prompt.txt"))
        values = {
            "{{AGENT_ROLE}}": agent,
            "{{REVIEW_AREA}}": mode.label,
            "{{SERVICE_NAME}}": service.label if service else "the integrated application",
            "{{SERVICE_PATH}}": service.directory if service else ".",
            "{{MCP_PATH}}": "mcp",
            "{{RAG_PATH}}": "rag-server",
            "{{MULTI_AGENT_PATH}}": "multi-agent-server"
        }
        combined = "\n\n".join(fragments)
        for placeholder, value in values.items():
            combined = combined.replace(placeholder, value)
        return combined
