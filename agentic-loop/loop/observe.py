"""Observe: turning a response into data quality findings.

Every finding in this module is computed in Python, not asked of a model. That
is deliberate. A 0.5B model handed a raw JSON body will confidently describe
fields that are not there, so the models are never the thing that decides
whether a problem exists. They are given this evidence and asked what a
developer should do about it.
"""

import json
from dataclasses import dataclass, field

# Worst first. Used for sorting and for deciding what a report leads with.
SEVERITIES = ("critical", "major", "minor", "info")

# Values that parse as data but mean a field was never really filled in. Kept
# lowercase; comparison strips and folds case.
PLACEHOLDERS = {
    "string", "todo", "tbd", "n/a", "na", "none", "null", "nil", "undefined",
    "unknown", "test", "testing", "example", "sample", "changeme", "foo", "bar",
    "lorem ipsum", "placeholder", "xxx", "asdf", "-",
}

# Text that should never reach a client. A stack trace in a response body is a
# leak and a bug at once, so it outranks everything else.
ERROR_MARKERS = ("traceback (most recent call last)", "internal server error", "werkzeug")

# Below this a fragment is almost certainly an empty state rendered by accident.
THIN_FRAGMENT_BYTES = 40

# Constant value checks need enough rows to mean anything.
MIN_ROWS_FOR_CONSTANT = 3


@dataclass
class Finding:
    endpoint: str
    severity: str
    code: str
    message: str

    def __str__(self):
        return f"[{self.severity}] {self.endpoint} {self.code}: {self.message}"


@dataclass
class FieldProfile:
    name: str
    present: int = 0
    blank: int = 0
    types: set = field(default_factory=set)
    distinct: set = field(default_factory=set)
    placeholders: int = 0
    untrimmed: int = 0


@dataclass
class Observation:
    probe: object
    findings: list = field(default_factory=list)
    record_count: int = 0
    # False for an endpoint that returns one object rather than a collection, so
    # a report does not present a row count that was never a row count.
    is_collection: bool = False
    profiles: list = field(default_factory=list)

    @property
    def ref(self):
        return self.probe.ref

    @property
    def clean(self):
        return not [item for item in self.findings if item.severity != "info"]

    def worst(self):
        for severity in SEVERITIES:
            if any(item.severity == severity for item in self.findings):
                return severity

        return "clean"


def sort_findings(findings):
    return sorted(findings, key=lambda item: (SEVERITIES.index(item.severity), item.endpoint))


def _article(word):
    return "an" if word[:1] in "aeiou" else "a"


def _type_name(value):
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "object"

    return "null"


def _is_blank(value):
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list | dict):
        return not value

    return False


def _resolve(payload, path):
    """Follow a dotted `records_at` path, returning None if it does not lead anywhere."""
    current = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]

    return current


def _transport_findings(probe, slow_response_ms):
    ref = probe.ref
    findings = []

    if not probe.reached:
        findings.append(
            Finding(ref, "critical", "unreachable", f"No response from {probe.endpoint.url}: {probe.error}")
        )
        return findings

    if probe.status >= 500:
        findings.append(
            Finding(ref, "critical", "server-error", f"Responded {probe.status}, so the service is failing.")
        )
    elif probe.status >= 400:
        findings.append(
            Finding(
                ref,
                "major",
                "client-error",
                f"Responded {probe.status}. Either the URL in services.yml is wrong or the "
                f"resource it names no longer exists.",
            )
        )
    elif probe.status != 200:
        findings.append(Finding(ref, "minor", "unexpected-status", f"Responded {probe.status}, not 200."))

    if probe.latency_ms > slow_response_ms:
        findings.append(
            Finding(ref, "minor", "slow-response", f"Took {probe.latency_ms}ms to answer a plain GET.")
        )

    if probe.size_bytes == 0:
        findings.append(Finding(ref, "major", "empty-body", "Responded with an empty body."))

    # Only worth checking on a successful read. A failing endpoint returning an
    # HTML error page is expected, and saying so here only buries the failure
    # that actually matters.
    if probe.status != 200:
        return findings

    expects_json = probe.endpoint.expect.startswith("json")
    content_type = probe.content_type.lower()
    if expects_json and content_type and "json" not in content_type:
        findings.append(
            Finding(
                ref, "minor", "content-type-mismatch",
                f"Sent Content-Type {probe.content_type} for JSON.",
            )
        )
    if probe.endpoint.expect == "html" and content_type and "html" not in content_type:
        findings.append(
            Finding(
                ref, "minor", "content-type-mismatch",
                f"Sent Content-Type {probe.content_type} for HTML.",
            )
        )

    return findings


def _markup_findings(probe):
    ref = probe.ref
    findings = []
    body = probe.body.lower()

    for marker in ERROR_MARKERS:
        if marker in body:
            findings.append(
                Finding(
                    ref,
                    "critical",
                    "leaked-error",
                    f"The body contains '{marker}', so a server error is being rendered to the user.",
                )
            )
            break

    stripped = probe.body.strip()
    if not stripped:
        findings.append(Finding(ref, "major", "empty-fragment", "The fragment is blank."))
    elif len(stripped) < THIN_FRAGMENT_BYTES:
        findings.append(
            Finding(
                ref, "minor", "thin-fragment",
                f"Only {len(stripped)} characters of markup were returned.",
            )
        )

    if "{{" in probe.body or "None" in probe.body.split():
        findings.append(
            Finding(
                ref,
                "major",
                "unrendered-value",
                "The markup contains an unsubstituted template marker or a literal 'None'.",
            )
        )

    return findings


def _extract_records(probe):
    """The rows to profile, plus any finding raised while getting to them.

    Returns (records, findings, is_collection). `records` is None when the body
    could not be read as the configured shape at all, and `is_collection` is
    False for an endpoint that returns a single object rather than many rows.
    """
    ref = probe.ref
    endpoint = probe.endpoint

    try:
        payload = json.loads(probe.body)
    except (ValueError, TypeError):
        return None, [
            Finding(ref, "critical", "invalid-json", f"The body is not JSON. It begins: {probe.excerpt(120)}")
        ], False

    if endpoint.expect == "json_array":
        if not isinstance(payload, list):
            shape = _type_name(payload)
            hint = ""
            if isinstance(payload, dict):
                # Almost always the collection is one key down, so name the keys
                # rather than leaving the developer to go and look.
                hint = f" Its keys are: {', '.join(sorted(payload)[:8])}."
            return None, [
                Finding(
                    ref,
                    "major",
                    "shape-mismatch",
                    f"Configured as a list but returned {_article(shape)} {shape}.{hint}",
                )
            ], False
        return payload, [], True

    else:
        if not isinstance(payload, dict):
            shape = _type_name(payload)
            return None, [
                Finding(
                    ref,
                    "major",
                    "shape-mismatch",
                    f"Configured as an object but returned {_article(shape)} {shape}.",
                )
            ], False
        if endpoint.records_at:
            nested = _resolve(payload, endpoint.records_at)
            if not isinstance(nested, list):
                return None, [
                    Finding(
                        ref,
                        "major",
                        "missing-collection",
                        f"records_at '{endpoint.records_at}' does not lead to a list in the response.",
                    )
                ], False
            return nested, [], True

        # A single object is profiled as one row, which still catches blank and
        # placeholder fields even though every rate is all or nothing.
        return [payload], [], False


def _profile_fields(records):
    profiles = {}
    for record in records:
        for name, value in record.items():
            profile = profiles.setdefault(name, FieldProfile(name=name))
            profile.present += 1
            profile.types.add(_type_name(value))

            if _is_blank(value):
                profile.blank += 1
                continue

            if isinstance(value, str):
                text = value.strip()
                if text.lower() in PLACEHOLDERS:
                    profile.placeholders += 1
                if text != value:
                    profile.untrimmed += 1

            if isinstance(value, str | int | float | bool):
                # Bounded so one wide free text column cannot hold the whole
                # response in memory just to be counted.
                if len(profile.distinct) < 100:
                    profile.distinct.add(str(value))

    return list(profiles.values())


def _collection_findings(probe, records, max_records):
    ref = probe.ref
    endpoint = probe.endpoint
    findings = []

    if not records:
        findings.append(
            Finding(
                ref,
                "major",
                "empty-collection",
                "The endpoint works but returned no rows, so anything reading it renders empty.",
            )
        )
        return findings, []

    if len(records) > max_records:
        findings.append(
            Finding(
                ref,
                "info",
                "large-collection",
                f"{len(records)} rows returned; only the first {max_records} were profiled. "
                f"An unpaginated collection this size will keep growing.",
            )
        )
        records = records[:max_records]

    objects = [record for record in records if isinstance(record, dict)]
    if not objects:
        if all(isinstance(record, list) for record in records):
            findings.append(
                Finding(
                    ref,
                    "major",
                    "records-not-objects",
                    "Rows are returned as positional lists rather than named objects, so every consumer "
                    "depends on column order and no field can be validated.",
                )
            )
        else:
            # A flat list of colours or tags is a perfectly good response; there
            # is simply nothing per field to profile in it.
            findings.append(
                Finding(
                    ref,
                    "info",
                    "scalar-collection",
                    f"{len(records)} plain values rather than objects, so no per field checks apply.",
                )
            )
        return findings, []

    if len(objects) != len(records):
        findings.append(
            Finding(
                ref,
                "major",
                "mixed-record-shapes",
                f"{len(records) - len(objects)} of {len(records)} rows are not objects.",
            )
        )

    total = len(objects)
    profiles = _profile_fields(objects)
    by_name = {profile.name: profile for profile in profiles}

    for wanted in endpoint.required_fields:
        profile = by_name.get(wanted)
        if profile is None:
            findings.append(
                Finding(
                    ref,
                    "major",
                    "missing-required-field",
                    f"'{wanted}' is required by services.yml but appears in no row.",
                )
            )
        elif profile.present < total:
            findings.append(
                Finding(
                    ref,
                    "major",
                    "inconsistent-required-field",
                    f"'{wanted}' is missing from {total - profile.present} of {total} rows.",
                )
            )

    for profile in profiles:
        _field_findings(ref, profile, total, endpoint, findings)

    if endpoint.identifier:
        _identifier_findings(ref, objects, endpoint.identifier, findings)

    _duplicate_findings(ref, objects, findings)

    return findings, profiles


def _field_findings(ref, profile, total, endpoint, findings):
    name = profile.name
    required = name in endpoint.required_fields

    if profile.present < total and not required:
        findings.append(
            Finding(
                ref,
                "minor",
                "sparse-field",
                f"'{name}' is only present in {profile.present} of {total} rows, so consumers have to "
                f"handle its absence.",
            )
        )

    if profile.blank == profile.present and profile.present:
        findings.append(
            Finding(
                ref,
                "major" if required else "minor",
                "always-blank-field",
                f"'{name}' is present in every row and empty in every row.",
            )
        )
    elif profile.blank:
        findings.append(
            Finding(
                ref,
                "major" if required else "minor",
                "blank-values",
                f"'{name}' is empty or null in {profile.blank} of {profile.present} rows.",
            )
        )

    concrete = profile.types - {"null"}
    if len(concrete) > 1:
        findings.append(
            Finding(
                ref,
                "major",
                "mixed-types",
                f"'{name}' arrives as {', '.join(sorted(concrete))} across rows, so any consumer "
                f"parsing it has to guess.",
            )
        )

    if profile.placeholders:
        findings.append(
            Finding(
                ref,
                "major",
                "placeholder-values",
                f"'{name}' holds filler text such as 'todo' or 'test' in {profile.placeholders} rows.",
            )
        )

    if profile.untrimmed:
        findings.append(
            Finding(
                ref,
                "minor",
                "untrimmed-values",
                f"'{name}' has leading or trailing whitespace in {profile.untrimmed} rows, which breaks "
                f"sorting and equality checks.",
            )
        )

    if total >= MIN_ROWS_FOR_CONSTANT and len(profile.distinct) == 1 and not profile.blank:
        findings.append(
            Finding(
                ref,
                "info",
                "constant-field",
                f"'{name}' is '{next(iter(profile.distinct))}' in all {total} rows, so it currently "
                f"carries no information.",
            )
        )


def _identifier_findings(ref, records, identifier, findings):
    values = [record.get(identifier) for record in records if identifier in record]
    if not values:
        findings.append(
            Finding(
                ref,
                "major",
                "missing-identifier",
                f"'{identifier}' is configured as the identifier but no row carries it.",
            )
        )
        return

    seen = set()
    duplicates = set()
    for value in values:
        key = str(value)
        if key in seen:
            duplicates.add(key)
        seen.add(key)

    if duplicates:
        sample = ", ".join(sorted(duplicates)[:5])
        findings.append(
            Finding(
                ref,
                "major",
                "duplicate-identifier",
                f"'{identifier}' repeats across rows ({sample}), so rows cannot be addressed uniquely.",
            )
        )


def _duplicate_findings(ref, records, findings):
    seen = set()
    duplicates = 0
    for record in records:
        try:
            key = json.dumps(record, sort_keys=True, default=str)
        except (TypeError, ValueError):
            continue
        if key in seen:
            duplicates += 1
        seen.add(key)

    if duplicates:
        findings.append(
            Finding(
                ref,
                "major",
                "duplicate-records",
                f"{duplicates} rows are byte for byte copies of another row.",
            )
        )


def observe(probe, slow_response_ms, max_records):
    """Every check that applies to one probe, worst first."""
    observation = Observation(probe=probe)
    observation.findings.extend(_transport_findings(probe, slow_response_ms))

    # There is nothing to read in a body that never arrived, and a failing status
    # code makes an error body's shape uninteresting.
    if not probe.reached or probe.status != 200 or probe.size_bytes == 0:
        observation.findings = sort_findings(observation.findings)
        return observation

    if probe.endpoint.expect in ("html", "text"):
        observation.findings.extend(_markup_findings(probe))
        observation.findings = sort_findings(observation.findings)
        return observation

    records, problems, is_collection = _extract_records(probe)
    observation.findings.extend(problems)
    if records is not None:
        collection_findings, profiles = _collection_findings(probe, records, max_records)
        observation.findings.extend(collection_findings)
        observation.is_collection = is_collection
        observation.record_count = len(records) if is_collection else 0
        observation.profiles = profiles

    observation.findings = sort_findings(observation.findings)

    return observation


def evidence_block(observation):
    """The compact, model facing form of one observation.

    Deliberately terse: this is what both models see instead of the response
    body, so it has to hold everything a recommendation could be based on and
    nothing a model could wander off into.
    """
    probe = observation.probe
    lines = [
        f"ENDPOINT: {observation.ref}",
        f"URL: {probe.endpoint.url}",
        f"RESULT: {'no response' if not probe.reached else f'HTTP {probe.status}'} "
        f"in {probe.latency_ms}ms, {probe.size_bytes} bytes",
    ]
    if observation.record_count:
        lines.append(f"ROWS: {observation.record_count}")
    if probe.endpoint.notes:
        lines.append(f"NOTE FROM CONFIG: {probe.endpoint.notes}")

    if observation.findings:
        lines.append("FINDINGS:")
        lines.extend(f"  - {finding}" for finding in observation.findings)
    else:
        lines.append("FINDINGS: none, this endpoint passed every check.")

    return "\n".join(lines)


def evidence_report(observations):
    return "\n\n".join(evidence_block(observation) for observation in observations)
