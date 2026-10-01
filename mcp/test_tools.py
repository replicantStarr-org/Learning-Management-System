#!/usr/bin/env python3
"""Smoke-test the tools registered by the LMS MCP server.

The MCP server itself does not need to be running: tools are invoked through its
in-process MCP dispatcher. The backing service containers do need to be up.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from collections.abc import Callable
from datetime import date
from typing import Any

from server import mcp


SERVICE_ALIASES = {
    "subjects": "subjects",
    "subject": "subjects",
    "learning_resources": "learning_resources",
    "learning-resources": "learning_resources",
    "learning-resource-manager": "learning_resources",
    "learning_resource_manager": "learning_resources",
    "resources": "learning_resources",
    "timetable": "timetable",
    "timetables": "timetable",
    "quizzes": "quizzes",
    "quiz": "quizzes",
}


class ToolTester:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.attempted: set[str] = set()

    async def call(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        check: Callable[[Any], bool] | None = None,
    ) -> Any | None:
        """Call one tool, print its JSON result, and record pass/fail."""
        self.attempted.add(name)
        try:
            result = await mcp.call_tool(name, arguments or {})
            if result.is_error:
                raise RuntimeError("; ".join(part.text for part in result.content))
            if not result.content or not hasattr(result.content[0], "text"):
                raise RuntimeError("tool returned no text content")

            text = result.content[0].text
            value = json.loads(text)
            if check is not None and not check(value):
                raise AssertionError(f"unexpected result shape: {text}")

            print(f"PASS {name}: {json.dumps(value, ensure_ascii=False)}")
            self.passed += 1
            return value
        except Exception as exc:  # Keep going so every selected tool is exercised.
            print(f"FAIL {name}: {exc}", file=sys.stderr)
            self.failed += 1
            return None

    async def cleanup(self, name: str, arguments: dict[str, Any]) -> None:
        """Best-effort cleanup after an interrupted CRUD test."""
        try:
            await mcp.call_tool(name, arguments)
        except Exception:
            pass


async def test_learning_resources(tester: ToolTester) -> None:
    resources = await tester.call(
        "learning_resources_list", check=lambda value: isinstance(value, list)
    )
    tags = await tester.call(
        "learning_resources_tags_list", check=lambda value: isinstance(value, list)
    )

    # Prefer a real tag, but still exercise the tool when the catalogue is empty.
    tag = "__mcp_smoke_test_missing_tag__"
    if isinstance(tags, list) and tags:
        first = tags[0]
        if isinstance(first, dict) and isinstance(first.get("name"), str):
            tag = first["name"]
    elif isinstance(resources, list):
        for resource in resources:
            if isinstance(resource, dict) and resource.get("tags"):
                tag = resource["tags"][0]
                break

    await tester.call(
        "learning_resources_by_tag",
        {"tag": tag},
        check=lambda value: isinstance(value, list),
    )


async def test_timetable(tester: ToolTester) -> None:
    users = await tester.call(
        "timetable_users_list", check=lambda value: isinstance(value, list)
    )
    username = users[0] if users else "__mcp_smoke_test_missing_user__"

    week = await tester.call(
        "timetable_entries_list",
        {"username": username},
        check=lambda value: isinstance(value, dict)
        and isinstance(value.get("entries"), list),
    )
    entries = week["entries"] if week else []
    entry = entries[0] if entries else {"timetable_id": 1, "date": date.today().isoformat()}

    await tester.call(
        "timetable_entry_get",
        {"timetable_id": entry["timetable_id"]},
        check=lambda value: isinstance(value, dict)
        and value.get("timetable_id") == entry["timetable_id"],
    )
    await tester.call(
        "timetable_free_time",
        {"username": username, "on_date": entry["date"]},
        check=lambda value: isinstance(value, dict)
        and isinstance(value.get("free"), list),
    )


async def test_quizzes(tester: ToolTester) -> None:
    is_list = lambda value: isinstance(value, list)
    quizzes = await tester.call("quizzes_list", check=is_list)
    await tester.call("quizzes_list", {"difficulty": "Easy"}, check=is_list)
    quiz_id = quizzes[0]["quiz_id"] if quizzes else 1

    await tester.call(
        "quizzes_get",
        {"quiz_id": quiz_id},
        check=lambda value: isinstance(value, dict)
        and value.get("quiz_id") == quiz_id
        and isinstance(value.get("questions"), list),
    )
    await tester.call(
        "quizzes_practice_question",
        {"difficulty": "Easy"},
        check=lambda value: isinstance(value, dict)
        and value.get("difficulty") == "Easy"
        and value.get("correct_answer") in value.get("answers", []),
    )
    await tester.call(
        "quizzes_search_questions",
        {"keyword": "primary key"},
        check=lambda value: isinstance(value, dict)
        and isinstance(value.get("matches"), list),
    )


async def test_subjects(tester: ToolTester) -> None:
    token = uuid.uuid4().hex[:8]
    code = f"MCP{token}".upper()
    tag_name = f"MCP smoke {token}"
    updated_tag_name = f"MCP checked {token}"
    subject_id: int | None = None
    tag_id: int | None = None
    subject_deleted = False
    tag_deleted = False

    is_list = lambda value: isinstance(value, list)
    is_dict = lambda value: isinstance(value, dict)

    try:
        await tester.call("subjects_list", check=is_list)
        await tester.call("subjects_tags_list", check=is_list)

        subject = await tester.call(
            "subjects_create",
            {
                "code": code,
                "name": f"MCP smoke test {token}",
                "description": "Temporary subject created by test_tools.py",
                "semester": "Test semester",
                "coordinator": "MCP smoke test",
                "status": "Test",
            },
            check=lambda value: is_dict(value)
            and isinstance(value.get("subject_id"), int),
        )
        if isinstance(subject, dict) and isinstance(subject.get("subject_id"), int):
            subject_id = subject["subject_id"]

        # -1 lets the remaining tools be invoked and reported even if creation failed.
        sid = subject_id if subject_id is not None else -1
        await tester.call("subjects_get", {"subject_id": sid}, check=is_dict)
        await tester.call(
            "subjects_update",
            {"subject_id": sid, "description": "Updated by the MCP smoke test"},
            check=is_dict,
        )

        tag = await tester.call(
            "subjects_tag_create",
            {"name": tag_name},
            check=lambda value: is_dict(value) and isinstance(value.get("tag_id"), int),
        )
        if isinstance(tag, dict) and isinstance(tag.get("tag_id"), int):
            tag_id = tag["tag_id"]
        tid = tag_id if tag_id is not None else -1

        await tester.call("subjects_tag_get", {"tag_id": tid}, check=is_dict)
        await tester.call(
            "subjects_tag_update",
            {"tag_id": tid, "name": updated_tag_name},
            check=is_dict,
        )
        await tester.call(
            "subjects_subject_tags_set",
            {"subject_id": sid, "tag_ids": [tid]},
            check=is_list,
        )
        await tester.call(
            "subjects_subject_tags_list", {"subject_id": sid}, check=is_list
        )
        await tester.call(
            "subjects_query_by_tag", {"tag": updated_tag_name}, check=is_list
        )
        await tester.call(
            "subjects_query_by_field",
            {"field": "code", "value": code},
            check=is_list,
        )
        await tester.call(
            "subjects_subject_tag_remove",
            {"subject_id": sid, "tag_id": tid},
            check=is_dict,
        )

        deleted_tag = await tester.call(
            "subjects_tag_delete", {"tag_id": tid}, check=is_dict
        )
        tag_deleted = deleted_tag is not None
        deleted_subject = await tester.call(
            "subjects_delete", {"subject_id": sid}, check=is_dict
        )
        subject_deleted = deleted_subject is not None
    finally:
        if tag_id is not None and not tag_deleted:
            await tester.cleanup("subjects_tag_delete", {"tag_id": tag_id})
        if subject_id is not None and not subject_deleted:
            await tester.cleanup("subjects_delete", {"subject_id": subject_id})


async def async_main(service: str | None) -> int:
    selected = (
        {SERVICE_ALIASES[service]}
        if service is not None
        else {"subjects", "learning_resources", "timetable", "quizzes"}
    )
    tester = ToolTester()

    if "subjects" in selected:
        print("\n== subjects ==", flush=True)
        await test_subjects(tester)
    if "learning_resources" in selected:
        print("\n== learning_resources ==", flush=True)
        await test_learning_resources(tester)
    if "timetable" in selected:
        print("\n== timetable ==", flush=True)
        await test_timetable(tester)
    if "quizzes" in selected:
        print("\n== quizzes ==", flush=True)
        await test_quizzes(tester)

    registered = {tool.name for tool in await mcp.list_tools()}
    prefixes = tuple(f"{name}_" for name in selected)
    expected = (
        registered
        if service is None
        else {name for name in registered if name.startswith(prefixes)}
    )
    missing = expected - tester.attempted
    if missing:
        for name in sorted(missing):
            print(f"FAIL {name}: no smoke-test case defined", file=sys.stderr)
        tester.failed += len(missing)

    print(f"\nSummary: {tester.passed} passed, {tester.failed} failed")
    return 1 if tester.failed else 0


def main() -> int:
    # Windows consoles default to a legacy code page that cannot print some
    # seed data (such as the arrows in quiz questions).
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="Smoke-test all MCP tools, optionally scoped to one service.",
        epilog=(
            "Services: subjects, learning_resources, timetable, quizzes (aliases "
            "include subject, learning-resources, learning-resource-manager, "
            "resources, timetables, quiz). "
            "Backing containers must be running."
        ),
    )
    parser.add_argument(
        "service",
        nargs="?",
        type=str.lower,
        help="service whose tools should be tested (default: all services)",
    )
    args = parser.parse_args()
    if args.service is not None and args.service not in SERVICE_ALIASES:
        parser.error(
            f"unknown service {args.service!r}; "
            "choose subjects, learning_resources, timetable or quizzes"
        )
    return asyncio.run(async_main(args.service))


if __name__ == "__main__":
    raise SystemExit(main())
