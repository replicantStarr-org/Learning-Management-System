# Timetable Manager Feature Design

This document details the design for the timetable microservice and its 3 associated containers.
It follows the conventions set out in the [application design](../design.md) and mirrors the
structure of the [Subject Management](../subjects/design.md) and [Quiz Manager](../quizzes/design.md)
features.

The timetable feature lets a student manage their own weekly schedule (classes, study blocks,
work, and personal time) as an hour-by-hour calendar grid, and gives AI (Ollama) two roles:
generating an optimised weekly study plan grounded in real time-management research, and
answering on-demand time-management questions.

Ports (per the port assignment scheme in the [application design](../design.md), position 5):
frontend `3005`, backend `5005`, database `6005`.

The frontend is a multi-page Bootstrap 5 site (index/create/edit pages, a shared `navbar.html`
partial, and an `app.js` that prefills the student's username from a cookie and loads
query-param-driven edit fragments from the backend), matching the convention established by the
Subject Management and Quiz Manager frontends. The Learning Hub home page
(`access/frontend/index.html`) links to this feature with a "Timetable Manager" card, and the
shared navbar links back to the Learning Hub.

Data is scoped per student by a free-text `username` field (there are no numeric user IDs
anywhere in this application - `access`'s database keys users by `username TEXT`, and `quizzes`
scopes attempts the same way). The username is prefilled client-side from the `username` cookie
set by the access service, purely as a convenience - this app has no real access control, per the
top-level design's explicit note.

### Functionality Breakdown

- **Weekly calendar grid**: an hour-by-hour view (8am-11pm, one column per day) rather than a plain
  list, with previous/next week navigation and a "Today" button (disabled and highlighted when
  already viewing the current week, otherwise jumps straight to it). Entries are positioned by actual time and duration;
  empty time is simply blank grid space. Clicking an empty area of the grid jumps straight to the
  add-entry form with that day and a snapped-to-the-half-hour time slot pre-filled. Entries that
  overlap in time (rare, but possible from older data) render side-by-side in separate lanes
  rather than hiding one behind the other.
- **Create/edit/delete a timetable entry**: date, start/end time, activity name (optional -
  defaults to "Activity" if left blank), category, optional notes. The date defaults to today and
  the start time to 8am on a fresh add-entry form; the end time always defaults to one hour after
  whatever the start time currently is (recomputed live as the student changes the start time),
  rather than being left blank for the browser to improvise a value from the system clock.
- **No overlapping entries, ever**: creating or editing an entry that would overlap an existing
  one on the same day is rejected outright with a message naming what it clashes with. This is
  enforced in the backend service layer (`_find_clash`, using the same interval-overlap check the
  AI-suggestion filtering below also uses), not just suggested by the UI.
- **Generate an AI-optimised weekly plan**: opens a modal showing the student's real calendar with
  AI-suggested Study blocks overlaid in a distinct violet dashed style (never confused with a real
  category colour), each individually addable via a "+" button, plus an "Add all suggestions"
  button. The narrative above the calendar is built entirely in Python from computed facts (see
  *AI weekly plan design* below) - the model's only job is choosing where to place Study blocks.
  Real entries shown in this preview are read-only (no edit/delete, no click-to-create) - the
  modal is a review-and-accept surface, not another place to edit the timetable.
- **Time-management advice**: an optional free-text question, answered using the student's current
  week as context. If the question is specifically about wanting more/better study time, the
  advice also points the student to the Quiz Manager (practice quizzes) and this feature's own
  "Generate optimised plan" button.

- **Import a schedule from iCal**: a "Import from iCal" modal takes any `.ics` URL (or `webcal://`,
  normalised to `https://`) - e.g. a university's published class schedule, or a Google
  Calendar/Outlook export - and imports the events it finds over the next `IMPORT_RANGE_WEEKS`
  weeks (default 16, roughly a semester) into the student's timetable. A real class-schedule feed
  is one weekly-recurring `VEVENT` per class rather than one row per week, so recurrence
  (`RRULE`/`RDATE`/`EXDATE`) is expanded with `recurring-ical-events`. Only the current calendar
  week was originally imported, which meant a recurring schedule with no occurrence landing in
  that specific week (e.g. imported outside term, or on a day the recurrence skips) reported "0
  events found" and left the timetable looking empty despite the feed being valid - importing a
  forward-looking multi-week range instead of a single week fixes that; the student then browses
  to other weeks with the grid's own Previous/Next buttons to see what was imported there. Each
  parsed occurrence is created through the same `create_entry` path as a manual entry, so the same
  validation and no-overlap enforcement applies - an occurrence that clashes with an entry already
  on the timetable (including one from an earlier import of the same feed, making re-import a safe
  no-op) is skipped, not force-inserted. The import URL is validated against obvious SSRF targets
  (`services/ical_client.py::_is_unsafe_host` - literal `localhost`/private/loopback/link-local
  addresses) and capped at 5MB.

  This app has no per-user timezone concept anywhere (usernames are free text, not real accounts -
  see the top-level note on access control), so every imported time has to be converted to one
  assumed student timezone, `IMPORT_TIMEZONE` (default `Australia/Sydney`). How a source feed
  expresses time varies: some events carry a named zone (`DTSTART;TZID=...`), and some feeds omit
  `VTIMEZONE` entirely and give an absolute UTC instant instead (confirmed directly against a real
  UTS Canvas export: `DTSTART:20260810T030000Z`, no `TZID` anywhere in the file). Both cases are
  handled the same way - explicit conversion with `zoneinfo` (DST-aware, unlike a fixed offset) to
  `IMPORT_TIMEZONE` - rather than assuming the source's own encoding already matches the target
  and just stripping tzinfo, which only happens to produce the right wall-clock time for the TZID
  case. A truly floating/naive `DTSTART` (no tzinfo at all) is left untouched, since there's
  nothing to convert.

  A real LMS export (confirmed directly against the same UTS Canvas feed) is mostly *not*
  scheduled class time - the large majority of it is assignment/quiz/exam due-date markers, which
  icalendar represents either as an all-day (date-only) `VEVENT` or as a timed `VEVENT` with
  `DTEND == DTSTART` (a single instant, not a range). Neither fits a block on the hourly grid, but
  a due date is still real information worth importing, so both shapes are collected separately
  (`ical_client.parse_events` returns `(timed_events, due_events)`) and imported as `all_day=True`
  entries under a new `Assessment` category - stored as `00:00`-`23:59` purely so the existing
  `start_time`/`end_time NOT NULL` schema doesn't need touching, but never treated as occupying
  that range: `_find_clash` ignores `all_day` rows entirely (in both directions - an all-day entry
  can't clash with anything, and can't be clashed with), and `get_or_create_plan` explicitly
  filters them out of `entries` before any free-time/balance calculation, or every day with a due
  date would look completely full to the AI weekly planner. `create_advice` deliberately does
  *not* filter them out - `_entries_to_text` instead describes them as `DUE - <name>` rather than
  a fake `00:00-23:59` time range, so the model gets genuinely useful context ("what should I
  prioritise this week") without being misled into treating the whole day as booked.

  Due-date entries never clash-check on creation, so re-importing the same feed needs its own
  duplicate guard (`_find_duplicate_due` - same username/date/activity name) instead, or every
  re-import would pile up fresh copies. Rendered as a slim banner row of pills above the hourly
  grid, one per day (`_calendar_frame`'s `render_due` - Google-Calendar-style), which is only
  rendered at all when at least one day in the week actually has one, so a week with nothing
  imported looks exactly as it did before this existed. Each pill shows the full title (wrapped
  over up to 3 lines, not truncated to one - real due-date titles from a source feed can be long)
  plus edit and delete actions, matching the actions available on a normal hourly-grid entry.
  Editing one through the generic edit form works, but only its `date` field meaningfully affects
  anything - `start_time`/`end_time` stay editable in the form (they're stored as `00:00`-`23:59`,
  see above) and `category` still offers the full category list, but neither has any visible
  effect, since whether something renders as a due-date pill vs. an hourly block depends only on
  the `all_day` flag, which the edit form never changes. The iCal import modal's own "Import as
  category" dropdown deliberately excludes `Assessment` (it only applies to timed events - due
  dates always get `Assessment` regardless of what's selected there). Due-date entries are also
  never shown in the AI-plan preview modal - `get_or_create_plan` filters `all_day` entries out of
  `entries` before `_plan_calendar` ever sees them (see *AI weekly plan design* below), so a
  student opening that modal during a week with due dates won't see them there, only on the main
  grid.

Both AI actions show a live "Ns elapsed" counter while running (generation is CPU-only on this
hardware and can take one to a few minutes) instead of a static "please wait" message.

Appropriate validation is implemented first as frontend input constraints (`required`,
`maxlength`, `type="date"`/`type="time"`), then repeated on the backend: date must be a valid ISO
date, times must be in `HH:MM` format with start before end and no overlap with an existing entry,
category must be one of `Class | Study | Personal | Work | Assessment | Other`, and activity
name/notes have length limits. (`Extracurricular` was removed as a category - `Personal` covers
that case, and having two categories for essentially the same kind of time made the category list
confusing without adding anything the AI-balance calculation below could use differently.
`Assessment` was added later, specifically for all-day due-date entries imported from iCal - see
*Import a schedule from iCal* below - and isn't manually selectable in a meaningful way since the
create/edit forms don't expose an "all day" toggle.)

### Cross-feature integration

None for reading/writing timetable data. The AI context for both the weekly plan and advice is
built purely from the student's own timetable entries. Pulling in the Subjects (or a future
Assignments) database to ground AI output in external data is a retrieval/grounding concern, which
the project specification places in **Release 1 (RAG)**, not Release 0 - so it is intentionally
out of scope here rather than a missing integration. The one exception is informational: the AI
advice feature's system prompt can point a student towards the Quiz Manager by name when relevant,
without querying its service.

### Backend/API Functions

- `GET /timetable` - the current (or `?week_start=`-selected) week's timetable, as a calendar-grid
  fragment
- `GET /timetable/{id}` - a single timetable entry
- `GET /timetable/{id}/edit` - edit form fragment for a timetable entry
- `POST /timetable` - create a timetable entry (rejected with 409 if it overlaps an existing one)
- `POST /timetable/update` - edit a timetable entry (HTMX form convention, id in the request body;
  same overlap check, excluding the entry being edited)
- `POST /timetable/delete` - delete a timetable entry
- `POST /timetable/ai-plan` - generate or reuse the AI-optimised weekly plan
- `POST /timetable/ai-advice` - request AI time-management advice
- `POST /timetable/import-ical` - import events from an external iCal URL over the next
  `IMPORT_RANGE_WEEKS` weeks (default 16)

The **database service** exposes the equivalent REST resource directly (`GET/POST/PUT/DELETE
/timetable/<id>`, plus `/timetable/plans*` and `/timetable/advice`), matching the
`subjects`/`quizzes` convention of a JSON CRUD API at the database layer and an HTMX-form-friendly
flat-route layer at the backend.

### Database Tables

- `timetable_entries` - username, date, day_of_week (auto-derived from date), start_time,
  end_time, activity_name, category, notes, ai_generated flag, last_updated (auto-updated by a
  trigger, same pattern as `subjects.last_update`)
- `ai_timetable_plans` - one evolving row per student: username, plan_text, `suggested_entries`
  (JSON-encoded list, so a reused/cached plan can still show the same suggestions it originally
  generated instead of always reporting none), created_at, regenerated_at (set each time the plan
  is refreshed)
- `ai_advice_logs` - append-only history: username, question, advice_text, created_at

Seeded with 16 timetable entries across 3 students (dates computed relative to the current week so
the demo data is always "this week"), 10 AI plan rows, and 10 AI advice log rows (see
`database/init_db.py`), satisfying the 10-row-per-table minimum. Seed data contains no overlapping
entries and no `Extracurricular` category (verified by hand against the current validation rules).

### AI weekly plan design: grounded, not free-form

Two rounds of real testing exposed the same underlying problem from different angles: small/medium
local models are unreliable at multi-item reasoning over a raw list of timetable entries. Observed
failures included inventing a clash that didn't exist, skipping an entirely free day when placing
suggestions, padding free time with generic "relax"/"break" blocks instead of leaving it open, not
reliably hitting a requested numeric total, and a narrative that described suggestions no longer
present after budget filtering. The fix for all of these was the same pattern, applied
consistently: **compute the fact in Python, hand it to the model as ground truth, and re-verify
the model's output against that same computation afterwards rather than trusting instructions were
followed.**

Concretely, `timetable_service.py` computes, before ever calling the model:

- **Free time per day** (`_free_intervals_by_day`) - exact gaps within the 8am-11pm window, per day,
  including flagging a day with zero entries as `ENTIRELY FREE`.
- **Time clashes** (`_detect_clashes`) - exact pairwise overlap check across the week's entries,
  using the same `_times_overlap` logic that guards entry creation.
- **Weekly study/work balance** (`_weekly_balance`), grounded in real research rather than an
  arbitrary flat percentage of the week:
  - The **"2-hour rule"**: roughly 2 hours of independent study per 1 hour of class time. This is
    the US Department of Education's credit-hour standard (1 credit = 1h instruction + a minimum
    of 2h outside work/week) and the guideline most university academic-success programs use.
    Anchoring the target to the student's own logged Class hours (`target_study = 2 x class_hours`)
    means it scales with actual course load instead of an arbitrary number - a student with 2
    classes doesn't get the same target as one with 6. ([Study Time Per Credit Hour: What Research
    Shows](https://www.formulaforge.org/education/study-time-per-credit-research); NSSE research
    cited there finds the average student studies only 10-13h/week regardless of course load, well
    under this benchmark, but students who do hit it earn significantly higher GPAs.)
  - **Paid work**: research on working students finds 10-15h/week ideal, 15-20h "manageable," and
    a clear decline in academic performance above roughly 30h/week
    ([Understanding the Impacts of Employment on Students'
    Lives](https://pdxscholar.library.pdx.edu/cgi/viewcontent.cgi?article=1016&context=honors_fac)).
    This can't be turned into a suggestion (the tool shouldn't invent or remove work shifts), so
    it's surfaced as an informational note in the narrative when a student's logged Work hours
    reach that threshold.
  - A student far below target could have a genuine gap of many hours - asking the model to close
    all of it in one response would mean suggesting blocks across nearly all remaining free time
    (defeating the point of leaving free time unscheduled). A single generation is capped at 4
    Study blocks totalling at most 4 hours, framed explicitly as one incremental step when the full
    gap is larger than that.

The model is given these three sections (`COMPUTED FREE TIME PER DAY`, `COMPUTED TIME CLASHES`,
`COMPUTED WEEKLY BALANCE`) as verified facts and told to defer to them rather than re-derive any of
them. Its **only remaining job is choosing where to place the Study blocks** the balance
calculation calls for - it no longer writes any narrative text, and only `category: "Study"`
suggestions are requested (never a generic "relax"/"leisure" filler - free time is meant to stay
genuinely unscheduled).

Everything the model returns is still re-verified rather than trusted:

- `_drop_clashing_suggestions` removes any suggestion that overlaps a real entry or another
  suggestion in the same batch (defensive - the model doesn't always respect "don't overlap"
  either).
- Only `category == "Study"` suggestions survive filtering, regardless of what the prompt asked
  for.
- `_diversify_by_day` reorders accepted suggestions to interleave across distinct days before
  `_trim_to_budget` runs, so the count/time budget is spent covering multiple days (especially any
  `ENTIRELY FREE` one) rather than exhausted on the model's first-listed day.
- `_trim_to_budget` enforces the 4-block/4-hour cap in code (observed: asked for "about 4.0h," the
  model returned 7h across 4 blocks) - it keeps suggestions in order up to the budget, always
  keeping at least one even if it alone exceeds it.

Finally, **the narrative shown to the student is built entirely in Python**
(`_build_plan_narrative`) from these same computed facts plus the *final* (filtered, diversified,
trimmed) suggestion list - never from AI-written prose. It follows a fixed structure: the
research-based optimal study time, the currently-allocated amount, which days adjustments were
suggested on (explicitly calling out any entirely-free day that got covered, "to help spread study
sessions properly across the week"), a reminder that all other empty space is free time and
doesn't need filling, and - if the week is too full to fit the recommended amount - an honest note
that the optimal target is still worth stating even though only a partial suggestion could be
fit in. This removes AI narrative hallucination as a possibility entirely (there's no free-text
generation left to hallucinate in) and guarantees the described suggestion count/hours can never
drift out of sync with what's actually offered on the calendar, which is what AI-written narrative
prose was doing before this design.

A cached/reused plan re-runs this same filtering-and-narrative-building pipeline against the
*current* entries every time it's viewed (cheap - no AI call), rather than replaying whatever was
computed at generation time. A plan row saved before `suggested_entries` existed as a column has
it as `NULL` in the database (not `"[]"`), which is treated as "nothing usable to reuse" so it
self-heals into a fresh generation the first time it's next viewed, rather than silently serving a
plan with no suggestions forever.

### AI model choice and performance

The single AI-mode workflow (Frontend -> Backend/API -> Ollama -> LLM) for this feature uses
`llama3.1:8b` for both AI functions - the weekly plan needs reliable structured JSON output, which
the lighter `qwen2.5:0.5b` model used by the subjects feature was not reliable enough for in the
quizzes feature's own testing; the same reasoning applies here.

Measured directly against this container's Ollama instance (CPU-only, no GPU detected): ~5.2
output tokens/second, ~14 prompt tokens/second. Wall-clock time scales with how much text is
generated, so the practical levers - beyond swapping to a smaller/less-reliable model, which was
already ruled out - are asking for less output and bounding it:

- `OLLAMA_TIMEOUT_SECONDS=240` with `OLLAMA_MAX_RETRIES=0`. The OpenAI SDK retries a timed-out
  request twice more by default; a slow-but-working generation was being abandoned mid-way at the
  original 90s timeout and retried up to 3 times over, turning a real ~3 minute wait into a ~5
  minute failure. A longer timeout with no blind retries means a working generation gets the time
  it needs, and a genuine failure surfaces after one honest wait instead of three.
- The model now only returns a JSON array of suggestions (no narrative prose at all, per the
  design above), which is a much smaller realistic output than earlier iterations that asked for
  an 80-150 word narrative plus suggestions - `PLAN_MAX_TOKENS=250` is a generous ceiling for that.
- Both AI panels show a live elapsed-time counter and an honest "usually 1-2 minutes" / "usually
  under 1.5 minutes" estimate instead of a static message, since a multi-minute wait with no
  feedback reads as broken.

### Known Limitations

- The AI weekly plan and the balance calculation always operate on the *current* week (relative to
  today), regardless of which week is currently displayed in the grid.
- The model doesn't always fully use its suggestion budget efficiently (e.g. two 2-hour blocks
  instead of spreading across more, shorter ones) - the code-level diversification helps but can't
  force the model to propose more candidates than it does.
- `Assessment`/all-day entries can only be *created* via iCal import - the manual create/edit forms
  don't expose an "all day" toggle, so a manually-entered `Assessment` row would still need (and
  clash-check against) a real start/end time like any other category. They *can* be edited
  afterwards through the generic edit form, but as noted above only the `date` field has any real
  effect there.
- `POST /timetable/ai-plan` accepts a `force` flag to bypass the reuse cache and regenerate
  immediately, but nothing in the frontend ever sends it - the one "Generate optimised plan"
  button always omits it, so reuse-vs-regenerate is entirely automatic (governed by
  `PLAN_MAX_AGE_HOURS` and whether entries changed since the plan was last built, per *AI weekly
  plan design* above). `force` exists for a future "regenerate now" control, not a currently
  reachable one.

### Additional Notes

The timetable feature has a CI workflow (`timetable.yml`) mirroring the pattern described in
[the app design](../design.md): build images, smoke-check each container (database, backend,
frontend, in that order), and upload evidence reports.
