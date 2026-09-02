"""Reading and validating the hand written endpoint configuration.

Every other service in this repository stays untouched, so the only thing the
loop knows about them is what a developer types into services.yml. That makes
this the one place where a bad hand edit can be caught, which is why validation
is strict and every error names the key that caused it.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PACKAGE_ROOT / "services.yml"

# What the body of a response is expected to look like. An unrecognised value is
# a config error rather than a finding, because it means a typo in the file and
# not a problem with the service being probed.
SHAPES = ("json_array", "json_object", "html", "text")

# The loop only ever observes. Allowing anything but GET would let a probe
# create or delete data in a service the developer did not intend to touch.
ALLOWED_METHOD = "GET"

# Used when services.yml does not name a model. The roles are not
# interchangeable: the small one writes, the large one judges.
DEFAULT_IMPLEMENTATION_MODEL = "qwen2.5:0.5b"
DEFAULT_REVIEW_MODEL = "llama3.1:8b"


class ConfigError(RuntimeError):
    pass


@dataclass
class Endpoint:
    service: str
    name: str
    url: str
    expect: str
    records_at: str = ""
    required_fields: list = field(default_factory=list)
    identifier: str = ""
    notes: str = ""

    @property
    def ref(self):
        """How an endpoint is named everywhere else, including to the models."""
        return f"{self.service}/{self.name}"


@dataclass
class Service:
    name: str
    description: str
    endpoints: list


@dataclass
class ModelSettings:
    host: str
    implementation_model: str
    review_model: str
    context_tokens: int
    reply_tokens: int
    temperature: float
    timeout_seconds: int


@dataclass
class LoopSettings:
    max_iterations: int
    endpoints_per_iteration: int
    request_timeout_seconds: int
    slow_response_ms: int
    max_records: int


@dataclass
class Config:
    models: ModelSettings
    loop: LoopSettings
    services: list

    @property
    def endpoints(self):
        return [endpoint for service in self.services for endpoint in service.endpoints]

    def endpoint(self, ref):
        for endpoint in self.endpoints:
            if endpoint.ref == ref:
                return endpoint

        return None

    def describe_service(self, name):
        for service in self.services:
            if service.name == name:
                return service.description

        return ""


def _require_mapping(value, where):
    if not isinstance(value, dict):
        raise ConfigError(f"{where} must be a mapping, got {type(value).__name__}.")

    return value


def _string_list(value, where):
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{where} must be a list of strings.")

    return value


def _model_settings(raw):
    section = _require_mapping(raw.get("ollama") or {}, "ollama")

    # The compose file sets these so a containerised run can reach the host,
    # without the developer having to keep two copies of the config in step.
    host = os.getenv("OLLAMA_URL") or section.get("host") or "http://localhost:11434"

    # Defaulted rather than required, because the loop runs without models at
    # all under --offline and a missing model name should not stop the checks.
    implementation = (
        os.getenv("IMPLEMENTATION_MODEL")
        or section.get("implementation_model")
        or DEFAULT_IMPLEMENTATION_MODEL
    )
    review = os.getenv("REVIEW_MODEL") or section.get("review_model") or DEFAULT_REVIEW_MODEL

    return ModelSettings(
        host=host.rstrip("/"),
        implementation_model=implementation,
        review_model=review,
        context_tokens=int(section.get("context_tokens", 8192)),
        reply_tokens=int(section.get("reply_tokens", 600)),
        temperature=float(section.get("temperature", 0.2)),
        timeout_seconds=int(section.get("timeout_seconds", 180)),
    )


def _loop_settings(raw):
    section = _require_mapping(raw.get("loop") or {}, "loop")

    settings = LoopSettings(
        max_iterations=int(section.get("max_iterations", 3)),
        endpoints_per_iteration=int(section.get("endpoints_per_iteration", 4)),
        request_timeout_seconds=int(section.get("request_timeout_seconds", 10)),
        slow_response_ms=int(section.get("slow_response_ms", 1500)),
        max_records=int(section.get("max_records", 500)),
    )
    if settings.max_iterations < 1:
        raise ConfigError("loop.max_iterations must be at least 1.")
    if settings.endpoints_per_iteration < 1:
        raise ConfigError("loop.endpoints_per_iteration must be at least 1.")

    return settings


def _endpoint(service_name, raw, seen):
    where = f"services.{service_name}.endpoints"
    entry = _require_mapping(raw, where)

    name = entry.get("name")
    url = entry.get("url")
    if not name or not url:
        raise ConfigError(f"Every entry under {where} needs a name and a url.")

    method = str(entry.get("method", ALLOWED_METHOD)).upper()
    if method != ALLOWED_METHOD:
        raise ConfigError(
            f"{where}.{name} uses {method}. The loop only observes, so endpoints "
            f"must be {ALLOWED_METHOD}."
        )

    expect = entry.get("expect", "json_array")
    if expect not in SHAPES:
        raise ConfigError(f"{where}.{name}.expect must be one of {', '.join(SHAPES)}.")

    ref = f"{service_name}/{name}"
    if ref in seen:
        raise ConfigError(f"Two endpoints are both named {ref}; names must be unique.")
    seen.add(ref)

    return Endpoint(
        service=service_name,
        name=name,
        url=url,
        expect=expect,
        records_at=entry.get("records_at") or "",
        required_fields=_string_list(entry.get("required_fields"), f"{where}.{name}.required_fields"),
        identifier=entry.get("identifier") or "",
        notes=(entry.get("notes") or "").strip(),
    )


def _services(raw):
    entries = raw.get("services")
    if not isinstance(entries, list) or not entries:
        raise ConfigError("services must be a non empty list.")

    seen = set()
    services = []
    for entry in entries:
        service = _require_mapping(entry, "services")
        name = service.get("name")
        if not name:
            raise ConfigError("Every service needs a name.")

        endpoints = service.get("endpoints")
        if not isinstance(endpoints, list) or not endpoints:
            raise ConfigError(f"Service {name} needs at least one endpoint.")

        services.append(
            Service(
                name=name,
                description=(service.get("description") or "").strip(),
                endpoints=[_endpoint(name, item, seen) for item in endpoints],
            )
        )

    return services


def load_config(path=None):
    path = Path(path or os.getenv("SERVICES_CONFIG") or DEFAULT_CONFIG_PATH)
    try:
        document = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"{path} could not be read.") from exc

    try:
        raw = yaml.safe_load(document)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from exc

    raw = _require_mapping(raw or {}, str(path))

    # Services first: an endpoint is what a developer is most likely to mistype,
    # so that error should be the one they see.
    services = _services(raw)

    return Config(models=_model_settings(raw), loop=_loop_settings(raw), services=services)
