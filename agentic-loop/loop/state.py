"""What the loop remembers between iterations.

Small on purpose. The only things a later pass needs from an earlier one are how
bad each endpoint looked and what the reviewer asked to see next; everything
else lives in the iteration records kept for the report.
"""

from dataclasses import dataclass, field

SEVERITY_ORDER = ("critical", "major", "minor", "info", "clean")


@dataclass
class Iteration:
    number: int
    plan: object = None
    observations: list = field(default_factory=list)
    draft: object = None
    review: object = None


@dataclass
class LoopState:
    iteration: int = 1
    worst_by_ref: dict = field(default_factory=dict)
    next_focus: list = field(default_factory=list)
    iterations: list = field(default_factory=list)

    def record(self, observations):
        for observation in observations:
            worst = observation.worst()
            known = self.worst_by_ref.get(observation.ref)
            # A later pass reflects the current state of the endpoint, so it
            # replaces the earlier verdict rather than being merged with it.
            if known != worst:
                self.worst_by_ref[observation.ref] = worst

    def open_problems(self):
        return {
            ref: worst
            for ref, worst in self.worst_by_ref.items()
            if worst in ("critical", "major")
        }

    def open_summary(self):
        problems = self.open_problems()
        if not problems:
            return ""

        return ", ".join(f"{ref} ({worst})" for ref, worst in sorted(problems.items()))

    def probed_refs(self):
        return set(self.worst_by_ref)

    def all_findings(self):
        return [
            finding
            for iteration in self.iterations
            for observation in iteration.observations
            for finding in observation.findings
        ]

    def latest_observations(self):
        """The most recent observation of each endpoint, worst endpoint first."""
        latest = {}
        for iteration in self.iterations:
            for observation in iteration.observations:
                latest[observation.ref] = observation

        return sorted(
            latest.values(),
            key=lambda observation: (SEVERITY_ORDER.index(observation.worst()), observation.ref),
        )
