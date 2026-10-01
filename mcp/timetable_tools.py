"""
MCP tools for the timetable manager.

The tools call the timetable database API. The timetable backend's routes
return HTML fragments for its page, so the database API is the JSON view of
the same entries (the RAG connector reads it for the same reason).

Every tool is read-only: an MCP client can look at a timetable but never change
one, so the validation and clash rules that guard writes stay in the backend
and the page remains the only way to add, edit or delete an entry.
"""

import json
import os
from datetime import date, datetime, timedelta
from typing import Any

import requests
from mcp.server.mcpserver.exceptions import ToolError


DAY_START = "08:00"
DAY_END = "23:00"
MIN_FREE_MINUTES = 30


class TimetableApiError(ToolError):
    """An error returned by, or while reaching, the timetable database API.

    A ToolError, so the MCP SDK passes this message on to the caller rather
    than replacing it with a generic one.
    """


class TimetableApiClient:
    def __init__(self):
        self.base_url = os.getenv(
            "TIMETABLE_DATABASE_API_URL", "http://127.0.0.1:6005"
        ).rstrip("/")
        self.timeout = float(os.getenv("TIMETABLE_DATABASE_API_TIMEOUT_SECONDS", "10"))

    def request(self, path: str, **params: Any) -> Any:
        try:
            response = requests.get(
                f"{self.base_url}{path}", params=params, timeout=self.timeout
            )
        except requests.RequestException as exc:
            raise TimetableApiError(
                "The timetable service is unavailable. "
                "Make sure the timetable containers are running."
            ) from exc

        if not response.ok:
            try:
                message = response.json().get("error")
            except ValueError:
                message = None
            raise TimetableApiError(
                f"HTTP {response.status_code}: {message or 'timetable database request failed'}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise TimetableApiError(
                "The timetable service returned invalid JSON."
            ) from exc


def _username(value: str) -> str:
    username = value.strip()
    if not username:
        raise ToolError("A username is required.")
    return username


def _date(value: str, name: str) -> date:
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ToolError(f"{name} must be a date in YYYY-MM-DD format.") from None


def _minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def _hhmm(total_minutes: int) -> str:
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def register_timetable_tools(mcp):
    client = TimetableApiClient()

    def known_username(value: str) -> str:
        username = _username(value)
        if username not in client.request("/timetable/users"):
            raise ToolError(
                f"No timetable entries exist for {username!r}. "
                "Use timetable_users_list to see the usernames that have entries."
            )
        return username

    @mcp.tool(name="timetable_users_list")
    def timetable_users_list() -> str:
        """List the usernames that have at least one timetable entry, such as
        "alex.wong". Use one of these with the other timetable tools."""
        return json.dumps(client.request("/timetable/users"), ensure_ascii=False)

    @mcp.tool(name="timetable_entries_list")
    def timetable_entries_list(username: str, week_of: str | None = None) -> str:
        """List one student's timetable entries for a week, Monday to Sunday.

        week_of is any date in the week wanted, as YYYY-MM-DD; it defaults to
        the current week. Entries are ordered by date and start time. All-day
        entries are due dates imported from iCal, not time slots.
        """
        username = known_username(username)
        reference = _date(week_of, "week_of") if week_of else date.today()
        week_start = reference - timedelta(days=reference.weekday())
        week_end = week_start + timedelta(days=6)
        entries = client.request(
            "/timetable",
            username=username,
            week_start=week_start.isoformat(),
            week_end=week_end.isoformat(),
        )
        return json.dumps(
            {
                "username": username,
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "entries": entries,
            },
            ensure_ascii=False,
        )

    @mcp.tool(name="timetable_entry_get")
    def timetable_entry_get(timetable_id: int) -> str:
        """Get one timetable entry by its timetable_id."""
        if timetable_id < 1:
            raise ToolError("timetable_id must be a positive integer.")
        return json.dumps(
            client.request(f"/timetable/{timetable_id}"), ensure_ascii=False
        )

    @mcp.tool(name="timetable_free_time")
    def timetable_free_time(username: str, on_date: str) -> str:
        """Find a student's free time on one date (YYYY-MM-DD).

        Free time is every gap of at least 30 minutes between 08:00 and 23:00
        that no entry covers. All-day due dates do not take up any time.
        """
        username = known_username(username)
        day = _date(on_date, "on_date")
        entries = client.request(
            "/timetable",
            username=username,
            week_start=day.isoformat(),
            week_end=day.isoformat(),
        )
        busy = sorted(
            (entry for entry in entries if not entry["all_day"]),
            key=lambda entry: entry["start_time"],
        )

        free = []
        cursor = _minutes(DAY_START)
        for entry in busy:
            start = _minutes(entry["start_time"])
            if start - cursor >= MIN_FREE_MINUTES:
                free.append((cursor, start))
            cursor = max(cursor, _minutes(entry["end_time"]))
        if _minutes(DAY_END) - cursor >= MIN_FREE_MINUTES:
            free.append((cursor, _minutes(DAY_END)))

        return json.dumps(
            {
                "username": username,
                "date": day.isoformat(),
                "day_of_week": day.strftime("%A"),
                "window": f"{DAY_START}-{DAY_END}",
                "busy": [
                    {
                        "timetable_id": entry["timetable_id"],
                        "activity_name": entry["activity_name"],
                        "start_time": entry["start_time"],
                        "end_time": entry["end_time"],
                    }
                    for entry in busy
                ],
                "free": [
                    {"start": _hhmm(start), "end": _hhmm(end), "minutes": end - start}
                    for start, end in free
                ],
                "free_minutes": sum(end - start for start, end in free),
            },
            ensure_ascii=False,
        )
