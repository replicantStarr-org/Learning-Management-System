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


SERVICE_REVIEWS: dict[str, Callable[[ClientSession, set[str]], Awaitable[list[str]]]] = {
    "subjects": _review_subjects,
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
