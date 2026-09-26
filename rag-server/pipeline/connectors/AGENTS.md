# Writing a RAG connector

A connector tells the RAG server (`rag-server/`) what to index from one
Learning Hub service. Each service team owns its connector, one module in this
folder. Read this file in full before writing one.

`learning_resources.py` is a complete working example. The other modules are
stubs that only declare the service's name and URL.

## What your connector feeds

1. `POST /ingest` (or the MCP `ingest` tool) calls `ingest_services` in
   `pipeline/ingestion.py`.
2. For your service it calls `connector.records()`, which runs each of your
   entity functions and collects the `Record`s they yield.
3. Each record is rendered to text, split into chunks, embedded and upserted
   into ChromaDB. Chunks from an earlier run that are not produced again are
   deleted, so the index always mirrors what your connector yields now.
4. `POST /answer` retrieves the few chunks closest to a question and gives them
   to a small local LLM (`qwen2.5:0.5b`) as its **only** evidence.

**The text your records render to is everything the model will ever know
about your service.** Anything you leave out cannot be answered. Anything
ambiguous will be answered badly.

The RAG server runs on the host, not in Docker. It reaches your service's
database API on `localhost` using the port scheme in the root `design.md`
(database services use 6000–6005).

## The contract

```python
from ..connector import Connector, Record, pick

connector = Connector("quizzes", "http://localhost:6004")  # already in your stub


@connector.entity
def quizzes(get):
    for row in get("/quizzes"):
        yield Record(
            entity="quiz",
            id=row["quiz_id"],
            title=row["title"],
            fields=pick(row, "subject_name", "title", "difficulty", "description"),
        )
```

The module must define a module-level `connector`. Every module in this folder
is discovered automatically; nothing else needs registering.

| Piece | Meaning |
|---|---|
| `Connector(name, base_url)` | `name` identifies your service everywhere: `{"service": "quizzes"}` in API calls, chunk IDs and metadata. It is already set in your stub; **do not rename it**, or chunks indexed under the old name are orphaned. `base_url` is your database API on `localhost`. |
| `@connector.entity` | Registers a function that yields records for one kind of thing. Add one per entity, in any number. A connector with no entity functions is reported as `skipped` and its index is left untouched. |
| `get(path, **params)` | Passed to every entity function. Sends `GET base_url + path` with `params` as the query string, and returns the parsed JSON. Raises on a non-2xx response or after a 10 second timeout. Use it for every request; do not import `requests` yourself. |
| `Record.entity` | A singular, snake_case noun: `quiz`, `quiz_question`, `timetable_entry`. Its label (underscores to spaces, capitalised) starts every chunk: `Quiz question: …`. |
| `Record.id` | The row's primary key. It must be **stable across runs and unique within the entity**. Chunk IDs are `{service}:{entity}:{id}:{n}`, so an ID that changes between runs makes every ingest delete and re-add the record. |
| `Record.title` | A short human name, shown in citations and at the top of every chunk. Put the words people search by in it: code and name, or owner, activity and day. |
| `Record.fields` | A dict rendered **in insertion order**; see below. |
| `pick(row, *keys)` | `{key: row[key]}` for the listed keys, in that order. A missing key raises `KeyError` on purpose, so a renamed column fails the ingest instead of silently dropping the field. |

## How fields become text

Real output of the renderer (`render` in `pipeline/ingestion.py`):

```python
Record(entity="quiz", id=7, title="Intro to DevOps", fields={
    "subject_name": "ASD101 - Advanced Software Development",
    "difficulty": "Easy",
    "due_at": None,
    "tags": ["core", "week 1"],
    "author": {"name": "Dr. Georges", "email": ""},
    "questions": [
        {"question": "What does CI stand for?", "answer": "Continuous Integration"},
        {"question": "What is a container?", "answer": "An isolated process with its own filesystem"},
    ],
})
```

```text
Quiz: Intro to DevOps
subject name: ASD101 - Advanced Software Development
difficulty: Easy
tags: core; week 1
author:
  name: Dr. Georges
questions:
- question: What does CI stand for?
  answer: Continuous Integration
- question: What is a container?
  answer: An isolated process with its own filesystem
```

- Keys have `_` replaced by a space. Name keys the way a person would say them,
  because the words in them are searchable.
- `None`, `""` and `[]` are skipped, as `due_at` and `email` are above.
- A list of plain values is joined with `; ` (values often contain commas).
- A dict is indented under its key.
- In a list of dicts, each item is one block. A record longer than
  `chunking.max_words` (150, in `rag-server/config.toml`) is split into several
  chunks, but only **between** top-level fields or list items, never inside one.
- Values are printed with `str()`. Convert anything that reads badly first:
  `1`/`0` flags to `"yes"`/`"no"`, cents to dollars, ISO timestamps you only need
  the date of.

## Rules

These are not negotiable:

1. **Read only through your service's HTTP API, using `get`.** Never open a
   SQLite file and never import your service's code. `design.md` forbids direct
   querying, and the files live in Docker volumes the RAG server cannot see.
2. **GET requests only.** Ingestion must never change data.
3. **Let errors raise.** Do not wrap requests or parsing in `try/except` to
   carry on with partial data. A raised exception fails your service's ingest
   and keeps its previous chunks intact. Swallowing it and yielding fewer
   records makes ingestion **delete** the ones you skipped.
4. **Be deterministic.** The same data must give the same records: no current
   time, no randomness, no ordering that changes between runs.
5. **Never index secrets:** password hashes, tokens, API keys, session data.
6. **Do not index AI-generated content** (summaries, advice, generated plans).
   The model would cite its own earlier output as evidence. Index the source
   data those were generated from.
7. **Only edit your own connector module.** Everything in `pipeline/` outside
   this folder (`connector.py`, `ingestion.py`, `vectors.py` and the rest) is
   shared by every service. If you need a framework change, raise it instead of
   making it in a connector PR.

## Guidance

- **One record per thing a question is about.** If people ask about individual
  children of an entity (the questions in a quiz), yield each child as its own
  record as well as the parent. Repeat the parent's identifying fields (quiz
  title, subject) in each child. The small model often answers from the wrong
  item when one chunk holds several similar ones; small, specific records fix
  that.
- **Keep records under ~150 words.** Anything longer is split, and a later
  chunk carries only the header line for context.
- **Choose fields a user would ask about.** Drop internal and foreign key IDs,
  `created_at`/`last_update`, file paths and anything only the UI uses.
- **Resolve references.** `subject_id: 3` means nothing to a search. Include the
  subject's name if your API returns it; the RAG server must not query another
  team's service to look it up.
- **Per-user data:** include the username in both `title` and `fields`, so
  "what does alex.wong have on Tuesday?" matches. The design gives every user
  access to everything, so there is no filtering to do.
- **List, then detail.** If your list endpoint omits fields you need, call the
  detail endpoint per item. One request per record is fine at this scale.
- **Missing endpoint? Add it to your own service.** If you cannot list what you
  need (for example, every username), add a `GET` endpoint to your database
  service. Do not hard-code data into the connector.
- **Comment surprises.** When the API does something non-obvious (a list that
  omits a field, rows returned as arrays), say so in a comment at that call.

## Patterns

```python
@connector.entity
def things(get):
    # List, then detail: the list omits `description`.
    for row in get("/things"):
        thing = get(f"/things/{row['thing_id']}")
        yield Record("thing", thing["thing_id"], thing["name"],
                     pick(thing, "name", "owner", "description"))


@connector.entity
def entries(get):
    # Fan-out: entries are only served per user.
    for user in get("/users"):
        for entry in get("/entries", username=user["username"]):
            yield Record("entry", entry["entry_id"], f"{user['username']}: {entry['name']}",
                         pick(entry, "username", "name", "date"))


@connector.entity
def parents(get):
    # Children as their own records, repeating the parent's context.
    for parent in get("/parents"):
        yield Record("parent", parent["parent_id"], parent["title"],
                     pick(parent, "title", "summary"))
        for number, child in enumerate(parent["children"], start=1):
            yield Record("parent_child", child["child_id"], f"{parent['title']}, item {number}",
                         {"parent": parent["title"], **pick(child, "text", "detail")})
```

For an endpoint added to a service just so its connector can read what it
needs (there, each resource with its tags), see `learning_resources.py` and
`GET /api/resources/catalogue` in the learning resource manager.

## Testing your connector

Run these from `rag-server/`, with your service running (`docker compose up -d` in
your service's folder).

1. **Set up once:** `./init.sh` (Linux/macOS) or `./init.ps1` (Windows). On
   Windows, replace `.venv_rag/bin/python` below with
   `.venv_rag\Scripts\python.exe`.
2. **Preview the chunks** without touching the index:

   ```bash
   .venv_rag/bin/python -c "
   from pipeline.connector import connectors
   from pipeline.ingestion import record_chunks
   for record in connectors()['YOUR_SERVICE'].records():
       for chunk in record_chunks('YOUR_SERVICE', record, ''):
           print(chunk['id']); print(chunk['text']); print()
   "
   ```

   Read the output as the model will. Could it answer your users' questions
   from this text alone?
3. **Ingest** with the server running (`./run.sh`, or `./run.ps1` on Windows).
   It is reached at `server.url` in `rag-server/config.toml`,
   `http://localhost:5010` by default:

   ```bash
   curl -X POST localhost:5010/ingest -d '{"service": "YOUR_SERVICE"}'
   ```

   Expect `"status": "success"` and a non-zero `chunk_count`. The server loads
   connectors once, so **restart it after every change to your connector**.
4. **Retrieve and answer:** ask a question a user would ask.

   ```bash
   curl -X POST localhost:5010/retrieve -d '{"query": "...", "service": "YOUR_SERVICE"}'
   curl -X POST localhost:5010/answer -d '{"query": "..."}'
   ```

   The right chunk should be in the top three, and the answer should be correct.
5. **Add benchmarks** to `BENCHMARKS` in `rag-server/eval.py`: two or three
   questions, each with the chunk ID prefix of the record that answers it, e.g.
   `"quizzes:quiz_question:2:"`. Run `.venv_rag/bin/python eval.py` and check
   that R@5 is 1.0 for yours.
6. **Run the automated review** of your connector, with your service still
   running. From `agentic_loop/`:

   ```bash
   ./run.sh --skip-report-download --area rag --service YOUR_SERVICE_KEY
   ```

   Service keys are `subjects`, `assignments`, `resources`, `quizzes` and
   `timetable`. It checks the rules above statically, runs your connector
   twice to check the output is identical, and has two local models review the
   result. Fix every `FAIL` line it reports.

## Done when

- [ ] Every entity a user could ask about has an entity function.
- [ ] The preview reads clearly with no IDs, secrets, AI output or raw flags.
- [ ] `POST /ingest` for your service returns `success`.
- [ ] Your benchmarks in `rag-server/eval.py` reach R@5 = 1.0.
- [ ] The agentic loop's RAG review of your connector reports no `FAIL` lines.
- [ ] Only your connector module and `rag-server/eval.py` changed, plus any `GET`
      endpoints you added to your own service.
