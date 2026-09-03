import json
import os
import re
from datetime import date, datetime, timedelta, timezone

from services import ical_client
from services.database_client import database
from services.ollama_client import BLOCKED_OUTPUT, generate_advice, generate_weekly_plan


CATEGORIES = ("Class", "Study", "Personal", "Work", "Assessment", "Other")
PLAN_MAX_AGE_HOURS = int(os.getenv("PLAN_MAX_AGE_HOURS", "24"))
IMPORT_RANGE_WEEKS = int(os.getenv("IMPORT_RANGE_WEEKS", "16"))
TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
INJECTION_PATTERN = re.compile(
    r"(ignore (all |any )?(previous|prior|system) instructions|system prompt|"
    r"reveal .{0,20}(secret|password|token)|<\|im_(start|end)\|>|jailbreak)",
    re.IGNORECASE,
)


class ServiceError(RuntimeError):
    def __init__(self, message, status=400, details=None):
        super().__init__(message)
        self.status = status
        self.details = details


def _json(response, fallback="Timetable database service request failed"):
    try:
        body = response.json()
    except ValueError:
        body = {}
    if not response.ok:
        raise ServiceError(body.get("error", fallback), response.status_code, body)
    return body


def week_bounds(reference=None):
    reference = reference or date.today()
    week_start = reference - timedelta(days=reference.weekday())
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


def _require_username(username):
    username = str(username or "").strip()
    if not username:
        raise ServiceError("A username is required")
    if len(username) > 80:
        raise ServiceError("Username is too long")
    return username


def list_entries(username, week_start=None):
    username = _require_username(username)

    reference = None
    if week_start:
        try:
            reference = datetime.strptime(week_start, "%Y-%m-%d").date()
        except ValueError:
            raise ServiceError("week_start must be in YYYY-MM-DD format")

    start, end = week_bounds(reference)
    entries = _json(database.list_entries(username, start.isoformat(), end.isoformat()))
    return entries, start, end


def get_entry(timetable_id):
    return _json(database.get_entry(timetable_id), "Timetable entry not found")


def validate_entry(payload, partial=False):
    if not isinstance(payload, dict):
        raise ServiceError("Request body must be an object")

    required = () if partial else ("date", "start_time", "end_time", "category")
    missing = [field for field in required if not str(payload.get(field, "")).strip()]
    if missing:
        raise ServiceError("All required timetable fields must be provided", details={"fields": missing})

    cleaned = {}
    limits = {"activity_name": 120, "notes": 1000}

    if "date" in payload:
        raw = str(payload["date"]).strip()
        try:
            parsed = datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            raise ServiceError("Date must be in YYYY-MM-DD format")
        cleaned["date"] = parsed.isoformat()
        cleaned["day_of_week"] = parsed.strftime("%A")

    if "start_time" in payload or "end_time" in payload:
        start = str(payload.get("start_time", "")).strip()
        end = str(payload.get("end_time", "")).strip()
        if not TIME_PATTERN.match(start) or not TIME_PATTERN.match(end):
            raise ServiceError("Start and end time must be in HH:MM format")
        if start >= end:
            raise ServiceError("Start time must be before end time")
        cleaned["start_time"] = start
        cleaned["end_time"] = end

    if "activity_name" in payload:
        value = str(payload["activity_name"]).strip() or "Activity"
        if len(value) > limits["activity_name"]:
            raise ServiceError("Activity name is too long")
        cleaned["activity_name"] = value

    if "category" in payload:
        value = str(payload["category"]).strip().title()
        if value not in CATEGORIES:
            raise ServiceError(f"Category must be one of: {', '.join(CATEGORIES)}")
        cleaned["category"] = value

    if "notes" in payload:
        value = str(payload.get("notes") or "").strip()
        if len(value) > limits["notes"]:
            raise ServiceError("Notes are too long")
        cleaned["notes"] = value

    if not cleaned:
        raise ServiceError("At least one timetable field is required")
    return cleaned


def _times_overlap(start_a, end_a, start_b, end_b):
    return start_a < end_b and start_b < end_a


def _find_clash(username, date, start_time, end_time, exclude_id=None):
    day_entries = _json(database.list_entries(username, date, date))
    for entry in day_entries:
        if exclude_id is not None and entry["timetable_id"] == exclude_id:
            continue
        if entry.get("all_day"):
            continue
        if _times_overlap(start_time, end_time, entry["start_time"], entry["end_time"]):
            return entry
    return None


def _clash_error(clash, date):
    return ServiceError(
        f"This clashes with \"{clash['activity_name']}\" ({clash['start_time']}-{clash['end_time']}) "
        f"already scheduled on {date}",
        409,
    )


def _find_duplicate_due(username, date, activity_name):
    day_entries = _json(database.list_entries(username, date, date))
    return any(
        entry.get("all_day") and entry["activity_name"] == activity_name for entry in day_entries
    )


def create_entry(username, payload, ai_generated=False, all_day=False):
    username = _require_username(username)
    cleaned = validate_entry(payload)
    if not all_day:
        clash = _find_clash(username, cleaned["date"], cleaned["start_time"], cleaned["end_time"])
        if clash:
            raise _clash_error(clash, cleaned["date"])
    cleaned["username"] = username
    cleaned["ai_generated"] = bool(ai_generated)
    cleaned["all_day"] = bool(all_day)
    return _json(database.create_entry(cleaned), "Could not create timetable entry")


def update_entry(timetable_id, payload):
    cleaned = validate_entry(payload, partial=True)
    if {"date", "start_time", "end_time"} & cleaned.keys():
        current = get_entry(timetable_id)
        if not current.get("all_day"):
            effective_date = cleaned.get("date", current["date"])
            effective_start = cleaned.get("start_time", current["start_time"])
            effective_end = cleaned.get("end_time", current["end_time"])
            clash = _find_clash(
                current["username"], effective_date, effective_start, effective_end, exclude_id=timetable_id
            )
            if clash:
                raise _clash_error(clash, effective_date)
    return _json(
        database.update_entry(timetable_id, cleaned),
        "Could not update timetable entry",
    )


def delete_entry(timetable_id):
    response = database.delete_entry(timetable_id)
    if not response.ok:
        _json(response, "Could not delete timetable entry")


def import_ical_schedule(username, ical_url, category="Class"):
    username = _require_username(username)
    category = str(category or "Class").strip().title()
    if category not in CATEGORIES:
        category = "Class"

    url = ical_client.normalize_url(ical_url)
    if not url:
        raise ServiceError("A calendar URL is required")

    week_start, _current_week_end = week_bounds()
    range_end = week_start + timedelta(weeks=IMPORT_RANGE_WEEKS) - timedelta(days=1)
    try:
        ical_client.validate_url(url)
        ical_bytes = ical_client.fetch(url)
        timed_events, due_events = ical_client.parse_events(ical_bytes, week_start, range_end)
    except ical_client.ICalError as exc:
        raise ServiceError(str(exc)) from exc

    imported = skipped = 0
    for event in timed_events:
        try:
            create_entry(username, {**event, "category": category})
            imported += 1
        except ServiceError:
            skipped += 1

    due_imported = due_skipped = 0
    for event in due_events:
        if _find_duplicate_due(username, event["date"], event["activity_name"]):
            due_skipped += 1
            continue
        try:
            create_entry(
                username,
                {**event, "start_time": "00:00", "end_time": "23:59", "category": "Assessment"},
                all_day=True,
            )
            due_imported += 1
        except ServiceError:
            due_skipped += 1

    return {
        "found": len(timed_events),
        "imported": imported,
        "skipped": skipped,
        "due_found": len(due_events),
        "due_imported": due_imported,
        "due_skipped": due_skipped,
        "week_start": week_start,
        "week_end": range_end,
    }


def _entries_to_text(entries):
    if not entries:
        return "No timetable entries are currently scheduled this week."
    lines = []
    for entry in entries:
        if entry.get("all_day"):
            lines.append(f"{entry['day_of_week']} {entry['date']}: DUE - {entry['activity_name']} ({entry['category']})")
        else:
            lines.append(
                f"{entry['day_of_week']} {entry['date']} {entry['start_time']}-{entry['end_time']}: "
                f"{entry['activity_name']} ({entry['category']})"
            )
    return "\n".join(lines)


DAY_START_HOUR = 8
DAY_END_HOUR = 23
MIN_USEFUL_GAP_MINUTES = 30


def _minutes_from_hhmm(hhmm):
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def _hhmm_from_minutes(total_minutes):
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def _free_intervals_by_day(entries, week_start):
    occupied_by_date = {}
    for entry in entries:
        occupied_by_date.setdefault(entry["date"], []).append(
            (_minutes_from_hhmm(entry["start_time"]), _minutes_from_hhmm(entry["end_time"]))
        )

    day_start = DAY_START_HOUR * 60
    day_end = DAY_END_HOUR * 60
    result = {}
    current = week_start
    for _ in range(7):
        date_iso = current.isoformat()
        intervals = sorted(occupied_by_date.get(date_iso, []))
        free = []
        cursor = day_start
        for start, end in intervals:
            if start > cursor:
                free.append((cursor, start))
            cursor = max(cursor, end)
        if cursor < day_end:
            free.append((cursor, day_end))
        result[date_iso] = {
            "free": [(s, e) for s, e in free if e - s >= MIN_USEFUL_GAP_MINUTES],
            "has_entries": bool(intervals),
        }
        current = current + timedelta(days=1)
    return result


def _free_blocks_by_day(entries, week_start):
    intervals = _free_intervals_by_day(entries, week_start)
    lines = []
    current = week_start
    for _ in range(7):
        day = intervals[current.isoformat()]
        if not day["has_entries"]:
            window = f"{_hhmm_from_minutes(DAY_START_HOUR * 60)}-{_hhmm_from_minutes(DAY_END_HOUR * 60)}"
            free_text = f"ENTIRELY FREE all day ({window}) - no entries at all"
        elif day["free"]:
            free_text = ", ".join(f"{_hhmm_from_minutes(s)}-{_hhmm_from_minutes(e)}" for s, e in day["free"])
        else:
            free_text = "no free time of 30+ minutes in the 8am-11pm window"
        lines.append(f"{current.strftime('%A')} {current.isoformat()}: {free_text}")
        current = current + timedelta(days=1)
    return "\n".join(lines)


def _total_free_minutes(entries, week_start):
    intervals = _free_intervals_by_day(entries, week_start)
    return sum(e - s for day in intervals.values() for s, e in day["free"])


def _empty_days(entries, week_start):
    intervals = _free_intervals_by_day(entries, week_start)
    return {date_iso for date_iso, day in intervals.items() if not day["has_entries"]}


def _rank_days_by_free_time(entries, week_start):
    intervals = _free_intervals_by_day(entries, week_start)
    ranked = []
    current = week_start
    for _ in range(7):
        date_iso = current.isoformat()
        day = intervals[date_iso]
        total_free = sum(e - s for s, e in day["free"])
        if total_free >= MIN_USEFUL_GAP_MINUTES:
            ranked.append(
                {
                    "date": date_iso,
                    "day_of_week": current.strftime("%A"),
                    "total_free_minutes": total_free,
                    "largest_interval": max(day["free"], key=lambda iv: iv[1] - iv[0]),
                }
            )
        current = current + timedelta(days=1)
    ranked.sort(key=lambda d: d["total_free_minutes"], reverse=True)
    return ranked


def _plan_target_days(entries, week_start, suggest_minutes, max_count):
    ranked = _rank_days_by_free_time(entries, week_start)
    if not ranked or suggest_minutes < MIN_USEFUL_GAP_MINUTES:
        return []

    num_days = min(max_count, len(ranked), max(1, suggest_minutes // MIN_USEFUL_GAP_MINUTES))
    selected = ranked[:num_days]
    per_day = max(MIN_USEFUL_GAP_MINUTES, (suggest_minutes // num_days // 15) * 15)

    for day in selected:
        interval_minutes = day["largest_interval"][1] - day["largest_interval"][0]
        day["target_minutes"] = min(per_day, interval_minutes)
    return selected


def _detect_clashes(entries):
    by_date = {}
    for entry in entries:
        by_date.setdefault(entry["date"], []).append(entry)

    clashes = []
    for date_entries in by_date.values():
        for i in range(len(date_entries)):
            for j in range(i + 1, len(date_entries)):
                a, b = date_entries[i], date_entries[j]
                if _times_overlap(a["start_time"], a["end_time"], b["start_time"], b["end_time"]):
                    clashes.append(
                        f"{a['date']}: \"{a['activity_name']}\" ({a['start_time']}-{a['end_time']}) "
                        f"overlaps \"{b['activity_name']}\" ({b['start_time']}-{b['end_time']})"
                    )
    return clashes


STUDY_TO_CLASS_RATIO = 2.0
WORK_HOURS_CONCERN_THRESHOLD = 30 * 60


def _weekly_balance(entries):
    day_start = DAY_START_HOUR * 60
    day_end = DAY_END_HOUR * 60

    def category_minutes(category):
        total = 0
        for entry in entries:
            if entry["category"] != category:
                continue
            start = max(_minutes_from_hhmm(entry["start_time"]), day_start)
            end = min(_minutes_from_hhmm(entry["end_time"]), day_end)
            if end > start:
                total += end - start
        return total

    class_minutes = category_minutes("Class")
    study_minutes = category_minutes("Study")
    work_minutes = category_minutes("Work")
    target_study_minutes = round(class_minutes * STUDY_TO_CLASS_RATIO)
    gap_minutes = max(target_study_minutes - study_minutes, 0)

    return {
        "class_minutes": class_minutes,
        "study_minutes": study_minutes,
        "work_minutes": work_minutes,
        "target_study_minutes": target_study_minutes,
        "gap_minutes": gap_minutes,
        "suggest_minutes": min(gap_minutes, MAX_SUGGESTED_GAP_MINUTES),
    }


MAX_SUGGESTED_GAP_MINUTES = 240
MAX_SUGGESTION_COUNT = 4


def _trim_to_budget(suggestions, budget_minutes, max_count):
    accepted = []
    total_minutes = 0
    for suggestion in suggestions:
        if len(accepted) >= max_count:
            break
        duration = _minutes_from_hhmm(suggestion["end_time"]) - _minutes_from_hhmm(suggestion["start_time"])
        if accepted and total_minutes + duration > budget_minutes:
            break
        accepted.append(suggestion)
        total_minutes += duration
    return accepted


def _target_days_text(target_days):
    if not target_days:
        return "None."
    return "\n".join(
        f"{d['day_of_week']} {d['date']}: aim for about {round(d['target_minutes'] / 60, 1)}h, "
        f"somewhere within {_hhmm_from_minutes(d['largest_interval'][0])}-"
        f"{_hhmm_from_minutes(d['largest_interval'][1])} "
        f"({round(d['total_free_minutes'] / 60, 1)}h free that day in total)"
        for d in target_days
    )


def _balance_text(balance, target_days):
    def hours(minutes):
        return round(minutes / 60, 1)

    if balance["class_minutes"] == 0:
        return "No Class entries are logged this week. Do not suggest any Study blocks - suggested_entries must be empty."

    if balance["gap_minutes"] >= MIN_USEFUL_GAP_MINUTES and target_days:
        return (
            f"Target is {hours(balance['target_study_minutes'])}h of Study ({hours(balance['class_minutes'])}h "
            f"Class x2); {hours(balance['study_minutes'])}h is currently scheduled. Suggest exactly one Study "
            "block on each day listed in COMPUTED TARGET DAYS below - never more than one block per day, and "
            "never on any day not listed there (those days were chosen because they already have the most "
            "free time - do not substitute a different day). Size each block close to that day's stated "
            "target duration, placed somewhere within that day's stated free window. Never suggest a generic "
            "'relax'/'break'/'leisure'/free-time block."
        )
    return (
        "Target study time is already met, or no day has enough free time to fit a block. Do not suggest "
        "any Study blocks - suggested_entries must be empty."
    )


def _plan_context_text(entries, week_start, balance, target_days):
    clashes = _detect_clashes(entries)
    clashes_text = "\n".join(clashes) if clashes else "None - do not describe any clash or overlap."
    return (
        f"CURRENT ENTRIES:\n{_entries_to_text(entries)}\n\n"
        f"COMPUTED FREE TIME PER DAY (8am-11pm window, gaps of {MIN_USEFUL_GAP_MINUTES}+ minutes, "
        "already verified - trust this exactly):\n"
        f"{_free_blocks_by_day(entries, week_start)}\n\n"
        "COMPUTED TIME CLASHES (already verified exactly - trust this list, do not invent any "
        f"other clash):\n{clashes_text}\n\n"
        f"COMPUTED WEEKLY BALANCE (already verified exactly - follow this instruction):\n"
        f"{_balance_text(balance, target_days)}\n\n"
        "COMPUTED TARGET DAYS (already chosen exactly, ranked by free time - place exactly one "
        f"Study block on each of these days and no others):\n{_target_days_text(target_days)}"
    )


def _synthesize_suggestion(day):
    start, _ = day["largest_interval"]
    end = start + day["target_minutes"]
    return {
        "date": day["date"],
        "day_of_week": day["day_of_week"],
        "start_time": _hhmm_from_minutes(start),
        "end_time": _hhmm_from_minutes(end),
        "activity_name": "Study",
        "category": "Study",
    }


def _parse_timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)


def _latest_plan(username):
    response = database.latest_plan(username)
    if response.status_code == 404:
        return None
    return _json(response)


def _drop_clashing_suggestions(suggestions, entries):
    accepted = []
    for suggestion in suggestions:
        against_entries = any(
            suggestion["date"] == entry["date"]
            and _times_overlap(
                suggestion["start_time"], suggestion["end_time"], entry["start_time"], entry["end_time"]
            )
            for entry in entries
        )
        against_accepted = any(
            suggestion["date"] == kept["date"]
            and _times_overlap(
                suggestion["start_time"], suggestion["end_time"], kept["start_time"], kept["end_time"]
            )
            for kept in accepted
        )
        if not against_entries and not against_accepted:
            accepted.append(suggestion)
    return accepted


WEEKDAY_ORDER = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _diversify_by_day(suggestions):
    by_day = {}
    order = []
    for suggestion in suggestions:
        if suggestion["date"] not in by_day:
            by_day[suggestion["date"]] = []
            order.append(suggestion["date"])
        by_day[suggestion["date"]].append(suggestion)

    result = []
    while any(by_day[date] for date in order):
        for date in order:
            if by_day[date]:
                result.append(by_day[date].pop(0))
    return result


def _build_plan_narrative(balance, entries, week_start, accepted_suggestions):
    def hours(minutes):
        return round(minutes / 60, 1)

    if balance["class_minutes"] == 0:
        return (
            "No class hours are logged yet, so a personalised study target can't be calculated. "
            "Research suggests roughly 2 hours of independent study per hour of class (the "
            "standard university credit-hour guideline) - log your classes to see your target "
            "here. All empty space on your calendar is free time and doesn't need to be filled."
        )

    target_h = hours(balance["target_study_minutes"])
    current_h = hours(balance["study_minutes"])
    parts = [
        f"Research states that the optimised amount of study time is {target_h}h per week, based "
        f"on {hours(balance['class_minutes'])}h of classes (the \"2-hour rule\": roughly 2 hours "
        "of independent study per hour of class, the standard university credit-hour guideline).",
        f"Currently, your schedule has {current_h}h of study time allocated.",
    ]

    if balance["gap_minutes"] < MIN_USEFUL_GAP_MINUTES:
        parts.append(
            "You're already at or above that target - the remaining free time on your calendar "
            "is yours to use as you like."
        )
    elif not accepted_suggestions:
        parts.append(
            "Your week is very full, so no additional study sessions could be fit in right now. "
            f"The optimal amount of studying time should still be {target_h}h - freeing up some "
            "time would help you work towards it."
        )
    else:
        suggested_minutes = sum(
            _minutes_from_hhmm(s["end_time"]) - _minutes_from_hhmm(s["start_time"])
            for s in accepted_suggestions
        )
        empty_days = _empty_days(entries, week_start)
        days_seen, empty_days_used = [], []
        for suggestion in accepted_suggestions:
            if suggestion["day_of_week"] not in days_seen:
                days_seen.append(suggestion["day_of_week"])
                if suggestion["date"] in empty_days:
                    empty_days_used.append(suggestion["day_of_week"])
        days_sorted = sorted(days_seen, key=WEEKDAY_ORDER.index)

        is_packed = _total_free_minutes(entries, week_start) < balance["gap_minutes"]
        if is_packed:
            parts.append(
                f"Your schedule is quite packed, so to adjust this, {hours(suggested_minutes)}h "
                f"of study has been suggested on {', '.join(days_sorted)} - as much as could "
                f"reasonably fit. The optimal amount of studying time should still be {target_h}h; "
                "freeing up more time elsewhere would help close the rest of the gap."
            )
        else:
            parts.append(
                f"To adjust this, {hours(suggested_minutes)}h of study has been suggested on "
                f"{', '.join(days_sorted)}."
            )
            if balance["gap_minutes"] > suggested_minutes:
                parts.append(
                    f"This is a first step - about {hours(balance['gap_minutes'] - suggested_minutes)}h "
                    "would still remain to fully reach the target over time."
                )

        if empty_days_used:
            parts.append(
                f"{', '.join(empty_days_used)} had no entries at all, so a session was placed "
                "there to help spread study sessions properly across the week rather than "
                "clustering them."
            )
        parts.append("All other empty space on your calendar is available as free time and doesn't need to be filled.")

    if balance["work_minutes"] >= WORK_HOURS_CONCERN_THRESHOLD:
        parts.append(
            f"Separately: paid work is at {hours(balance['work_minutes'])}h this week, at or "
            "above the point research links to declining academic performance (around 30h/week) "
            "- worth keeping an eye on."
        )

    return " ".join(parts)


def get_or_create_plan(username, force=False):
    username = _require_username(username)
    entries, week_start, _week_end = list_entries(username)
    entries = [entry for entry in entries if not entry.get("all_day")]

    balance = _weekly_balance(entries)
    existing = _latest_plan(username)
    has_reusable_suggestions = existing is not None and existing.get("suggested_entries") is not None
    if existing and has_reusable_suggestions and not force:
        plan_updated = _parse_timestamp(existing.get("regenerated_at") or existing["created_at"])
        newest_entry = max(
            (_parse_timestamp(entry["last_updated"]) for entry in entries),
            default=plan_updated,
        )
        age_hours = (datetime.now(timezone.utc) - plan_updated).total_seconds() / 3600
        if plan_updated >= newest_entry and age_hours <= PLAN_MAX_AGE_HOURS:
            try:
                stored_suggestions = json.loads(existing.get("suggested_entries") or "[]")
            except (json.JSONDecodeError, TypeError):
                stored_suggestions = []
            stored_suggestions = _drop_clashing_suggestions(stored_suggestions, entries)
            stored_suggestions = _diversify_by_day(stored_suggestions)
            stored_suggestions = _trim_to_budget(
                stored_suggestions, balance["suggest_minutes"], MAX_SUGGESTION_COUNT
            )
            plan_text = _build_plan_narrative(balance, entries, week_start, stored_suggestions)
            return {
                **existing,
                "plan_text": plan_text,
                "reused": True,
                "suggested_entries": stored_suggestions,
                "entries": entries,
                "week_start": week_start,
            }

    target_days = _plan_target_days(entries, week_start, balance["suggest_minutes"], MAX_SUGGESTION_COUNT)
    context_text = _plan_context_text(entries, week_start, balance, target_days)
    if INJECTION_PATTERN.search(context_text):
        raise ServiceError("The timetable content was rejected as unsafe for AI planning", 422)

    payload, raw = generate_weekly_plan(context_text)
    if payload is None or BLOCKED_OUTPUT in raw:
        raise ServiceError("The AI could not generate a valid plan. Please try again.", 422)

    suggestions = payload.get("suggested_entries")
    cleaned_suggestions = []
    for suggestion in suggestions if isinstance(suggestions, list) else []:
        try:
            cleaned = validate_entry(suggestion)
        except ServiceError:
            continue
        if cleaned.get("category") != "Study":
            continue
        cleaned_suggestions.append(cleaned)
    cleaned_suggestions = _drop_clashing_suggestions(cleaned_suggestions, entries)

    by_target_date = {day["date"]: None for day in target_days}
    for suggestion in cleaned_suggestions:
        if suggestion["date"] in by_target_date and by_target_date[suggestion["date"]] is None:
            by_target_date[suggestion["date"]] = suggestion
    final_suggestions = []
    for day in target_days:
        chosen = by_target_date[day["date"]] or _synthesize_suggestion(day)
        final_suggestions.append(chosen)

    cleaned_suggestions = _trim_to_budget(final_suggestions, balance["suggest_minutes"], MAX_SUGGESTION_COUNT)
    plan_text = _build_plan_narrative(balance, entries, week_start, cleaned_suggestions)
    suggestions_json = json.dumps(cleaned_suggestions)

    if existing:
        result = _json(
            database.update_plan(existing["plan_id"], plan_text, suggestions_json), "Could not update plan"
        )
    else:
        result = _json(
            database.create_plan(username, plan_text, suggestions_json), "Could not store plan"
        )

    result["reused"] = False
    result["suggested_entries"] = cleaned_suggestions
    result["entries"] = entries
    result["week_start"] = week_start
    return result


def create_advice(username, question):
    username = _require_username(username)
    question = str(question or "").strip()
    if len(question) > 1000:
        raise ServiceError("Question must be 1000 characters or fewer")
    if question and INJECTION_PATTERN.search(question):
        raise ServiceError("That question cannot be processed safely", 422)

    entries, _week_start, _week_end = list_entries(username)
    entries_text = _entries_to_text(entries)
    if INJECTION_PATTERN.search(entries_text):
        raise ServiceError("The timetable content was rejected as unsafe for AI advice", 422)

    advice_text = generate_advice(entries_text, question)
    if BLOCKED_OUTPUT in advice_text:
        raise ServiceError("The AI rejected this request as unsafe", 422)

    return _json(
        database.create_advice(username, question or None, advice_text),
        "Could not store advice",
    )


def list_advice(username):
    username = _require_username(username)
    return _json(database.list_advice(username))
