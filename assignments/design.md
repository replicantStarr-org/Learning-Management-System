# Assignments / Task Manager Feature Design

This document details the design for the assignment microservice and its 3 associated containers.
It follows the conventions set out in the [application design](../design.md) and the structure
established by the [Subject Management](../subjects/design.md) and
[Quiz Manager](../quizzes/design.md) features.

The assignment feature lets students record the assessment tasks for their subjects, track their
status, filter and search the list, see what is due next, and receive deadline notifications. Two
AI capabilities run against Ollama: summarising an assignment brief, and recommending learning
materials that help complete it.

Ports (per the port assignment scheme in the [application design](../design.md), position 3):
frontend `3003`, backend `5003`, database `6003`.

The frontend is a multi-page Bootstrap 5 site (`index`, `assignment`, `create`, `edit`, `upcoming`,
plus the shared `navbar.html` partial and an `app.js` that loads query-param-driven detail/edit
fragments), matching the convention set by the other features. The Learning Hub home page
(`access/frontend/index.html`) links to this feature with an "Assignment Tracker" card, and the
shared navbar links back to the Learning Hub.

### Functionality Breakdown

- View all assignments as cards showing subject, status, priority and a deadline badge that turns
  amber when work is due within three days and red once it is overdue.
- Filter the list by subject, status and priority, and search across title, description and
  subject. Filters compose (they are ANDed) and re-query as you type.
- View upcoming deadlines over a chosen window (3, 7, 14 or 30 days). Only unfinished work is
  listed, since submitted and graded work is no longer actionable.
- Receive deadline notifications. Every assignment carries reminders; a reminder becomes visible
  once its `remind_at` has passed and its assignment is still due, and can be dismissed. The
  notification panel re-polls every 60 seconds and immediately after any assignment change.
- Create, edit and delete assignments (full CRUD), including status, priority, weighting and the
  full requirements text.
- Generate an AI summary of an assignment's requirements: what is being asked for, which
  deliverables are marked, and the single thing most likely to cost marks. Cached after the first
  generation, and regenerated on demand.

### Cross-feature integration

Two read-only integrations, both best-effort - if either service is offline this feature keeps
working, it just loses some context:

- **Subject Management** - the subject dropdown and the AI's subject context come from
  `GET /subjects` and `GET /subjects/{id}` on the subjects **database** service (port 6001), per
  the top-level design's rule that cross-feature reads go through the owning feature's database
  service CRUD API. `subject_id`/`subject_name` are stored here only as a denormalised snapshot;
  the subjects feature still owns that schema.

### Backend/API Functions

The endpoints required by the feature specification, all implemented with the matching HTTP verb:

- `GET /assignments` - list assignments (`subject_id`, `status`, `priority`, `q` filters)
- `GET /assignments/{id}` - one assignment with its cached summary, recommendations and reminders
- `POST /assignments` - create
- `PUT /assignments/{id}` - update (partial updates allowed)
- `DELETE /assignments/{id}` - delete, cascading to its summaries, recommendations and reminders
- `GET /assignments/upcoming?days=N` - unfinished work due inside the window
- `POST /assignments/{id}/summary` - generate (or return the cached) AI summary; `?force=true`
  regenerates
- `POST /assignments/{id}/recommendations` - generate (or return the cached) recommendations

Plus the endpoints the UI needs: `GET /assignments/{id}/edit` (edit form fragment),
`GET /subjects/options` (subject dropdown), `GET /reminders` (notification panel) and
`POST /reminders/{id}/acknowledge` (dismiss).

Every route answers **JSON by default and an HTML fragment when the request carries HTMX's
`HX-Request` header**. One route table therefore serves both the REST API the specification asks
for and the hypermedia the frontend consumes, with no duplicated routing or validation. Because
HTMX does not swap non-2xx responses, errors are also split: API clients get the true status code
(400/404/422/503) with a JSON body, while HTMX gets HTTP 200 carrying an alert fragment and an
`HX-Error: true` header.

This is a deliberate change from the quiz feature, which used flat `POST /quizzes/update` and
`POST /quizzes/delete` routes because a plain HTML form cannot issue PUT or DELETE. Here the forms
are HTMX-driven (`hx-put`, `hx-delete`), so the resource-oriented verbs the specification lists are
used directly.

### Backend layering

```
backend/
├── app.py            # app factory, blueprint registration, app-wide error handlers
├── routes/           # HTTP concerns only: parse the request, call a service, pick a renderer
├── services/         # domain rules, validation, and one client per upstream dependency
└── views/            # HTML fragments + the JSON/HTML negotiation helpers
```

Routes never touch SQL, HTTP clients or the model; services never build HTML. Error handling is
registered once on the app rather than as a decorator per view, so a newly added route cannot leak
a stack trace by forgetting to opt in. `ServiceError` (the caller can fix it) and `UpstreamError`
(a dependency is down) are separated so the status codes stay honest: a bad due date is a 400, a
dead database service is a 503.

### Database Tables

- `assignments` - subject snapshot, title, description, requirements, `due_at`, status, priority,
  weighting, timestamps (with an update trigger, as in the subjects and quizzes features)
- `assignment_summaries` - cached AI summaries, one row per generation, with the model that
  produced it
- `assignment_recommendations` - AI-recommended materials, with `source_resource_id` set when the
  suggestion matched a real row in the Learning Resource Manager
- `assignment_reminders` - `remind_at`, message and an `acknowledged` flag, driving notifications

Seeded with 12 assignments, 12 summaries, 15 recommendations and 13 reminders (see
`database/init_db.py`), satisfying the 10-row-per-table minimum. Due dates are seeded **relative to
build time**, so the upcoming-deadline and notification screens always have live data to
demonstrate rather than a wall of past dates.

### AI model choice

Summaries are free text and run on `qwen2.5:0.5b`, the same fast model the subject feature uses.
Recommendations must come back as a fixed JSON shape, which that 0.5B model cannot produce
reliably - the quiz feature hit the same wall - so `llama3.1:8b` (also approved) is used there, via
the separate `OLLAMA_MODEL` variable in the compose file. Both are overridable per environment.

Both prompts treat the assignment text and the resource catalogue as untrusted data, refuse
embedded instructions, and answer with a fixed sentinel (`ASSIGNMENT_REQUEST_BLOCKED`) that the
service turns into a 422 rather than passing model output through. Free text that will reach the
model is additionally screened for known injection phrasings before the call is made, and every
model-supplied `source_resource_id` is checked against the real catalogue so a hallucinated id can
never become a link.

### Testing

`scripts/api_check.sh` drives the whole non-AI REST surface against a running stack: the seeded
catalogue size, filtering, upcoming, create, the automatically scheduled reminder, update,
rejected invalid input, 404 handling, delete, and a final count check that the fixture cleaned up
after itself. The CI workflow ([`assignments.yml`](../.github/workflows/assignments.yml)) runs it
after the HTTP smoke check, which is the "non-functional requirement validation script" hook the
top-level design leaves open. The AI endpoints are excluded because GitHub's runners have no
Ollama runtime; they are verified locally instead.

### Known Limitations

- Reminders fire on a schedule the user cannot edit: one reminder is created three days before the
  due date (or immediately, for work due sooner than that). There is no UI yet for adding extra
  reminders, though the database service already supports it.
- Notifications are polled every 60 seconds rather than pushed, so a reminder can appear up to a
  minute late. Server-sent events would fix this but are out of scope for Release 0.
- `qwen2.5:0.5b` summaries occasionally paraphrase the brief instead of adding insight, a quality
  limit of a very small model rather than a code defect. Setting `OLLAMA_SUMMARY_MODEL` to a
  larger approved model improves it where hardware allows.
- Editing an assignment does not live-refresh a detail page already open in another tab;
  re-opening it shows the update. The list and notification panel do refresh automatically via the
  `assignmentsChanged` HTMX trigger.

### Additional Notes

On Windows/Mac, `network_mode: host` (used across this whole repo) requires Docker Desktop's
"Enable host networking" setting (Settings > Resources > Network) to be turned on, plus a restart
of Docker Desktop; each container may also need one `docker restart` after that if its port isn't
immediately forwarded to the host. This is a Docker Desktop limitation rather than something
specific to this feature.
