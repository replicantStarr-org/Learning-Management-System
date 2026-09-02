"""Plan: deciding what to look at next, and why.

The implementation agent chooses, but only from a shortlist this module builds,
and the shortlist is already in a sensible order. If the model answers with
nothing usable the shortlist is taken as the plan, so a weak model can improve
the ordering but can never derail the pass.
"""

from dataclasses import dataclass, field

from loop.ollama_client import ModelError

PLAN_PROMPT = "plan_prompt.md"

# Ranks the shortlist. Endpoints nobody has looked at yet come first, because
# nothing in the application changes during a run: re-probing an endpoint that
# was already found broken returns the same body and teaches nothing until a
# developer has acted on the report. The reviewer's steer therefore decides the
# order within a tier rather than overriding coverage.
UNSEEN_FOCUS_RANK = 0
UNSEEN_RANK = 1
RECHECK_RANK = 2
KNOWN_PROBLEM_RANK = 3
SETTLED_RANK = 4

SEVERITY_WEIGHT = {"critical": 0, "major": 1, "minor": 2, "info": 3, "clean": 4}


@dataclass
class Plan:
    goal: str
    targets: list
    source: str
    raw: str = ""
    note: str = ""
    shortlist: list = field(default_factory=list)


def _rank(endpoint, state):
    ref = endpoint.ref
    wanted = ref in state.next_focus

    if ref not in state.worst_by_ref:
        return (UNSEEN_FOCUS_RANK if wanted else UNSEEN_RANK, 0, ref)

    worst = state.worst_by_ref[ref]
    if worst in ("critical", "major"):
        return (RECHECK_RANK if wanted else KNOWN_PROBLEM_RANK, SEVERITY_WEIGHT[worst], ref)

    return (SETTLED_RANK, SEVERITY_WEIGHT.get(worst, 4), ref)


def shortlist(config, state):
    """Candidate endpoints, most worth probing first."""
    return sorted(config.endpoints, key=lambda endpoint: _rank(endpoint, state))


def _describe(config, endpoints, state):
    lines = []
    for endpoint in endpoints:
        status = state.worst_by_ref.get(endpoint.ref)
        seen = f"last pass: {status}" if status else "not probed yet"
        description = config.describe_service(endpoint.service)
        lines.append(f"- {endpoint.ref} ({seen}) - {description}")

    return "\n".join(lines)


def _parse(reply, candidates):
    """Pull a goal and any endpoint names the model actually named.

    Matching is by substring against the real endpoint refs rather than by
    parsing a format, because a small model will not hold a format reliably and
    an invented endpoint must never make it into a probe.
    """
    goal = ""
    for line in reply.splitlines():
        line = line.strip()
        if line.upper().startswith("GOAL:"):
            goal = line.split(":", 1)[1].strip()
            break

    chosen = []
    for endpoint in candidates:
        if endpoint.ref in reply and endpoint not in chosen:
            chosen.append(endpoint)

    return goal, chosen


def make_plan(agent, config, state):
    candidates = shortlist(config, state)
    limit = config.loop.endpoints_per_iteration
    # The model only ever chooses from the top of the shortlist, so the prompt
    # stays small and every option in it is one worth spending a probe on.
    offered = candidates[: limit * 2]
    fallback = candidates[:limit]

    message = (
        f"Iteration {state.iteration} of {config.loop.max_iterations}.\n"
        f"Pick at most {limit} endpoints to probe next.\n\n"
        f"AVAILABLE ENDPOINTS:\n{_describe(config, offered, state)}\n\n"
        f"REVIEWER ASKED FOR NEXT: "
        f"{', '.join(state.next_focus) if state.next_focus else 'nothing in particular'}\n"
        f"OPEN PROBLEMS SO FAR: {state.open_summary() or 'none recorded yet'}"
    )

    try:
        reply = agent.ask(PLAN_PROMPT, message)
    except ModelError as exc:
        return Plan(
            goal="Probe the endpoints that have been seen least or are known to be failing.",
            targets=fallback,
            source="fallback",
            note=str(exc),
            shortlist=offered,
        )

    goal, chosen = _parse(reply, offered)
    if not chosen:
        return Plan(
            goal=goal or "Probe the endpoints that have been seen least or are known to be failing.",
            targets=fallback,
            source="fallback",
            raw=reply,
            note="The implementation model named no endpoint that exists in services.yml.",
            shortlist=offered,
        )

    targets = chosen[:limit]
    note = ""
    if len(targets) < limit:
        # A 0.5B model will sometimes name one endpoint and stop, which spends a
        # whole pass on a fraction of what it could have covered. Its choices are
        # kept and lead the list; the rest of the pass is filled from the
        # shortlist rather than left empty.
        topped_up = [endpoint for endpoint in candidates if endpoint not in targets]
        added = topped_up[: limit - len(targets)]
        if added:
            note = (
                f"The implementation model chose {len(targets)}; "
                f"{len(added)} more were added from the shortlist to fill the pass."
            )
        targets = targets + added

    return Plan(
        goal=goal or "Check the data quality of the chosen endpoints.",
        targets=targets,
        source=f"implementation model ({agent.model})",
        raw=reply,
        note=note,
        shortlist=offered,
    )
