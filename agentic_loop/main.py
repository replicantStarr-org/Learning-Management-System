import argparse
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from config.review_config import MODES, SERVICES, ModeConfig, ServiceConfig
from core.ai_runner import AIRunner
from core.orchestrator import run_mode
from core.prompt_registry import PromptRegistry
from core.reporter import print_result


def _choose(title: str, options: dict) -> object | None:
    values = list(options.values())
    print(f"\n{title}")
    for number, value in enumerate(values, 1):
        print(f"{number} - {value.label}")
    print("0 - Exit")
    while True:
        choice = input("Choice: ").strip()
        if choice == "0":
            return None
        if choice.isdigit() and 1 <= int(choice) <= len(values):
            return values[int(choice) - 1]
        print(f"Enter a number from 0 to {len(values)}.")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review one area of an ASD microservice or its shared AI integrations.")
    parser.add_argument("--area", choices=MODES, help="review area (omit for the interactive menu)")
    parser.add_argument("--service", choices=SERVICES, help="microservice (optional for pre_test and deployment)")
    args = parser.parse_args()
    if args.service and not args.area:
        parser.error("--service requires --area")
    if args.area and MODES[args.area].requires_service and not args.service:
        parser.error(f"--service is required for --area {args.area}")
    return args


def main() -> None:
    agent_dir = Path(__file__).resolve().parent
    repo_root = agent_dir.parent
    load_dotenv(dotenv_path=agent_dir / ".env")
    args = _arguments()

    print("AGENTIC MICROSERVICE REVIEW")
    if args.area:
        mode: ModeConfig = MODES[args.area]
        service: ServiceConfig | None = SERVICES[args.service] if args.service else None
    else:
        selected_mode = _choose("Choose a review area", MODES)
        if selected_mode is None:
            return
        mode = selected_mode
        service = None
        if mode.requires_service:
            selected_service = _choose("Choose a microservice", SERVICES)
            if selected_service is None:
                return
            service = selected_service

    result = run_mode(mode, service, repo_root, PromptRegistry(repo_root), AIRunner())
    title = f"{service.label if service else 'Repository-wide'} - {mode.label}"
    print_result(title, result)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = service.key if service else "repository"
    log_path = agent_dir / "runs" / f"{mode.key}-{target}-{timestamp}.md"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        f"# {title}\n\n- Mode: `{mode.key}`\n- Target: `{target}`\n- Timestamp (UTC): `{timestamp}`\n\n{result}\n",
        encoding="utf-8",
    )
    print(f"Review and validation log: {log_path.relative_to(repo_root)}")


if __name__ == "__main__":
    main()
