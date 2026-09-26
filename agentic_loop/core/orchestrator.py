from pathlib import Path
from typing import Callable

from collectors import architecture_collector, db_collector, devops_collector, endpoints_collector, mcp_collector, rag_collector
from pipelines import rag_pipeline
from config.review_config import ModeConfig, ServiceConfig
from core.ai_runner import AIRunner
from core.prompt_registry import PromptRegistry


Collector = Callable[[Path, ServiceConfig], tuple[bool, str]]
COLLECTORS: dict[str, Collector] = {
    "database": db_collector.collect,
    "endpoint": endpoints_collector.collect,
    "architecture": architecture_collector.collect,
    "devops": devops_collector.collect,
    "mcp": mcp_collector.collect,
    "rag": rag_collector.collect,
}


def _stage(mode: ModeConfig, service: ServiceConfig, step: str, message: str) -> None:
    target = service.key
    print(f"[{target}][{mode.key}][{step}] {message}")


def run_mode(
    mode: ModeConfig,
    service: ServiceConfig,
    repo_root: Path,
    prompts: PromptRegistry,
    ai: AIRunner,
) -> str:
    _stage(mode, service, "OBSERVE", "Collecting and validating evidence")
    ok, evidence = COLLECTORS[mode.key](repo_root, service)
    if not ok:
        _stage(mode, service, "OBSERVE", "Validation failed; model calls skipped")
        return f"OBSERVE FAILED: {evidence}"

    implementation_prompt = prompts.compose("implementation", mode, service)
    implementation_input = f"VALIDATION EVIDENCE:\n{evidence}"
    _stage(mode, service, "IMPLEMENT", "Running implementation model")
    recommendation, error = ai.call(implementation_prompt, implementation_input)
    if error:
        return f"IMPLEMENTATION MODEL FAILED: {error}"

    review_prompt = prompts.compose("review", mode, service)
    review_input = (
        f"IMPLEMENTATION RECOMMENDATION:\n{recommendation}\n\n"
        f"VALIDATION EVIDENCE:\n{evidence}"
    )
    _stage(mode, service, "REVIEW", "Running review model")
    review, review_error = ai.call(review_prompt, review_input, review=True)
    if review_error:
        return (
            f"OBSERVE:\n{evidence}\n\nIMPLEMENTATION:\n{recommendation}\n\n"
            f"REVIEW MODEL FAILED: {review_error}"
        )

    _stage(mode, service, "DONE", "Review complete")
    return f"OBSERVE:\n{evidence}\n\nIMPLEMENTATION:\n{recommendation}\n\nREVIEW:\n{review}"
