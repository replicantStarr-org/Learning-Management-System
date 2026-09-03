import ipaddress
import os
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events
import requests


FETCH_TIMEOUT_SECONDS = 10
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
REQUEST_HEADERS = {"User-Agent": "TimetableManager/1.0 (LMS calendar import)"}

_BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain"}

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
    try:
        calendar = icalendar.Calendar.from_ical(ical_bytes)
    except Exception as exc:
        raise ICalError("That URL did not return a valid calendar (.ics) file.") from exc

    try:
        occurrences = recurring_ical_events.of(calendar).between(
            (week_start.year, week_start.month, week_start.day),
            (week_end.year, week_end.month, week_end.day, 23, 59, 59),
        )
    except Exception as exc:
        raise ICalError("Could not read the events in that calendar file.") from exc

    timed_events = []
    due_events = []
    for occurrence in occurrences:
        dtstart = occurrence.get("DTSTART")
        if dtstart is None:
            continue
        start = dtstart.dt
        summary = str(occurrence.get("SUMMARY") or "Imported event").strip() or "Imported event"

        if not isinstance(start, datetime):
            due_events.append({"date": start.isoformat(), "activity_name": summary[:120]})
            continue

        if start.tzinfo is not None:
            start = start.astimezone(_TARGET_TZ).replace(tzinfo=None)

        dtend = occurrence.get("DTEND")
        end = dtend.dt if dtend is not None else None
        if isinstance(end, datetime) and end.tzinfo is not None:
            end = end.astimezone(_TARGET_TZ).replace(tzinfo=None)

        if not isinstance(end, datetime) or end <= start:
            due_events.append({"date": start.date().isoformat(), "activity_name": summary[:120]})
            continue

        if start.date() != end.date():
            continue

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
