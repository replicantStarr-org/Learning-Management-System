import tomllib
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.toml"
SERVICES_DIR = BASE_DIR / "services"


@dataclass(frozen=True)
class Source:
    entity: str
    label: str
    path: str
    id_field: str
    title: str
    detail: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    # Keys to keep, in display order, applied at every nesting depth.
    fields: list[str] | None = None


@dataclass(frozen=True)
class Service:
    name: str
    base_url: str
    sources: list[Source]


@cache
def settings() -> dict[str, Any]:
    with CONFIG_PATH.open("rb") as f:
        return tomllib.load(f)


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else BASE_DIR / path


@cache
def services() -> dict[str, Service]:
    """Every service in services/*.toml, keyed by name. Read once per process."""
    loaded: dict[str, Service] = {}
    for path in sorted(SERVICES_DIR.glob("*.toml")):
        with path.open("rb") as f:
            raw = tomllib.load(f)
        service = Service(
            name=raw["name"],
            base_url=raw["base_url"].rstrip("/"),
            sources=[Source(**source) for source in raw.get("sources", [])],
        )
        if service.name in loaded:
            raise ValueError(f"Duplicate service name {service.name!r} in {path.name}")
        loaded[service.name] = service
    return loaded
