import argparse
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
    parser = argparse.ArgumentParser(description="Review one area of an ASD microservice or the MCP server.")
    parser.add_argument("--area", choices=MODES, help="review area (omit for the interactive menu)")
    parser.add_argument("--service", choices=SERVICES, help="microservice (omit for the interactive menu)")
    args = parser.parse_args()
    if bool(args.area) != bool(args.service):
        parser.error("--area and --service must be supplied together")
    return args


def main() -> None:
    agent_dir = Path(__file__).resolve().parent
    repo_root = agent_dir.parent
    load_dotenv(dotenv_path=agent_dir / ".env")
    args = _arguments()

    print("AGENTIC MICROSERVICE REVIEW")
    if args.area:
        mode: ModeConfig = MODES[args.area]
        service: ServiceConfig = SERVICES[args.service]
    else:
        selected_mode = _choose("Choose a review area", MODES)
        if selected_mode is None:
            return
        mode = selected_mode
        selected_service = _choose("Choose a microservice", SERVICES)
        if selected_service is None:
            return
        service = selected_service

    result = run_mode(mode, service, repo_root, PromptRegistry(repo_root), AIRunner())
    title = f"{service.label} - {mode.label}"
    print_result(title, result)


if __name__ == "__main__":
    main()
