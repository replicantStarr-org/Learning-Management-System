import asyncio
import json
import os
from pathlib import Path
from typing import Any, Awaitable, Callable
from uuid import uuid4

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from config.review_config import ServiceConfig


DEFAULT_MCP_URL = "http://127.0.0.1:8000/mcp"
SUBJECT_TOOL_NAMES = {
    "subjects_list",
    "subjects_query_by_tag",
    "subjects_query_by_field",
    "subjects_get",
    "subjects_create",
    "subjects_update",
    "subjects_delete",
    "subjects_tags_list",
    "subjects_tag_get",
    "subjects_tag_create",
    "subjects_tag_update",
    "subjects_tag_delete",
    "subjects_subject_tags_list",
    "subjects_subject_tags_set",
    "subjects_subject_tag_remove",
}
RESOURCE_TOOL_NAMES = {
    "learning_resources_list",
    "learning_resources_tags_list",
    "learning_resources_by_tag",
}


async def _call(session: ClientSession, name: str, arguments: dict[str, Any] | None = None) -> Any:
    result = await session.call_tool(name, arguments or {})
    if result.is_error:
        text = "; ".join(
            item.text for item in result.content if hasattr(item, "text")
        )
        raise RuntimeError(f"{name} returned an MCP error: {text or 'unknown error'}")

    text = next(
        (item.text for item in result.content if hasattr(item, "text")),
        None,
    )
    if text is None:
        raise RuntimeError(f"{name} returned no text content")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{name} returned invalid JSON: {text!r}") from exc


async def _review_subjects(session: ClientSession, tool_names: set[str]) -> list[str]:
    """Exercise the subjects MCP tool set with a disposable CRUD fixture."""
    missing = sorted(SUBJECT_TOOL_NAMES - tool_names)
    if missing:
        raise RuntimeError("subjects tools missing from MCP server: " + ", ".join(missing))

    evidence: list[str] = [
        f"subjects tools advertised: {len(SUBJECT_TOOL_NAMES)}"
    ]
    subjects = await _call(session, "subjects_list")
    if not isinstance(subjects, list):
        raise RuntimeError("subjects_list did not return a JSON list")
    evidence.append(f"subjects_list returned {len(subjects)} subject(s)")

    subject_id: int | None = None
    tag_id: int | None = None
    subject_deleted = False
    tag_deleted = False
    fixture = uuid4().hex[:10]

    try:
        created = await _call(
            session,
            "subjects_create",
            {
                "code": f"MCP{fixture}",
                "name": "Agentic MCP Review Subject",
                "description": "Disposable fixture created by the MCP collector.",
                "semester": "Review",
                "coordinator": "Agentic Loop",
                "status": "Open",
            },
        )
        subject_id = created.get("subject_id") if isinstance(created, dict) else None
        if not isinstance(subject_id, int):
            raise RuntimeError("subjects_create did not return a subject_id")
        evidence.append(f"subjects_create returned subject_id={subject_id}")

        updated = await _call(
            session,
            "subjects_update",
            {"subject_id": subject_id, "name": "Updated MCP Review Subject"},
        )
        if updated.get("name") != "Updated MCP Review Subject":
            raise RuntimeError("subjects_update did not return the updated name")
        evidence.append("subjects_update passed")

        fetched = await _call(session, "subjects_get", {"subject_id": subject_id})
        if fetched.get("subject_id") != subject_id:
            raise RuntimeError("subjects_get returned the wrong subject")
        evidence.append("subjects_get passed")

        subject_tags = await _call(
            session, "subjects_subject_tags_list", {"subject_id": subject_id}
        )
        if not isinstance(subject_tags, list):
            raise RuntimeError("subjects_subject_tags_list did not return a JSON list")
        evidence.append("subjects_subject_tags_list passed")

        tag = await _call(
            session,
            "subjects_tag_create",
            {"name": f"Agentic MCP Review {fixture}"},
        )
        tag_id = tag.get("tag_id") if isinstance(tag, dict) else None
        if not isinstance(tag_id, int):
            raise RuntimeError("subjects_tag_create did not return a tag_id")
        evidence.append(f"subjects_tag_create returned tag_id={tag_id}")

        tag = await _call(session, "subjects_tag_get", {"tag_id": tag_id})
        if tag.get("tag_id") != tag_id:
            raise RuntimeError("subjects_tag_get returned the wrong tag")
        evidence.append("subjects_tag_get passed")

        assigned = await _call(
            session,
            "subjects_subject_tags_set",
            {"subject_id": subject_id, "tag_ids": [tag_id]},
        )
        if not any(item.get("tag_id") == tag_id for item in assigned):
            raise RuntimeError("subjects_subject_tags_set did not assign the tag")
        evidence.append("subjects_subject_tags_set passed")

        by_tag = await _call(
            session,
            "subjects_query_by_tag",
            {"tag": f"Agentic MCP Review {fixture}"},
        )
        if not any(item.get("subject_id") == subject_id for item in by_tag):
            raise RuntimeError("subjects_query_by_tag did not find the assigned subject")
        evidence.append("subjects_query_by_tag passed")

        by_field = await _call(
            session,
            "subjects_query_by_field",
            {"field": "code", "value": f"MCP{fixture}"},
        )
        if not any(item.get("subject_id") == subject_id for item in by_field):
            raise RuntimeError("subjects_query_by_field did not find the created subject")
        evidence.append("subjects_query_by_field passed")

        listed_tags = await _call(session, "subjects_tags_list")
        if not any(item.get("tag_id") == tag_id for item in listed_tags):
            raise RuntimeError("subjects_tags_list did not include the created tag")
        evidence.append("subjects_tags_list passed")

        await _call(
            session,
            "subjects_subject_tag_remove",
            {"subject_id": subject_id, "tag_id": tag_id},
        )
        evidence.append("subjects_subject_tag_remove passed")

        await _call(session, "subjects_tag_update", {"tag_id": tag_id, "name": f"Updated MCP Review {fixture}"})
        evidence.append("subjects_tag_update passed")

        await _call(session, "subjects_delete", {"subject_id": subject_id})
        subject_deleted = True
        evidence.append("subjects_delete passed")

        await _call(session, "subjects_tag_delete", {"tag_id": tag_id})
        tag_deleted = True
        evidence.append("subjects_tag_delete passed")
    finally:
        cleanup_errors: list[str] = []
        if subject_id is not None and not subject_deleted:
            try:
                await _call(session, "subjects_delete", {"subject_id": subject_id})
            except Exception as exc:  # cleanup must not hide the review failure
                cleanup_errors.append(f"subject cleanup failed: {exc}")
        if tag_id is not None and not tag_deleted:
            try:
                await _call(session, "subjects_tag_delete", {"tag_id": tag_id})
            except Exception as exc:
                cleanup_errors.append(f"tag cleanup failed: {exc}")
        if cleanup_errors:
            raise RuntimeError("; ".join(cleanup_errors))

    return evidence


async def _review_resources(session: ClientSession, tool_names: set[str]) -> list[str]:
    """Cross-check the read-only learning resource tools against each other.

    The tools only read, so there is no fixture to create or clean up: the
    library's own resources and tags are the test data.
    """
    missing = sorted(RESOURCE_TOOL_NAMES - tool_names)
    if missing:
        raise RuntimeError("learning resource tools missing from MCP server: " + ", ".join(missing))

    evidence: list[str] = [
        f"learning resource tools advertised: {len(RESOURCE_TOOL_NAMES)}; all read-only, "
        "so no CRUD fixture is created"
    ]

    resources = await _call(session, "learning_resources_list")
    if not isinstance(resources, list) or not resources:
        raise RuntimeError("learning_resources_list did not return a non-empty JSON list")
    evidence.append(f"learning_resources_list returned {len(resources)} resource(s)")

    tags = await _call(session, "learning_resources_tags_list")
    tag_names = {tag["name"] for tag in tags}
    carried = {name for resource in resources for name in resource["tags"]}
    if carried - tag_names:
        raise RuntimeError(
            "tags on resources missing from learning_resources_tags_list: "
            + ", ".join(sorted(carried - tag_names))
        )
    evidence.append(f"learning_resources_tags_list returned {len(tags)} tag(s), including every tag a resource carries")

    # The most used tag, so the check covers as many resources as it can.
    tag = max(sorted(carried), key=lambda name: sum(name in r["tags"] for r in resources))
    expected = {r["l_resource_id"] for r in resources if tag in r["tags"]}
    for query in (tag, f"  {tag.upper()} "):
        found = {r["l_resource_id"] for r in await _call(session, "learning_resources_by_tag", {"tag": query})}
        if found != expected:
            raise RuntimeError(f"learning_resources_by_tag({query!r}) did not match learning_resources_list")
    evidence.append(
        f"learning_resources_by_tag({tag!r}) returned the same {len(expected)} resource(s) as "
        "learning_resources_list, ignoring case and surrounding spaces"
    )

    if await _call(session, "learning_resources_by_tag", {"tag": f"No Such Tag {uuid4().hex[:10]}"}) != []:
        raise RuntimeError("learning_resources_by_tag did not return [] for an unknown tag")
    evidence.append("learning_resources_by_tag returns [] for an unknown tag")

    blank = await session.call_tool("learning_resources_by_tag", {"tag": "   "})
    if not blank.is_error:
        raise RuntimeError("learning_resources_by_tag accepted a blank tag")
    evidence.append("learning_resources_by_tag rejects a blank tag with an MCP error")

    # The contracts clients see, so the models have more than passing calls to
    # review. The shared server lists every service's tools; only these are ours.
    for tool in sorted((await session.list_tools()).tools, key=lambda tool: tool.name):
        if tool.name in RESOURCE_TOOL_NAMES:
            output = list((tool.output_schema or {}).get("properties", {}))
            evidence.append(
                f"{tool.name} contract: output schema fields {output or 'none'}, "
                f"annotations {'none' if tool.annotations is None else tool.annotations}"
            )

    return evidence


SERVICE_REVIEWS: dict[str, Callable[[ClientSession, set[str]], Awaitable[list[str]]]] = {
    "subjects": _review_subjects,
    "resources": _review_resources,
}


async def _probe(url: str, service: ServiceConfig) -> tuple[list[str], list[str]]:
    async with streamable_http_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            names = {tool.name for tool in listed.tools}

            review = SERVICE_REVIEWS.get(service.key)
            if review is None:
                raise RuntimeError(
                    f"no MCP tool review is registered for service '{service.key}'"
                )
            evidence = await review(session, names)
            return sorted(names), evidence


def collect(repo_root: Path, service: ServiceConfig | None) -> tuple[bool, str]:
    server_dir = repo_root / "mcp"
    if not server_dir.is_dir():
        return False, f"MCP server directory is missing: {server_dir}"
    if service is None:
        return False, "A service is required for an MCP review."

    url = os.getenv("MCP_SERVER_URL", DEFAULT_MCP_URL).rstrip("/")
    try:
        names, evidence = asyncio.run(
            asyncio.wait_for(_probe(url, service), timeout=30.0)
        )
    except Exception as exc:
        return False, (
            f"MCP server/tool review failed at {url} for {service.key}. "
            f"Start ../mcp and the selected service before running the review. "
            f"({type(exc).__name__}: {exc})"
        )

    return True, (
        f"MCP endpoint: {url}\n"
        f"Service area: {service.key}\n"
        f"Tools listed by the running server: {', '.join(names) or '(none)'}\n"
        "Validation evidence:\n- " + "\n- ".join(evidence)
    )
