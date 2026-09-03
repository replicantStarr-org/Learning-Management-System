import ipaddress
import os
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events
import requests


# A real class-schedule feed (a semester of weekly-recurring VEVENTs) is a few KB to a few hundred
# KB - this is a generous ceiling against a malicious or accidental huge response, not a realistic
# expectation.
FETCH_TIMEOUT_SECONDS = 10
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
REQUEST_HEADERS = {"User-Agent": "TimetableManager/1.0 (LMS calendar import)"}

_BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain"}

# This app stores one naive local HH:MM per entry with no timezone dimension anywhere, so every
# imported time has to be converted to a single assumed student timezone. Some feeds attach a
# named zone to each event (DTSTART;TZID=...) and some (observed directly against UTS Canvas'
# export) instead give an absolute UTC instant with no VTIMEZONE at all (DTSTART:...T030000Z) -
# either way, explicitly converting to this target with zoneinfo (correctly DST-aware, unlike a
# fixed offset) is the only encoding-agnostic way to land on the right wall-clock time. A truly
# floating/naive DTSTART (no tzinfo at all) is left untouched - there's nothing to convert.
IMPORT_TIMEZONE = os.getenv("IMPORT_TIMEZONE", "Australia/Sydney")
_TARGET_TZ = ZoneInfo(IMPORT_TIMEZONE)


class ICalError(RuntimeError):
    pass


def normalize_url(url):
    url = (url or "").strip()
    if url.lower().startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]
    return url


def _is_unsafe_host(hostname):
    # Best-effort guard against the import URL being used to reach this app's own services or
    # anything else on the host (the whole stack runs with network_mode: host, so "localhost" or a
    # private-IP literal here would reach real internal services) - not a hardened, DNS-resolution-
    # based SSRF defence, which would be disproportionate given this app has no real access control
    # anywhere else either (see design.md). Blocks the obvious literal cases only.
    if not hostname:
        return True
    hostname = hostname.lower()
    if hostname in _BLOCKED_HOSTNAMES or hostname.endswith(".local"):
        return True
    try:
        parsed_ip = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return parsed_ip.is_private or parsed_ip.is_loopback or parsed_ip.is_link_local or parsed_ip.is_reserved


def validate_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ICalError("The calendar URL must start with https:// (or webcal://).")
    if _is_unsafe_host(parsed.hostname):
        raise ICalError("That calendar URL can't be used.")
    return url


def fetch(url):
    try:
        response = requests.get(
            url, timeout=FETCH_TIMEOUT_SECONDS, headers=REQUEST_HEADERS, stream=True
        )
    except requests.RequestException as exc:
        raise ICalError("Could not reach that calendar URL.") from exc

    if not response.ok:
        raise ICalError(f"That calendar URL returned an error (HTTP {response.status_code}).")

    content = response.raw.read(MAX_RESPONSE_BYTES + 1, decode_content=True)
    if len(content) > MAX_RESPONSE_BYTES:
        raise ICalError("That calendar file is too large to import.")
    return content


def parse_events(ical_bytes, week_start, week_end):
    # Uses icalendar (RFC 5545 parsing - handles line folding, encodings, timezones properly
    # rather than a hand-rolled regex parser) plus recurring-ical-events (expands RRULE/RDATE/
    # EXDATE recurrence into concrete occurrences within a date range) - real class-schedule
    # exports are almost always one recurring VEVENT per weekly class, not one row per week.
    try:
        calendar = icalendar.Calendar.from_ical(ical_bytes)
    except Exception as exc:  # icalendar raises several distinct exception types for bad input
        raise ICalError("That URL did not return a valid calendar (.ics) file.") from exc

    try:
        occurrences = recurring_ical_events.of(calendar).between(
            (week_start.year, week_start.month, week_start.day),
            (week_end.year, week_end.month, week_end.day, 23, 59, 59),
        )
    except Exception as exc:
        raise ICalError("Could not read the events in that calendar file.") from exc

    # A real LMS export (confirmed directly against a UTS Canvas feed) is mostly *not* scheduled
    # class time - the bulk of it is assignment/quiz/exam due-date markers, which icalendar
    # represents either as an all-day (date-only) VEVENT or as a timed VEVENT with DTEND == DTSTART
    # (a single instant, not a range). Neither fits a timed block on an hourly grid, but a due date
    # is still real, useful information a student would want imported - so it's collected
    # separately as a "due" event (date + title only, no time-of-day) rather than silently dropped.
    timed_events = []
    due_events = []
    for occurrence in occurrences:
        dtstart = occurrence.get("DTSTART")
        if dtstart is None:
            continue
        start = dtstart.dt
        summary = str(occurrence.get("SUMMARY") or "Imported event").strip() or "Imported event"

        if not isinstance(start, datetime):
            # All-day (date-only) VEVENT - e.g. "Lab Week 2 - Submission" with no time attached.
            due_events.append({"date": start.isoformat(), "activity_name": summary[:120]})
            continue

        # Convert to IMPORT_TIMEZONE explicitly (see the module-level comment) rather than just
        # dropping tzinfo - a bare "just strip it" approach only happens to work for a feed that
        # already encodes each event with a matching TZID, and does nothing for a feed (like UTS
        # Canvas' export, confirmed directly against a real feed) that gives an absolute UTC
        # instant with no VTIMEZONE at all - that case needs an actual conversion, not just having
        # its "Z" ignored, or the entry keeps its raw UTC hour and silently lands outside the
        # calendar's 8am-11pm display window (observed: a 1pm Sydney lecture stored as 03:00).
        if start.tzinfo is not None:
            start = start.astimezone(_TARGET_TZ).replace(tzinfo=None)

        dtend = occurrence.get("DTEND")
        end = dtend.dt if dtend is not None else None
        if isinstance(end, datetime) and end.tzinfo is not None:
            end = end.astimezone(_TARGET_TZ).replace(tzinfo=None)

        if not isinstance(end, datetime) or end <= start:
            # Zero-length (or no DTEND at all) - a due-*time* marker such as Canvas' "Quiz 1 (10
            # Marks)" fixed-instant deadlines, not a real scheduled block. Treated the same as an
            # all-day due date (the exact due time isn't the primary thing a student needs here).
            due_events.append({"date": start.date().isoformat(), "activity_name": summary[:120]})
            continue

        if start.date() != end.date():
            continue  # spans midnight - doesn't fit this app's single-day timed entries

        timed_events.append(
            {
                "date": start.date().isoformat(),
                "start_time": start.strftime("%H:%M"),
                "end_time": end.strftime("%H:%M"),
                "activity_name": summary[:120],
            }
        )

    timed_events.sort(key=lambda e: (e["date"], e["start_time"]))
    due_events.sort(key=lambda e: e["date"])
    return timed_events, due_events
