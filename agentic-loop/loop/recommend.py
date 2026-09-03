"""The implementation agent's half of Observe: findings turned into advice.

Nothing here changes a service. The output is a list of things a developer could
do, which is the whole product of this tool.

Every finding code also has a written remedy below. Those are what the report
falls back to, and they are also the floor: if the model does not write about an
endpoint that has findings, the written remedy for it is used instead, so a real
problem is never dropped just because the model failed to mention it.
"""

import re
from dataclasses import dataclass

from loop.ollama_client import ModelError

RECOMMEND_PROMPT = "recommend_prompt.md"

# How many recommendations one iteration may carry. More than this and the
# report stops being a list a person will act on.
MAX_RECOMMENDATIONS = 8

# Shortest a line can be and still be advice rather than a fragment.
MIN_RECOMMENDATION_LENGTH = 20

# The headings used in the evidence block. A small model will sometimes echo one
# back instead of answering, and an echoed heading must not become advice.
EVIDENCE_LABELS = ("endpoint", "url", "result", "rows", "findings", "note from config", "evidence")

# The deterministic answer to each check in observe.py, written as an
# instruction to a developer.
REMEDIES = {
    "unreachable":
        "Start the service or correct its URL in services.yml before trusting any other finding for it.",
    "server-error":
        "Fix the unhandled failure behind the 500; the endpoint is returning an error page to real clients.",
    "client-error":
        "Confirm the path still exists and update services.yml, or restore the resource it names.",
    "unexpected-status":
        "Return 200 for a successful read so clients can branch on the status alone.",
    "slow-response":
        "Profile the query behind this endpoint; a plain read should not be this slow at this data size.",
    "empty-body":
        "Return an explicit empty collection or object instead of nothing, so clients can parse a "
        "response either way.",
    "content-type-mismatch":
        "Set the Content-Type header to match what is actually returned.",
    "invalid-json":
        "Return JSON from this endpoint, or change its `expect` in services.yml if it was never meant to.",
    "shape-mismatch":
        "Settle on one shape for this endpoint and correct either the service or the `expect` value.",
    "missing-collection":
        "Correct `records_at` in services.yml, or return the collection under the key clients expect.",
    "empty-collection":
        "Seed this table in populate_db.sql so the feature has something to render.",
    "records-not-objects":
        "Return named objects rather than positional rows so consumers stop depending on column order.",
    "mixed-record-shapes":
        "Return every row in the same shape.",
    "missing-required-field":
        "Add the field to the query behind this endpoint, or drop it from required_fields if it is "
        "genuinely gone.",
    "inconsistent-required-field":
        "Make the field non optional in the schema and backfill the rows that lack it.",
    "sparse-field":
        "Return the field on every row, using an explicit null where there is no value.",
    "always-blank-field":
        "Populate this field or stop returning it; every consumer is handling a column that never has data.",
    "blank-values":
        "Backfill the empty rows, or make the field NOT NULL so more cannot be created.",
    "mixed-types":
        "Pick one type for the field and cast it in the query so clients do not have to guess.",
    "placeholder-values":
        "Replace the filler values with real data before this is demonstrated.",
    "untrimmed-values":
        "Trim values on write so sorting and equality comparisons behave.",
    "duplicate-identifier":
        "Add a unique constraint on the identifier column; rows cannot currently be addressed one at a time.",
    "duplicate-records":
        "De-duplicate the table and add a constraint that stops identical rows being inserted again.",
    "missing-identifier":
        "Return the identifier column so individual rows can be addressed.",
    "large-collection":
        "Paginate this endpoint before the collection grows further.",
    "leaked-error":
        "Catch the failure and render an error state; a stack trace is reaching the browser.",
    "empty-fragment":
        "Return an empty state fragment so the page does not silently render nothing.",
    "thin-fragment":
        "Check this fragment renders what it should; it returned almost no markup.",
    "unrendered-value":
        "Fix the template or the value it is given; a placeholder is reaching the page unrendered.",
}


@dataclass
class Recommendation:
    endpoint: str
    text: str
    source: str

    def __str__(self):
        return f"{self.endpoint}: {self.text}"


@dataclass
class Draft:
    recommendations: list
    source: str
    raw: str = ""
    note: str = ""


def from_findings(observations):
    """One recommendation per finding, worst first, deduplicated per endpoint.

    Informational findings are left out: they describe the data rather than ask
    for a change, and a list of things to do should only contain things to do.
    """
    recommendations = []
    seen = set()
    for observation in observations:
        for finding in observation.findings:
            if finding.severity == "info":
                continue
            remedy = REMEDIES.get(finding.code)
            if not remedy:
                continue
            key = (observation.ref, finding.code)
            if key in seen:
                continue
            seen.add(key)
            recommendations.append(
                Recommendation(endpoint=observation.ref, text=f"{finding.message} {remedy}", source="checks")
            )

    return recommendations


def _is_junk(line):
    """Whether a line is an echo of the prompt rather than an answer."""
    if len(line) < MIN_RECOMMENDATION_LENGTH or line.endswith(":"):
        return True

    lowered = line.lower()

    return any(lowered.startswith(f"{label}:") for label in EVIDENCE_LABELS)


def _normalise(text):
    return " ".join(text.lower().split())


def _strip_label(line, endpoint):
    """Drop the endpoint name only where it is a leading label.

    Removing it wherever it appears was the simpler rule and it mangled
    sentences: "update the `svc/ep` endpoint" came out as "update the ``
    endpoint". Mid sentence the name is part of what the model wrote, so it
    stays.
    """
    for candidate in (f"`{endpoint}`", endpoint):
        if line.startswith(candidate):
            return line[len(candidate):].lstrip(" -:–—").strip()

    return line


def _parse(reply, eligible, evidence=""):
    """Read back the model's recommendations, keeping only attributable ones.

    A line is dropped unless it names one of the endpoints that actually has a
    finding this pass. Guessing an endpoint for an unattributed line was the
    alternative, and that produces advice filed against a service it was never
    about, which is worse than losing the line.
    """
    haystack = _normalise(evidence)
    recommendations = []
    seen = set()

    for raw_line in reply.splitlines():
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", raw_line).strip().strip("*")
        if _is_junk(line):
            continue

        # Longest first, so `subjects/list-subjects` is not matched as a shorter
        # endpoint name that happens to be a prefix of it.
        endpoint = next((ref for ref in sorted(eligible, key=len, reverse=True) if ref in line), "")
        if not endpoint:
            continue

        text = _strip_label(line, endpoint)

        # A small model often answers by copying a finding back. That is not a
        # recommendation, and the written remedy for the same finding is better
        # than the echo, so drop it and let the merge fill the gap.
        if haystack and _normalise(text) in haystack:
            continue

        if _is_junk(text) or (endpoint, text) in seen:
            continue

        seen.add((endpoint, text))
        recommendations.append(Recommendation(endpoint=endpoint, text=text, source="model"))

    return recommendations


def _merge(parsed, computed):
    """The model's wording where it wrote any, the written remedy where it did not.

    Ordered by `computed`, which is already worst finding first, so the merged
    list keeps that order regardless of what order the model answered in.
    """
    by_endpoint = {}
    for item in parsed:
        by_endpoint.setdefault(item.endpoint, []).append(item)

    merged = []
    taken = set()
    for item in computed:
        if item.endpoint in by_endpoint:
            if item.endpoint not in taken:
                merged.extend(by_endpoint[item.endpoint])
                taken.add(item.endpoint)
        else:
            merged.append(item)

    return merged[:MAX_RECOMMENDATIONS]


def draft(agent, observations, evidence):
    """What the implementation agent thinks should be done about the evidence."""
    computed = from_findings(observations)
    if not computed:
        return Draft(recommendations=[], source="checks", note="No findings that ask for a change.")

    eligible = {item.endpoint for item in computed}

    message = (
        f"EVIDENCE:\n{evidence}\n\n"
        f"Write at most {MAX_RECOMMENDATIONS} recommendations, one per line, each beginning with one of "
        f"these endpoint names: {', '.join(sorted(eligible))}"
    )

    try:
        reply = agent.ask(RECOMMEND_PROMPT, message)
    except ModelError as exc:
        return Draft(recommendations=computed[:MAX_RECOMMENDATIONS], source="checks", note=str(exc))

    parsed = _parse(reply, eligible, evidence)
    if not parsed:
        return Draft(
            recommendations=computed[:MAX_RECOMMENDATIONS],
            source="checks",
            raw=reply,
            note="The implementation model returned nothing that could be tied to an endpoint "
                 "with a finding.",
        )

    merged = _merge(parsed, computed)
    covered = len({item.endpoint for item in merged if item.source == "model"})
    source = f"implementation model ({agent.model})"
    if covered < len(eligible):
        source += ", with written remedies for the endpoints it did not mention"

    return Draft(recommendations=merged, source=source, raw=reply)
