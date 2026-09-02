"""Act: the only step that touches another service.

A probe is a plain GET, the same request a browser or another microservice would
make. Nothing here interprets the body; that is the Observe step's job. Keeping
the two apart means a probe can be recorded once and re-read by every later step
without the service being hit again.
"""

import time
from dataclasses import dataclass, field

import requests

# Bodies are kept in full for the checks but truncated before they reach a report
# or a prompt, because a catalogue endpoint can return far more text than either
# has room for.
EXCERPT_LIMIT = 400


@dataclass
class Probe:
    endpoint: object
    status: int = 0
    latency_ms: int = 0
    content_type: str = ""
    size_bytes: int = 0
    body: str = ""
    error: str = ""
    findings: list = field(default_factory=list)

    @property
    def ref(self):
        return self.endpoint.ref

    @property
    def reached(self):
        return not self.error

    def excerpt(self, limit=EXCERPT_LIMIT):
        body = " ".join(self.body.split())
        if len(body) <= limit:
            return body

        return body[:limit] + f"... [{self.size_bytes} bytes total]"


def probe(endpoint, timeout_seconds):
    started = time.monotonic()
    try:
        response = requests.get(
            endpoint.url,
            timeout=timeout_seconds,
            # A stale cached body would be reported as today's data quality.
            headers={"Accept": "*/*", "Cache-Control": "no-cache"},
        )
    except requests.RequestException as exc:
        # A service that is simply not running is the most common case here, and
        # it is worth reporting rather than crashing the pass.
        return Probe(
            endpoint=endpoint,
            latency_ms=int((time.monotonic() - started) * 1000),
            error=str(exc),
        )

    return Probe(
        endpoint=endpoint,
        status=response.status_code,
        latency_ms=int((time.monotonic() - started) * 1000),
        content_type=response.headers.get("Content-Type", ""),
        size_bytes=len(response.content),
        body=response.text,
    )


def probe_all(endpoints, timeout_seconds):
    return [probe(endpoint, timeout_seconds) for endpoint in endpoints]
