"""The written output of a run.

The report is the deliverable. Nothing in this tool changes a service, so the
run is only worth anything if a developer can read what came out of it, see the
evidence behind each recommendation, and see which ones the reviewer threw out.
"""

from datetime import datetime
from pathlib import Path

from loop.observe import SEVERITIES

REPORT_DIRECTORY = Path(__file__).resolve().parent.parent / "reports"

STATUS_ICON = {
    "critical": "critical",
    "major": "major",
    "minor": "minor",
    "info": "info only",
    "clean": "clean",
}


def _summary_table(observations):
    lines = [
        "| Endpoint | Response | Rows | Worst finding | Findings |",
        "| --- | --- | --- | --- | --- |",
    ]
    for observation in observations:
        probe = observation.probe
        response = "no response" if not probe.reached else f"{probe.status} in {probe.latency_ms}ms"
        rows = str(observation.record_count) if observation.is_collection else "-"
        lines.append(
            f"| `{observation.ref}` | {response} | {rows} | "
            f"{STATUS_ICON[observation.worst()]} | {len(observation.findings)} |"
        )

    return "\n".join(lines)


def _findings_by_severity(findings):
    if not findings:
        return "No findings. Every configured endpoint passed every check."

    blocks = []
    for severity in SEVERITIES:
        matching = [finding for finding in findings if finding.severity == severity]
        if not matching:
            continue
        blocks.append(f"**{severity}** ({len(matching)})\n")
        blocks.extend(
            f"- `{finding.endpoint}` **{finding.code}** — {finding.message}" for finding in matching
        )
        blocks.append("")

    return "\n".join(blocks)


def _plan_section(plan):
    lines = [
        "#### Plan",
        "",
        f"- Goal: {plan.goal}",
        f"- Chosen by: {plan.source}",
        f"- Probing: {', '.join(f'`{endpoint.ref}`' for endpoint in plan.targets)}",
    ]
    if plan.note:
        lines.append(f"- Note: {plan.note}")

    return "\n".join(lines)


def _act_section(observations):
    lines = ["#### Act", "", "Read-only GET requests, one per planned endpoint.", ""]
    lines.append(_summary_table(observations))

    return "\n".join(lines)


def _observe_section(observations, draft):
    findings = [finding for observation in observations for finding in observation.findings]
    lines = ["#### Observe", "", _findings_by_severity(findings), ""]

    lines.append(f"Recommendations drafted by: {draft.source}")
    if draft.note:
        lines.append(f"\nNote: {draft.note}")
    lines.append("")

    if draft.recommendations:
        lines.extend(
            f"{index}. `{item.endpoint}` — {item.text}"
            for index, item in enumerate(draft.recommendations, start=1)
        )
    else:
        lines.append("Nothing to recommend for these endpoints.")

    return "\n".join(lines)


def _adapt_section(review):
    lines = ["#### Adapt", "", f"Reviewed by: {review.source}"]
    if review.note:
        lines.append(f"\nNote: {review.note}")
    lines.append("")

    if review.verdicts:
        lines.append("| Verdict | Recommendation | Reviewer's reason |")
        lines.append("| --- | --- | --- |")
        for verdict in review.verdicts:
            recommendation = verdict.recommendation.replace("|", "\\|")
            reason = (verdict.reason or "-").replace("|", "\\|")
            lines.append(f"| {verdict.decision} | {recommendation} | {reason} |")
    else:
        lines.append("No verdicts were returned.")

    if review.summary:
        lines.append(f"\n{review.summary}")
    if review.next_focus:
        lines.append(f"\nNext iteration should look at: {', '.join(f'`{ref}`' for ref in review.next_focus)}")

    return "\n".join(lines)


def _kept(state):
    """The distinct recommendations the reviewer did not throw out.

    An endpoint that stays broken produces the same advice on every pass, so
    without deduplication this list repeats itself once per iteration. The
    per-iteration detail is kept below in full; this is meant to be a list of
    things to do, and a thing to do only needs saying once. The latest verdict
    on a recommendation is the one that stands.
    """
    kept = {}
    for iteration in state.iterations:
        if not iteration.review:
            continue
        for verdict in iteration.review.verdicts:
            if verdict.decision == "REJECT":
                continue
            kept[" ".join(verdict.recommendation.lower().split())] = (
                verdict.decision,
                verdict.recommendation,
            )

    return list(kept.values())


def build_report(config, state, started_at):
    observations = state.latest_observations()
    findings = [finding for observation in observations for finding in observation.findings]
    kept = _kept(state)

    lines = [
        "# Data quality review",
        "",
        f"- Run at: {started_at:%Y-%m-%d %H:%M:%S}",
        f"- Implementation agent: `{config.models.implementation_model}` (plans, recommends)",
        f"- Review agent: `{config.models.review_model}` (reviews, sets the next focus)",
        f"- Endpoints configured: {len(config.endpoints)} across {len(config.services)} services",
        f"- Iterations run: {len(state.iterations)}",
        "",
        "This tool changes nothing. Everything below is a recommendation for a developer to act on,",
        "and every probe was a read-only GET against an endpoint listed in `services.yml`.",
        "",
        "## What to do",
        "",
    ]

    if kept:
        lines.extend(
            f"{index}. **{decision}** — {text}"
            for index, (decision, text) in enumerate(kept, start=1)
        )
    else:
        lines.append(
            "Nothing was recommended. Either every endpoint passed, or none could be reached."
        )

    lines.extend([
        "", "## Endpoints", "", _summary_table(observations),
        "", "## All findings", "", _findings_by_severity(findings), "",
    ])

    for iteration in state.iterations:
        lines.append(f"## Iteration {iteration.number}")
        lines.append("")
        if iteration.plan:
            lines.extend([_plan_section(iteration.plan), ""])
        if iteration.observations:
            lines.extend([_act_section(iteration.observations), ""])
        if iteration.draft:
            lines.extend([_observe_section(iteration.observations, iteration.draft), ""])
        if iteration.review:
            lines.extend([_adapt_section(iteration.review), ""])

    return "\n".join(lines).rstrip() + "\n"


def write_report(text, directory=None, started_at=None):
    directory = Path(directory or REPORT_DIRECTORY)
    directory.mkdir(parents=True, exist_ok=True)
    started_at = started_at or datetime.now()
    path = directory / f"data-quality-{started_at:%Y%m%d-%H%M%S}.md"
    path.write_text(text, encoding="utf-8")

    return path


def console_summary(state):
    """The short version, for someone watching the run."""
    observations = state.latest_observations()
    lines = []
    for observation in observations:
        worst = observation.worst()
        lines.append(f"  {worst:>8}  {observation.ref}  ({len(observation.findings)} findings)")

    kept = _kept(state)
    lines.append("")
    lines.append(f"  {len(kept)} recommendations survived review.")

    return "\n".join(lines)
