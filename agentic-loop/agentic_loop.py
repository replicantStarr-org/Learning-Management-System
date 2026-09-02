"""Plan -> Act -> Observe -> Adapt over the endpoints listed in services.yml.

Two local models share the work. The implementation agent plans each pass and
writes the recommendations; the review agent rules on them and names what the
next pass should look at. Neither one changes anything: the output is a report
for a developer to act on.

  python agentic_loop.py                 one run, using services.yml
  python agentic_loop.py --list          show what is configured and stop
  python agentic_loop.py --offline       skip both models, checks only
  python agentic_loop.py --service quizzes   probe one service and no others
"""

import argparse
import sys
from datetime import datetime

from loop import adapt, recommend
from loop.act import probe_all
from loop.config import ConfigError, load_config
from loop.observe import evidence_report, observe
from loop.ollama_client import ModelError, build_agents
from loop.plan import make_plan
from loop.report import build_report, console_summary, write_report
from loop.state import Iteration, LoopState


class OfflineAgent:
    """Stands in for a model when --offline is used.

    Every step already has a deterministic path for a model that cannot be
    reached, so refusing every call is enough to exercise it.
    """

    def __init__(self, role):
        self.role = role
        self.model = "offline"

    def ask(self, prompt_file, message):
        raise ModelError(f"The {self.role} agent is disabled by --offline.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", help="Path to the endpoint configuration (default: services.yml).")
    parser.add_argument("--iterations", type=int, help="Override loop.max_iterations for this run.")
    parser.add_argument("--reports", help="Directory to write the report into (default: reports/).")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Run the checks without either model, using the built in remedies.",
    )
    parser.add_argument(
        "--service",
        action="append",
        metavar="NAME",
        help="Only probe this service. Repeat the flag to name more than one.",
    )
    parser.add_argument("--list", action="store_true", help="List the configured endpoints and exit.")
    parser.add_argument(
        "--fail-on-critical",
        action="store_true",
        help="Exit non zero if any endpoint has a critical finding, for use in CI.",
    )

    return parser.parse_args(argv)


def list_endpoints(config):
    for service in config.services:
        print(f"{service.name} - {service.description}")
        for endpoint in service.endpoints:
            print(f"  {endpoint.ref:<45} {endpoint.expect:<12} {endpoint.url}")


def run_iteration(config, state, implementation, reviewer):
    iteration = Iteration(number=state.iteration)

    iteration.plan = make_plan(implementation, config, state)
    print(f"  plan   : {iteration.plan.goal} [{iteration.plan.source}]")
    print(f"  act    : {', '.join(endpoint.ref for endpoint in iteration.plan.targets)}")

    probes = probe_all(iteration.plan.targets, config.loop.request_timeout_seconds)
    iteration.observations = [
        observe(item, config.loop.slow_response_ms, config.loop.max_records) for item in probes
    ]
    state.record(iteration.observations)

    findings = sum(len(observation.findings) for observation in iteration.observations)
    print(f"  observe: {findings} findings")

    evidence = evidence_report(iteration.observations)
    iteration.draft = recommend.draft(implementation, iteration.observations, evidence)
    print(f"  draft  : {len(iteration.draft.recommendations)} recommendations "
          f"[{iteration.draft.source}]")

    iteration.review = adapt.review(
        reviewer, iteration.draft.recommendations, iteration.observations, evidence
    )
    kept = len(iteration.review.kept())
    print(f"  adapt  : {kept} kept of {len(iteration.review.verdicts)} [{iteration.review.source}]")

    state.iterations.append(iteration)
    state.next_focus = iteration.review.next_focus

    return iteration


def settled(config, state):
    """Whether another pass could still tell the developer anything new.

    Once every configured endpoint has been probed and none of them are still
    failing, adapting further just re-probes healthy endpoints.
    """
    everything_seen = state.probed_refs() >= {endpoint.ref for endpoint in config.endpoints}

    return everything_seen and not state.open_problems()


def run(config, args):
    if args.offline:
        implementation, reviewer = OfflineAgent("implementation"), OfflineAgent("review")
    else:
        implementation, reviewer = build_agents(config.models)

    started_at = datetime.now()
    state = LoopState()
    iterations = args.iterations or config.loop.max_iterations

    for number in range(1, iterations + 1):
        state.iteration = number
        print(f"\nIteration {number} of {iterations}")
        run_iteration(config, state, implementation, reviewer)

        if settled(config, state):
            print("  stop   : every endpoint has been probed and none are failing")
            break

    report = build_report(config, state, started_at)
    path = write_report(report, args.reports, started_at)

    print("\nSummary")
    print(console_summary(state))
    print(f"\nReport written to {path}")

    return state


def main(argv=None):
    args = parse_args(argv)

    try:
        config = load_config(args.config)
        # Before --list, so listing shows exactly the set a real run would probe.
        if args.service:
            config = config.only(args.service)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    if args.list:
        list_endpoints(config)
        return 0

    state = run(config, args)

    if args.fail_on_critical and any(
        finding.severity == "critical" for finding in state.all_findings()
    ):
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
