"""The connector framework: how a service describes what to index.

The per-service connectors built with it live in pipeline/connectors/; see the
AGENTS.md there for how to write one.
"""

import importlib
import pkgutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import cache
from typing import Any

import requests

CONNECTORS_PACKAGE = f"{__package__}.connectors"
REQUEST_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class Record:
    """One thing to index, e.g. one quiz. `fields` is rendered in its own order."""

    entity: str
    id: str | int
    title: str
    fields: dict[str, Any]

    @property
    def label(self) -> str:
        return self.entity.replace("_", " ").capitalize()


Get = Callable[..., Any]
EntityFunction = Callable[[Get], Iterable[Record]]


class Connector:
    """One service: where its database API lives and a function per entity.

    Each module in pipeline/connectors/ creates one as `connector` and
    registers entity functions on it with @connector.entity. An entity function
    is given `get(path, **params)`, which returns the service's parsed JSON.
    """

    def __init__(self, name: str, base_url: str):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.entities: list[EntityFunction] = []

    def entity(self, function: EntityFunction) -> EntityFunction:
        self.entities.append(function)
        return function

    def get(self, path: str, **params: Any) -> Any:
        response = requests.get(self.base_url + path, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()

    def records(self) -> Iterable[Record]:
        for function in self.entities:
            yield from function(self.get)


def pick(row: dict[str, Any], *keys: str) -> dict[str, Any]:
    """The named keys of a row, in that order. A missing key raises, so a
    renamed column fails the ingest loudly instead of quietly vanishing."""
    return {key: row[key] for key in keys}


@cache
def connectors() -> dict[str, Connector]:
    """Every connector in pipeline/connectors/, keyed by service name."""
    package = importlib.import_module(CONNECTORS_PACKAGE)
    loaded: dict[str, Connector] = {}
    for module_info in pkgutil.iter_modules(package.__path__):
        module = importlib.import_module(f"{CONNECTORS_PACKAGE}.{module_info.name}")
        connector = getattr(module, "connector", None)
        if not isinstance(connector, Connector):
            raise TypeError(f"{module.__name__} must define `connector = Connector(...)`")
        if connector.name in loaded:
            raise ValueError(f"Duplicate service name {connector.name!r} in {module.__name__}")
        loaded[connector.name] = connector
    return loaded
