"""Adapt: the review agent checks the advice and steers the next iteration.

This is the half of the loop that closes it. The reviewer sees the same evidence
the implementation agent saw and rules on each recommendation, then names what
should be probed next. That last part is fed straight back into Plan, which is
what makes the next pass different from the last one.

The larger model does this job because deciding whether a claim is supported by
evidence is exactly what the small one is worst at.
"""

import re
from dataclasses import dataclass, field

from loop.ollama_client import ModelError

REVIEW_PROMPT = "review_prompt.md"

DECISIONS = ("ACCEPT", "REVISE", "REJECT")

# Shortest a verdict's subject can be and still name a recommendation.
MIN_RECOMMENDATION_LENGTH = 20

# `ACCEPT | recommendation | reason`, tolerating a dash, colon or nothing after
# the verdict and a missing reason.
VERDICT_LINE = re.compile(
    rf"^\s*(?:[-*•]|\d+[.)])?\s*\**({'|'.join(DECISIONS)})\**\s*[:\-|]*\s*(.*)$",
    re.IGNORECASE,
)


@dataclass
class Verdict:
    decision: str
    recommendation: str
    reason: str = ""


@dataclass
class Review:
    verdicts: list
    next_focus: list = field(default_factory=list)
    summary: str = ""
    source: str = "review model"
    raw: str = ""
    note: str = ""

    def kept(self):
        """Everything the reviewer did not throw out.

        An UNREVIEWED verdict counts as kept: the reviewer being unavailable is
        not a reason to hide a finding the checks already proved.
        """
        return [verdict for verdict in self.verdicts if verdict.decision != "REJECT"]


def _numbered(recommendations):
    return "\n".join(
        f"{index}. {recommendation.endpoint}: {recommendation.text}"
        for index, recommendation in enumerate(recommendations, start=1)
    )


def _unreviewed(recommendations, observations, note):
    """What a review looks like when the reviewer could not be reached."""
    return Review(
        verdicts=[
            Verdict("UNREVIEWED", f"{item.endpoint}: {item.text}", "The review model did not answer.")
            for item in recommendations
        ],
        next_focus=[
            observation.ref
            for observation in observations
            if observation.worst() in ("critical", "major")
        ],
        source="fallback",
        note=note,
    )


def _parse(reply, recommendations, refs):
    verdicts = []
    next_focus = []
    summary = ""

    for line in reply.splitlines():
        stripped = line.strip()

        if stripped.upper().startswith("NEXT:"):
            named = stripped.split(":", 1)[1]
            next_focus = [ref for ref in refs if ref in named]
            continue

        if stripped.upper().startswith("SUMMARY:"):
            summary = stripped.split(":", 1)[1].strip()
            continue

        match = VERDICT_LINE.match(stripped)
        if not match:
            continue

        decision = match.group(1).upper()
        remainder = match.group(2).strip()
        parts = [part.strip() for part in remainder.split("|") if part.strip()]

        target = parts[0] if parts else ""
        reason = parts[1] if len(parts) > 1 else ""

        # The reviewer is asked to answer by number, so a leading number is the
        # most reliable way back to the recommendation it is ruling on.
        index_match = re.match(r"^(\d+)\b[.):]?\s*(.*)$", target)
        if index_match:
            index = int(index_match.group(1)) - 1
            if 0 <= index < len(recommendations):
                item = recommendations[index]
                target = f"{item.endpoint}: {item.text}"
            else:
                # The reviewer ruled on a recommendation that was never made.
                # There is nothing for the verdict to be about, and a report
                # line reading "ACCEPT - 2" tells a developer nothing.
                target = index_match.group(2).strip()

        if len(target) < MIN_RECOMMENDATION_LENGTH:
            continue

        verdicts.append(Verdict(decision, target, reason))

    return verdicts, next_focus, summary


def review(agent, recommendations, observations, evidence):
    refs = [observation.ref for observation in observations]

    if not recommendations:
        return Review(
            verdicts=[],
            next_focus=[],
            summary="Nothing was recommended this iteration, so there was nothing to review.",
            source="skipped",
        )

    message = (
        f"EVIDENCE:\n{evidence}\n\n"
        f"RECOMMENDATIONS TO REVIEW:\n{_numbered(recommendations)}\n\n"
        f"ENDPOINT NAMES YOU MAY CHOOSE FROM FOR NEXT: {', '.join(refs)}"
    )

    try:
        reply = agent.ask(REVIEW_PROMPT, message)
    except ModelError as exc:
        return _unreviewed(recommendations, observations, str(exc))

    verdicts, next_focus, summary = _parse(reply, recommendations, refs)
    if not verdicts:
        fallback = _unreviewed(
            recommendations,
            observations,
            "The review model answered but no verdict could be read from it.",
        )
        fallback.raw = reply
        return fallback

    if not next_focus:
        # A reviewer that forgot the NEXT line should not stall the loop, so fall
        # back to whatever still looks worst.
        next_focus = [
            observation.ref
            for observation in observations
            if observation.worst() in ("critical", "major")
        ]

    return Review(
        verdicts=verdicts,
        next_focus=next_focus,
        summary=summary,
        source=f"review model ({agent.model})",
        raw=reply,
    )
