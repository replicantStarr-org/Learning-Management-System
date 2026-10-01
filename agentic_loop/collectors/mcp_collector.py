import asyncio
import json
import os
from pathlib import Path
from typing import Any, Awaitable, Callable
from uuid import uuid4

import requests

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
TIMETABLE_TOOL_NAMES = {
    "timetable_users_list",
    "timetable_entries_list",
    "timetable_entry_get",
    "timetable_free_time",
}
QUIZ_TOOL_NAMES = {
    "quizzes_list",
    "quizzes_get",
    "quizzes_search_questions",
    "quizzes_practice_question",
}
ASSIGNMENT_TOOL_NAMES = {
    "assignments_list",
    "assignments_upcoming",
    "assignments_get",
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


async def _review_timetable(session: ClientSession, tool_names: set[str]) -> list[str]:
    """Cross-check the read-only timetable tools against each other.

    The tools only read, so the seed entries are the test data and nothing is
    created or cleaned up.
    """
    missing = sorted(TIMETABLE_TOOL_NAMES - tool_names)
    if missing:
        raise RuntimeError("timetable tools missing from MCP server: " + ", ".join(missing))
    writes = sorted(
        name for name in tool_names
        if name.startswith("timetable_") and name not in TIMETABLE_TOOL_NAMES
    )
    if writes:
        raise RuntimeError("unexpected timetable tools beyond the read-only set: " + ", ".join(writes))

    evidence: list[str] = [
        f"timetable tools advertised: {len(TIMETABLE_TOOL_NAMES)}; all read-only, "
        "so no fixture is created"
    ]

    users = await _call(session, "timetable_users_list")
    if not isinstance(users, list) or not users:
        raise RuntimeError("timetable_users_list did not return a non-empty JSON list")
    evidence.append(f"timetable_users_list returned {len(users)} username(s)")

    weeks = [await _call(session, "timetable_entries_list", {"username": user}) for user in users]
    week = max(weeks, key=lambda week: len(week["entries"]))
    entries = week["entries"]
    if not entries:
        raise RuntimeError("timetable_entries_list returned no entries this week for any user")
    if any(
        entry["username"] != week["username"]
        or not week["week_start"] <= entry["date"] <= week["week_end"]
        for entry in entries
    ):
        raise RuntimeError("timetable_entries_list returned an entry outside its user or week")
    evidence.append(
        f"timetable_entries_list({week['username']!r}) returned {len(entries)} entries, "
        f"all theirs and within {week['week_start']} to {week['week_end']}"
    )

    entry = entries[0]
    if await _call(session, "timetable_entry_get", {"timetable_id": entry["timetable_id"]}) != entry:
        raise RuntimeError("timetable_entry_get did not match the entry timetable_entries_list returned")
    evidence.append(f"timetable_entry_get({entry['timetable_id']}) matched timetable_entries_list")

    day = await _call(
        session, "timetable_free_time", {"username": week["username"], "on_date": entry["date"]}
    )
    busy = [(b["start_time"], b["end_time"]) for b in day["busy"]]
    timed = [
        (e["start_time"], e["end_time"])
        for e in entries
        if e["date"] == entry["date"] and not e["all_day"]
    ]
    if sorted(busy) != sorted(timed):
        raise RuntimeError("timetable_free_time's busy list did not match that day's entries")
    if any(f["start"] < end and start < f["end"] for f in day["free"] for start, end in busy):
        raise RuntimeError("timetable_free_time returned free time that overlaps an entry")
    evidence.append(
        f"timetable_free_time on {entry['date']} found {len(day['free'])} free gap(s) "
        f"({day['free_minutes']} minutes), none overlapping that day's {len(busy)} entries"
    )

    refused = {
        "unknown username": ("timetable_entries_list", {"username": f"no.such.user.{uuid4().hex[:6]}"}),
        "malformed date": ("timetable_free_time", {"username": week["username"], "on_date": "next monday"}),
        "non-positive id": ("timetable_entry_get", {"timetable_id": 0}),
        "missing entry": ("timetable_entry_get", {"timetable_id": 999999}),
    }
    for label, (name, arguments) in refused.items():
        if not (await session.call_tool(name, arguments)).is_error:
            raise RuntimeError(f"{name} accepted a {label}")
    evidence.append("tools reject " + ", ".join(refused) + " with an MCP error")

    for tool in sorted((await session.list_tools()).tools, key=lambda tool: tool.name):
        if tool.name in TIMETABLE_TOOL_NAMES:
            inputs = list((tool.input_schema or {}).get("properties", {}))
            evidence.append(f"{tool.name} contract: inputs {inputs or 'none'}")

    return evidence


async def _review_quizzes(session: ClientSession, tool_names: set[str]) -> list[str]:
    """Cross-check the read-only quiz study tools against each other.

    The tools only read, so the seed quizzes are the test data and nothing is
    created or cleaned up.
    """
    missing = sorted(QUIZ_TOOL_NAMES - tool_names)
    if missing:
        raise RuntimeError("quiz tools missing from MCP server: " + ", ".join(missing))
    writes = sorted(
        name for name in tool_names
        if name.startswith("quizzes_") and name not in QUIZ_TOOL_NAMES
    )
    if writes:
        raise RuntimeError("unexpected quiz tools beyond the read-only set: " + ", ".join(writes))

    evidence: list[str] = [
        f"quiz tools advertised: {len(QUIZ_TOOL_NAMES)}; all read-only, so no fixture is created"
    ]

    quizzes = await _call(session, "quizzes_list")
    if not isinstance(quizzes, list) or not quizzes:
        raise RuntimeError("quizzes_list did not return a non-empty JSON list")
    evidence.append(f"quizzes_list returned {len(quizzes)} quiz(zes)")

    for difficulty in ("Easy", "Medium", "Hard"):
        filtered = await _call(session, "quizzes_list", {"difficulty": difficulty})
        expected = [q["quiz_id"] for q in quizzes if q["difficulty"] == difficulty]
        if [q["quiz_id"] for q in filtered] != expected:
            raise RuntimeError(f"quizzes_list(difficulty={difficulty!r}) did not match the full list")
    evidence.append("quizzes_list difficulty filters match the unfiltered list for Easy, Medium and Hard")

    quiz = await _call(session, "quizzes_get", {"quiz_id": quizzes[0]["quiz_id"]})
    if len(quiz["questions"]) != quizzes[0]["question_count"]:
        raise RuntimeError("quizzes_get question count does not match quizzes_list")
    if any(not q["correct_answer"] or q["correct_answer"] not in q["answers"] for q in quiz["questions"]):
        raise RuntimeError("quizzes_get returned a question whose correct answer is not one of its options")
    evidence.append(
        f"quizzes_get({quiz['quiz_id']}) returned {len(quiz['questions'])} questions, "
        "each with its correct answer among the options"
    )

    for difficulty in ("Easy", "Hard"):
        practice = await _call(session, "quizzes_practice_question", {"difficulty": difficulty})
        if practice["difficulty"] != difficulty or practice["correct_answer"] not in practice["answers"]:
            raise RuntimeError(f"quizzes_practice_question(difficulty={difficulty!r}) returned a bad question")
    evidence.append(
        "quizzes_practice_question honours its difficulty filter and returns a correct answer among the options"
    )

    # A self-study tool: no tool may reveal other students' attempts or scores.
    results = [quizzes, quiz, practice]
    leaked = {
        key for key in ("attempt_id", "student_name", "score", "ai_feedback")
        if f'"{key}"' in json.dumps(results)
    }
    if leaked:
        raise RuntimeError("quiz tools returned student data: " + ", ".join(sorted(leaked)))
    evidence.append("no tool returns attempts, student names, scores or AI feedback")

    keyword = quiz["questions"][0]["question_text"].split()[-1].strip("?.,'")
    found = await _call(session, "quizzes_search_questions", {"keyword": keyword})
    if not any(m["question_id"] == quiz["questions"][0]["question_id"] for m in found["matches"]):
        raise RuntimeError(f"quizzes_search_questions({keyword!r}) did not find the question it came from")
    evidence.append(f"quizzes_search_questions({keyword!r}) found the question the keyword came from")
    relevance = [m["relevance"] for m in found["matches"]]
    if relevance != sorted(relevance, reverse=True):
        raise RuntimeError("quizzes_search_questions did not rank matches by relevance")
    evidence.append("quizzes_search_questions ranks matches by relevance, best first")

    # The quiz keywords broaden the search: a keyword that none of its quiz's
    # questions spells out must still find that quiz's questions. The tools keep
    # the keywords internal, so they are read from the quiz database API.
    text = json.dumps(quiz["questions"]).lower()
    database_url = os.getenv("QUIZZES_DATABASE_API_URL", "http://127.0.0.1:6004").rstrip("/")
    try:
        response = await asyncio.to_thread(
            requests.get, f"{database_url}/quizzes/{quiz['quiz_id']}", timeout=10
        )
        keywords = response.json().get("keywords", []) if response.ok else []
    except (requests.RequestException, ValueError):
        keywords = []
    unspoken = next((k["keyword"] for k in keywords if k["keyword"].lower() not in text), None)
    if unspoken is None:
        evidence.append(
            f"no keyword of quiz {quiz['quiz_id']} is absent from its questions, or the quiz database "
            "API was unreachable; keyword broadening not checked"
        )
    else:
        broadened = await _call(session, "quizzes_search_questions", {"keyword": unspoken})
        if not any(m["quiz_id"] == quiz["quiz_id"] for m in broadened["matches"]):
            raise RuntimeError(f"quizzes_search_questions({unspoken!r}) ignored quiz {quiz['quiz_id']}'s keywords")
        evidence.append(
            f"quizzes_search_questions({unspoken!r}) finds quiz {quiz['quiz_id']} through its keywords, "
            "though no question mentions it"
        )
        typo = unspoken[:-2] + unspoken[-1]  # drop a letter: "software developmet"
        misspelt = await _call(session, "quizzes_search_questions", {"keyword": typo})
        if not any(m["quiz_id"] == quiz["quiz_id"] for m in misspelt["matches"]):
            raise RuntimeError(f"quizzes_search_questions({typo!r}) did not forgive the typo")
        evidence.append(f"quizzes_search_questions({typo!r}) forgives the typo and still finds quiz {quiz['quiz_id']}")

    if any("keywords" in result for result in (quizzes[0], quiz)):
        raise RuntimeError("quizzes_list or quizzes_get exposes the internal quiz keywords")
    evidence.append("quizzes_list and quizzes_get keep the quiz keywords internal")

    refused = {
        "non-positive id": ("quizzes_get", {"quiz_id": 0}),
        "missing quiz": ("quizzes_get", {"quiz_id": 999999}),
        "unknown difficulty": ("quizzes_list", {"difficulty": "Impossible"}),
        "subject with no quizzes": ("quizzes_practice_question", {"subject": f"No Such Subject {uuid4().hex[:6]}"}),
        "blank keyword": ("quizzes_search_questions", {"keyword": "   "}),
    }
    for label, (name, arguments) in refused.items():
        if not (await session.call_tool(name, arguments)).is_error:
            raise RuntimeError(f"{name} accepted a {label}")
    evidence.append("tools reject " + ", ".join(refused) + " with an MCP error")

    for tool in sorted((await session.list_tools()).tools, key=lambda tool: tool.name):
        if tool.name in QUIZ_TOOL_NAMES:
            inputs = list((tool.input_schema or {}).get("properties", {}))
            evidence.append(f"{tool.name} contract: inputs {inputs or 'none'}")

    return evidence


async def _review_assignments(session: ClientSession, tool_names: set[str]) -> list[str]:
    missing = sorted(ASSIGNMENT_TOOL_NAMES - tool_names)
    if missing:
        raise RuntimeError("assignment tools missing from MCP server: " + ", ".join(missing))
    
    listed = await _call(session, "assignments_list")

    if not isinstance(listed, list):
        raise RuntimeError("assignments_list did not return a JSON list")
    
    upcoming = await _call(session, "assignments_upcoming", {"days": 365})

    if not isinstance(upcoming, list):
        raise RuntimeError("assignments_upcoming did not return a JSON list")
    
    evidence = [f"assignment tools advertised: {len(ASSIGNMENT_TOOL_NAMES)}"]
    evidence.append(f"assignments_list returned {len(listed)} assignment(s)")
    evidence.append(f"assignments_upcoming returned {len(upcoming)} assignment(s) within 365 days")

    if listed:
        assignment_id = listed[0].get("assignment_id")
        if not isinstance(assignment_id, int):
            raise RuntimeError("assignments_list returned an invalid assignment_id")
        detail = await _call(session, "assignments_get", {"assignment_id": assignment_id})
        if detail.get("assignment_id") != assignment_id:
            raise RuntimeError("assignments_get returned the wrong assignment")
        evidence.append(f"assignments_get({assignment_id}) passed")

    for name, arguments in (("assignments_get", {"assignment_id": 0}), ("assignments_upcoming", {"days": 0})):
        if not (await session.call_tool(name, arguments)).is_error:
            raise RuntimeError(f"{name} accepted invalid arguments")
        
    evidence.append("assignment tools reject non-positive IDs and day ranges")
    return evidence


SERVICE_REVIEWS: dict[str, Callable[[ClientSession, set[str]], Awaitable[list[str]]]] = {
    "subjects": _review_subjects,
    "resources": _review_resources,
    "timetable": _review_timetable,
    "quizzes": _review_quizzes,
    "assignments": _review_assignments,
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
