import json
from datetime import date, timedelta
from html import escape


BACKEND_BASE = "http://localhost:5005"

CATEGORY_BADGES = {
    "Class": "text-bg-primary",
    "Study": "text-bg-info",
    "Personal": "text-bg-warning",
    "Work": "text-bg-secondary",
    "Assessment": "text-bg-danger",
    "Other": "text-bg-dark",
}

CATEGORY_SLUGS = {
    "Class": "cat-class",
    "Study": "cat-study",
    "Personal": "cat-personal",
    "Work": "cat-work",
    "Assessment": "cat-assessment",
    "Other": "cat-other",
}

# The grid shows this fixed 8am-11pm window. Must stay in sync with --cal-hour-height in
# timetable/frontend/calendar.css, which is what actually renders the pixel heights below.
CALENDAR_START_HOUR = 8
CALENDAR_END_HOUR = 23
PX_PER_HOUR = 56


def escaped(value):
    return escape(str(value), quote=True)


def message(text):
    return f'<div class="alert alert-success mt-3" role="status">{escaped(text)}</div>'


def error(text):
    return f'<div class="alert alert-danger mt-3" role="alert">{escaped(text)}</div>'


def _to_minutes(hhmm):
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def _format_hour_label(hour):
    period = "AM" if hour < 12 else "PM"
    display_hour = hour % 12 or 12
    return f"{display_hour} {period}"


def _assign_lanes(day_entries):
    # Greedy interval-graph colouring: each entry takes the first lane whose previous
    # occupant has already finished, so entries that overlap in time render side-by-side
    # instead of stacking on top of each other. Entries seeded/created with no overlaps
    # (the common case) all land in lane 0 and take the day column's full width.
    lane_ends = []
    assignments = []
    for entry in sorted(day_entries, key=lambda e: e["_start_min"]):
        for lane_index, lane_end in enumerate(lane_ends):
            if entry["_start_min"] >= lane_end:
                lane_ends[lane_index] = entry["_end_min"]
                assignments.append((entry, lane_index))
                break
        else:
            lane_ends.append(entry["_end_min"])
            assignments.append((entry, len(lane_ends) - 1))
    return assignments, max(len(lane_ends), 1)


def _cal_entry_block(entry, lane_index, total_lanes, interactive=True):
    window_start = CALENDAR_START_HOUR * 60
    window_end = CALENDAR_END_HOUR * 60
    start_min = max(entry["_start_min"], window_start)
    end_min = min(entry["_end_min"], window_end)
    if end_min <= start_min:
        # Entirely outside the visible 8am-11pm window - nothing sensible to draw.
        return ""

    px_per_min = PX_PER_HOUR / 60
    top = (start_min - window_start) * px_per_min
    height = max((end_min - start_min) * px_per_min, 22)
    left = (lane_index / total_lanes) * 100
    width = (1 / total_lanes) * 100

    slug = CATEGORY_SLUGS.get(entry.get("category"), "cat-other")
    ai_icon = (
        '<i class="bi bi-stars" aria-hidden="true"></i> ' if entry.get("ai_generated") else ""
    )
    tooltip = escaped(f"{entry['activity_name']} ({entry['start_time']} - {entry['end_time']})")

    # interactive=False renders a plain read-only block - used for the AI-plan preview, where
    # the student's real entries are shown for context only and shouldn't be editable/deletable
    # from inside that view.
    actions = ""
    if interactive:
        timetable_id = escaped(entry["timetable_id"])
        actions = f"""
        <div class="cal-entry-actions">
            <a href="/edit.html?id={timetable_id}" title="Edit" aria-label="Edit entry"><i class="bi bi-pencil" aria-hidden="true"></i></a>
            <button type="button" title="Delete" aria-label="Delete entry"
                    hx-post="{BACKEND_BASE}/timetable/delete"
                    hx-vals='{{"timetable_id": "{timetable_id}"}}'
                    hx-confirm="Delete this timetable entry?"><i class="bi bi-x-lg" aria-hidden="true"></i></button>
        </div>
        """

    return f"""
    <div class="cal-entry {slug}" title="{tooltip}"
         style="top: {top:.1f}px; height: {height:.1f}px; left: calc({left:.3f}% + 2px); width: calc({width:.3f}% - 4px);">
        {actions}
        <span class="cal-entry-title">{ai_icon}{escaped(entry['activity_name'])}</span>
        <span class="cal-entry-time">{escaped(entry['start_time'])} - {escaped(entry['end_time'])}</span>
    </div>
    """


def _due_pill(item):
    timetable_id = escaped(item["timetable_id"])
    return f"""
    <div class="cal-due-pill" title="{escaped('Due: ' + item['activity_name'])}">
        <span class="cal-due-title"><i class="bi bi-flag-fill" aria-hidden="true"></i> {escaped(item['activity_name'])}</span>
        <div class="cal-due-actions">
            <a href="/edit.html?id={timetable_id}" title="Edit" aria-label="Edit due date"><i class="bi bi-pencil" aria-hidden="true"></i></a>
            <button type="button" title="Delete" aria-label="Delete due date"
                    hx-post="{BACKEND_BASE}/timetable/delete" hx-vals='{{"timetable_id": "{timetable_id}"}}'
                    hx-confirm="Delete this due date?"><i class="bi bi-x" aria-hidden="true"></i></button>
        </div>
    </div>
    """


def _calendar_frame(week_start, render_day, render_due=None):
    # Shared by the main weekly grid and the AI-plan preview: builds the day-header row, an
    # optional all-day due-date banner row (render_due - omitted entirely, not just left empty,
    # when the caller has no all-day entries to show, e.g. the read-only AI-plan preview), the
    # hour-label gutter, and 7 day columns, delegating each day's actual blocks to render_day.
    column_height = (CALENDAR_END_HOUR - CALENDAR_START_HOUR) * PX_PER_HOUR
    hour_labels = "".join(
        f'<div class="cal-hour-label" style="top: {(hour - CALENDAR_START_HOUR) * PX_PER_HOUR}px">{_format_hour_label(hour)}</div>'
        for hour in range(CALENDAR_START_HOUR, CALENDAR_END_HOUR)
    )

    day_headers = []
    due_cells = []  # each day's raw content, before wrapping - so emptiness is checkable below
    day_columns = []
    current = week_start
    today = date.today()
    for _ in range(7):
        day_headers.append(f"""
        <div class="cal-day-header{' cal-today' if current == today else ''}">
            <span class="cal-day-name">{current.strftime('%a')}</span>
            <span class="cal-day-date">{current.strftime('%d %b')}</span>
        </div>
        """)
        if render_due is not None:
            due_cells.append(render_due(current.isoformat()))
        day_columns.append(
            f'<div class="cal-day-col" data-date="{current.isoformat()}" '
            f'style="height: {column_height}px;">{render_day(current.isoformat())}</div>'
        )
        current = current + timedelta(days=1)

    # Only rendered when at least one day actually has due-date content, so a week with nothing
    # imported looks exactly like it did before this feature existed - no empty strip of clutter.
    due_row = ""
    if any(due_cells):
        due_columns = "".join(f'<div class="cal-due-col">{cell}</div>' for cell in due_cells)
        due_row = f'<div class="cal-due-corner"></div>{due_columns}'

    return f"""
    <div class="calendar-scroll">
        <div class="calendar-grid">
            <div class="cal-corner"></div>
            {''.join(day_headers)}
            {due_row}
            <div class="cal-time-col" style="height: {column_height}px;">{hour_labels}</div>
            {''.join(day_columns)}
        </div>
    </div>
    """


def weekly_grid(entries, week_start, week_end, username):
    by_date = {}
    due_by_date = {}
    for entry in entries:
        if entry.get("all_day"):
            due_by_date.setdefault(entry["date"], []).append(entry)
            continue
        enriched = dict(entry)
        enriched["_start_min"] = _to_minutes(entry["start_time"])
        enriched["_end_min"] = _to_minutes(entry["end_time"])
        by_date.setdefault(entry["date"], []).append(enriched)

    def render_day(date_iso):
        assignments, total_lanes = _assign_lanes(by_date.get(date_iso, []))
        return "".join(
            _cal_entry_block(entry, lane_index, total_lanes) for entry, lane_index in assignments
        )

    def render_due(date_iso):
        return "".join(_due_pill(item) for item in due_by_date.get(date_iso, []))

    prev_week = escaped((week_start - timedelta(days=7)).isoformat())
    next_week = escaped((week_start + timedelta(days=7)).isoformat())
    username_param = escaped(username)

    today_date = date.today()
    current_week_start = today_date - timedelta(days=today_date.weekday())
    is_current_week = week_start == current_week_start
    current_week_param = escaped(current_week_start.isoformat())
    today_button = f"""
    <button class="btn btn-sm {'btn-primary' if is_current_week else 'btn-outline-primary'}" type="button"
            hx-get="{BACKEND_BASE}/timetable?username={username_param}&week_start={current_week_param}"
            hx-target="#timetable-grid" hx-swap="innerHTML"
            hx-push-url="?week_start={current_week_param}"
            {'disabled' if is_current_week else ''}>
        Today
    </button>
    """

    return f"""
    <div class="d-flex justify-content-between align-items-center mb-3">
        <div class="d-flex gap-2">
            {today_button}
            <button class="btn btn-outline-secondary btn-sm" type="button"
                    hx-get="{BACKEND_BASE}/timetable?username={username_param}&week_start={prev_week}"
                    hx-target="#timetable-grid" hx-swap="innerHTML"
                    hx-push-url="?week_start={prev_week}">
                <i class="bi bi-arrow-left"></i> Previous week
            </button>
        </div>
        <span class="fw-semibold">{week_start.strftime('%d %b')} - {week_end.strftime('%d %b %Y')}</span>
        <button class="btn btn-outline-secondary btn-sm" type="button"
                hx-get="{BACKEND_BASE}/timetable?username={username_param}&week_start={next_week}"
                hx-target="#timetable-grid" hx-swap="innerHTML"
                hx-push-url="?week_start={next_week}">
            Next week <i class="bi bi-arrow-right"></i>
        </button>
    </div>
    {_calendar_frame(week_start, render_day, render_due)}
    """


def entry_detail(entry):
    category = entry.get("category", "Other")
    badge_class = CATEGORY_BADGES.get(category, "text-bg-dark")
    notes = (
        f'<p class="mb-0">{escaped(entry["notes"])}</p>'
        if entry.get("notes")
        else '<p class="text-secondary mb-0">No notes.</p>'
    )
    when = (
        "Due date - no scheduled time"
        if entry.get("all_day")
        else f"{escaped(entry['start_time'])} - {escaped(entry['end_time'])}"
    )
    return f"""
    <article class="card border-0 shadow-sm">
        <div class="card-body p-4">
            <span class="badge {badge_class} mb-2">{escaped(category)}</span>
            <h1 class="h4 fw-bold">{escaped(entry['activity_name'])}</h1>
            <p class="text-secondary mb-3">{escaped(entry['day_of_week'])} {escaped(entry['date'])}, {when}</p>
            {notes}
            <p class="small text-secondary mt-3 mb-0">Last updated {escaped(entry['last_updated'])}</p>
        </div>
    </article>
    """


def _entry_fields(entry=None):
    values = entry or {}
    category_options = "".join(
        f'<option value="{escaped(cat)}" {"selected" if values.get("category") == cat else ""}>{escaped(cat)}</option>'
        for cat in CATEGORY_BADGES
    )
    return f"""
    <div class="row g-3 mb-3">
        <div class="col-md-4">
            <label class="form-label" for="date">Date</label>
            <input class="form-control" type="date" id="date" name="date" value="{escaped(values.get('date', ''))}" required>
        </div>
        <div class="col-md-4">
            <label class="form-label" for="start_time">Start time</label>
            <input class="form-control" type="time" id="start_time" name="start_time" value="{escaped(values.get('start_time', ''))}" required>
        </div>
        <div class="col-md-4">
            <label class="form-label" for="end_time">End time</label>
            <input class="form-control" type="time" id="end_time" name="end_time" value="{escaped(values.get('end_time', ''))}" required>
        </div>
        <div class="col-md-8">
            <label class="form-label" for="activity_name">Activity (optional)</label>
            <input class="form-control" id="activity_name" name="activity_name" maxlength="120"
                   value="{escaped(values.get('activity_name', ''))}" placeholder="Defaults to &quot;Activity&quot; if left blank">
        </div>
        <div class="col-md-4">
            <label class="form-label" for="category">Category</label>
            <select class="form-select" id="category" name="category" required>{category_options}</select>
        </div>
    </div>
    <div class="mb-4">
        <label class="form-label" for="notes">Notes (optional)</label>
        <textarea class="form-control" id="notes" name="notes" rows="3" maxlength="1000">{escaped(values.get('notes', ''))}</textarea>
    </div>
    """


def entry_form(entry):
    timetable_id = escaped(entry["timetable_id"])
    return f"""
    <form hx-post="{BACKEND_BASE}/timetable/update" hx-target="#form-result">
        <input type="hidden" name="timetable_id" value="{timetable_id}">
        {_entry_fields(entry)}
        <div class="d-flex gap-2">
            <button class="btn btn-primary" type="submit">Save changes</button>
            <a class="btn btn-outline-secondary" href="/">Cancel</a>
        </div>
        <div id="form-result" aria-live="polite"></div>
    </form>
    """


def _cal_suggestion_block(item, lane_index, total_lanes, username):
    window_start = CALENDAR_START_HOUR * 60
    window_end = CALENDAR_END_HOUR * 60
    start_min = max(item["_start_min"], window_start)
    end_min = min(item["_end_min"], window_end)
    if end_min <= start_min:
        return ""

    px_per_min = PX_PER_HOUR / 60
    top = (start_min - window_start) * px_per_min
    height = max((end_min - start_min) * px_per_min, 22)
    left = (lane_index / total_lanes) * 100
    width = (1 / total_lanes) * 100

    # Embed the full JSON payload (rather than per-field string interpolation) and HTML-escape
    # it as one unit, so free-text AI output containing quotes/ampersands can't break the
    # hx-vals JSON once the browser HTML-decodes the attribute.
    vals = json.dumps(
        {
            "username": username,
            "date": item["date"],
            "start_time": item["start_time"],
            "end_time": item["end_time"],
            "activity_name": item["activity_name"],
            "category": item["category"],
            "notes": item.get("notes", ""),
            "ai_generated": "1",
        }
    )
    # The "Add" button targets this inner body (not the outer positioned block) so the server's
    # generic add-entry confirmation can swap in without needing to know or preserve this block's
    # top/height/left/width - the outer .cal-entry keeps its position, only its contents change.
    body_id = escaped(item["_suggestion_id"])
    tooltip = escaped(f"Suggested: {item['activity_name']} ({item['start_time']} - {item['end_time']})")

    return f"""
    <div class="cal-entry cal-suggestion" title="{tooltip}"
         style="top: {top:.1f}px; height: {height:.1f}px; left: calc({left:.3f}% + 2px); width: calc({width:.3f}% - 4px);">
        <div class="cal-suggestion-body" id="{body_id}">
            <button type="button" class="cal-suggestion-add" title="Add to timetable" aria-label="Add suggestion to timetable"
                    hx-post="{BACKEND_BASE}/timetable" hx-target="#{body_id}" hx-swap="innerHTML"
                    hx-vals='{escaped(vals)}'>
                <i class="bi bi-plus-circle-fill" aria-hidden="true"></i>
            </button>
            <span class="cal-entry-title"><i class="bi bi-stars" aria-hidden="true"></i> Suggested: {escaped(item['activity_name'])}</span>
            <span class="cal-entry-time">{escaped(item['start_time'])} - {escaped(item['end_time'])}</span>
        </div>
    </div>
    """


def _plan_calendar(entries, suggested_entries, week_start, username):
    by_date = {}
    for entry in entries:
        enriched = dict(entry)
        enriched["_start_min"] = _to_minutes(entry["start_time"])
        enriched["_end_min"] = _to_minutes(entry["end_time"])
        enriched["_kind"] = "entry"
        by_date.setdefault(entry["date"], []).append(enriched)

    for index, item in enumerate(suggested_entries):
        enriched = dict(item)
        enriched["_start_min"] = _to_minutes(item["start_time"])
        enriched["_end_min"] = _to_minutes(item["end_time"])
        enriched["_kind"] = "suggestion"
        enriched["_suggestion_id"] = f"plan-suggestion-{index}"
        by_date.setdefault(item["date"], []).append(enriched)

    def render_day(date_iso):
        # Real entries and suggestions are lane-assigned together, so a suggestion that clashes
        # with an existing entry renders side-by-side with it instead of hiding one or the other.
        assignments, total_lanes = _assign_lanes(by_date.get(date_iso, []))
        return "".join(
            _cal_suggestion_block(item, lane_index, total_lanes, username)
            if item["_kind"] == "suggestion"
            # interactive=False: this preview is read-only apart from accepting suggestions -
            # the student's real entries show for context but can't be edited/deleted from here.
            else _cal_entry_block(item, lane_index, total_lanes, interactive=False)
            for item, lane_index in assignments
        )

    return _calendar_frame(week_start, render_day)


def plan_result(plan, username):
    source = "Reused recent plan" if plan.get("reused") else "Newly generated plan"
    suggestions = plan.get("suggested_entries") or []
    if suggestions:
        suggestion_note = f"""
        <div class="d-flex flex-wrap align-items-center justify-content-between gap-2 mb-3">
            <p class="small text-secondary mb-0">{len(suggestions)} suggested addition(s) shown with
                a dashed border and <i class="bi bi-stars"></i> - click the + on one to add it, or add them all.</p>
            <button type="button" class="btn btn-sm btn-primary"
                    onclick="document.querySelectorAll('#ai-plan-modal-body .cal-suggestion-add').forEach(b => b.click())">
                <i class="bi bi-check2-all" aria-hidden="true"></i> Add all suggestions
            </button>
        </div>
        """
    else:
        suggestion_note = (
            '<p class="small text-secondary mb-3">No new suggested blocks this time - '
            "your week already looks balanced.</p>"
        )
    calendar_html = _plan_calendar(plan.get("entries") or [], suggestions, plan["week_start"], username)
    return f"""
    <p class="fw-semibold mb-1"><i class="bi bi-stars text-primary" aria-hidden="true"></i> {source}</p>
    <p class="mb-2 preserve-lines">{escaped(plan['plan_text'])}</p>
    {suggestion_note}
    {calendar_html}
    """


def import_result(result):
    range_text = f"{result['week_start']:%d %b} - {result['week_end']:%d %b %Y}"
    due_found = result.get("due_found", 0)
    due_imported = result.get("due_imported", 0)
    due_skipped = result.get("due_skipped", 0)

    if result["found"] == 0 and due_found == 0:
        return (
            '<div class="alert alert-secondary mt-3" role="status">No events or due dates were '
            f"found in that calendar between {escaped(range_text)}.</div>"
        )

    parts = []
    if result["found"]:
        parts.append(
            f"Imported {result['imported']} of {result['found']} scheduled event(s) found between {range_text}."
        )
        if result["skipped"]:
            parts.append(
                f"{result['skipped']} were skipped because they clash with an entry already on your timetable."
            )
    if due_found:
        parts.append(
            f"Imported {due_imported} of {due_found} due date(s) (assignments/quizzes/exams) - "
            "shown above the calendar on the day they're due."
        )
        if due_skipped:
            parts.append(f"{due_skipped} were already on your timetable from an earlier import.")
    parts.append("Use the calendar's Previous/Next week buttons to see weeks other than the current one.")
    tone = "alert-success" if (result["imported"] or due_imported) else "alert-warning"
    return f'<div class="alert {tone} mt-3" role="status">{escaped(" ".join(parts))}</div>'


def advice_result(advice):
    return f"""
    <div class="alert alert-primary mt-3 ai-result">
        <p class="fw-semibold mb-1"><i class="bi bi-stars" aria-hidden="true"></i> Advice</p>
        <p class="mb-0 preserve-lines">{escaped(advice['advice_text'])}</p>
    </div>
    """
