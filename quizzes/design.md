# Quiz / Knowledge Check Manager Feature Design

This document details the design for the quiz microservice and its 3 associated containers.
It follows the conventions set out in the [application design](../design.md) and mirrors the
structure of the [Subject Management feature](../subjects/design.md).

The quiz feature lets students browse quizzes, take them, review their results (including
explanations for incorrect answers), and view their attempt history. AI (Ollama) can generate a
new practice quiz for a subject on demand, and can generate personalised feedback on a completed
attempt's mistakes.

Ports (per the port assignment scheme in the [application design](../design.md), position 4):
frontend `3004`, backend `5004`, database `6004`.

The frontend is a multi-page Bootstrap 5 site (index/quiz/edit/create/generate pages, a shared
`navbar.html` partial, and an `app.js` that loads query-param-driven detail/edit fragments from the
backend), matching the convention established by the [Subject Management feature](../subjects/design.md)
frontend. The Learning Hub home page (`access/frontend/index.html`) links to this feature with a
"Quiz Manager" card, and the shared navbar links back to the Learning Hub.

### Functionality Breakdown

- View available quizzes (title, subject, difficulty, question count, AI-generated vs manual).
- Take a quiz: select one answer per question and submit as a single attempt.
- View quiz results immediately after submitting: score, and for every incorrect answer, the
  correct answer plus its explanation.
- View previous attempts for a quiz (student name, score, completion time).
- Generate an AI practice quiz for a subject: choose difficulty (Easy/Medium/Hard) and number of
  questions (3-10), with an optional free-text topic hint. The AI-generated questions, options,
  correct answers, and explanations are all stored as a normal quiz.
- Generate AI feedback on an attempt's incorrect answers (cached on the attempt after first
  generation, mirroring the summary-caching approach used by the subjects feature).
- Manage quizzes (CRUD): create a quiz manually, add questions to it, edit its title/description/
  difficulty, and delete it.

### Cross-feature integration

Per the top-level design's integration rule, quiz generation reads subject context directly from
the Subject Management feature's **database** service (`GET /subjects/{id}` on port 6001), never
through its backend or database directly-coupled. If that service is unreachable, generation still
works using a generic subject placeholder so the quiz feature can be developed and demoed
independently - but see Known Limitations below.

In Release 1 the quiz feature is connected to the shared RAG and MCP servers (see *Release 1: RAG*
and *Release 1: MCP* below). Both read quiz data through this feature's database API; neither
changes the Release 0 quiz pages, quiz generation or attempt feedback.

### Backend/API Functions

The backend uses resource-oriented paths and HTTP verbs for CRUD:

- `GET /quizzes` - list all quizzes
- `POST /quizzes` - create a quiz
- `GET /quizzes/{id}` - quiz details (renders the take-quiz form)
- `PUT /quizzes/{id}` - update quiz metadata
- `DELETE /quizzes/{id}` - delete a quiz
- `GET /quizzes/{id}/questions` - list a quiz's questions
- `POST /quizzes/{id}/questions` - add a question
- `GET /quizzes/{id}/questions/{question_id}` - get one question
- `PUT /quizzes/{id}/questions/{question_id}` - update a question
- `DELETE /quizzes/{id}/questions/{question_id}` - delete a question
- `POST /quizzes/{id}/attempts` - submit a quiz attempt
- `GET /quizzes/{id}/attempts` - previous attempts for a quiz
- `GET /attempts/{id}` - get a submitted attempt
- `GET /attempts/{id}/feedback` - read cached AI feedback
- `POST /attempts/{id}/feedback` - create/fetch AI feedback for an attempt
- `POST /quiz-generations` - create an AI-generated quiz from a subject ID
- `POST /subjects/{id}/quiz-generations` - create an AI-generated quiz for a subject
- `GET /rag/status` - whether RAG integration is enabled (`RAG_ENABLED`); always answers
- `GET /rag/health`, `POST /rag/retrieve`, `POST /rag/answer`, `POST /rag/ingest`,
  `POST /rag/clear` - relayed to the shared RAG server for the `quizzes` service only (JSON, see
  *Release 1: RAG*); each returns 403 when RAG is disabled
- `GET /mcp/status` - whether MCP integration is enabled (`MCP_ENABLED`); always answers
- `POST /mcp/quizzes`, `POST /mcp/quiz`, `POST /mcp/practice`, `POST /mcp/search` - call the
  matching quiz tool on the shared MCP server and return its structured result (JSON, see
  *Release 1: MCP*); each returns 403 when MCP is disabled

Edit forms are alternate HTML representations of the resources, selected with
`GET /quizzes/{id}?view=edit` and `GET /quizzes/{id}/questions/{question_id}?view=edit`.
Subject options are served from `GET /subjects`.

### Database Tables

- `quizzes` - subject, title, description, difficulty, question_count, source (manual/ai_generated)
- `quiz_questions` - question text + explanation per quiz
- `quiz_answers` - answer options per question, with an `is_correct` flag
- `quiz_attempts` - student name, score, total_questions, cached `ai_feedback`, timestamps
- `quiz_responses` - the answer selected for each question in an attempt, and whether it was correct

Seeded with 10 quizzes, 42 questions, 168 answers, 12 attempts, and 50 responses (see
`database/init_db.py`), satisfying the 10-row-per-table minimum.

### AI model choice

The subject-QA/summary features use `qwen2.5:0.5b` for fast, cheap completions. Quiz generation
needs reliable structured JSON output (a list of questions with 4 options and a correct index),
which that 0.5B model could not produce consistently in testing - it would echo the literal JSON
schema example back rather than generating content. `llama3.1:8b` (also an approved model) is used
instead for `generate_quiz_questions`, and reliably produces valid, on-topic questions in ~10-30s
per quiz. Attempt feedback still uses the default lightweight model since it only needs free text.

### Release 1: RAG

The quiz feature is indexed by the shared, non-containerised RAG server (`rag-server/`,
`http://localhost:5010`), and the RAG Tools page (`rag.html`) reaches it through the backend. It is
a study assistant for the student: ask what a term means, why an answer is right, or which quiz
covers a topic, and get an answer grounded in the quiz questions and their explanations.

**Request flow:** Frontend (`rag.html`) -> Backend/API (`/rag/*`, `routes/rag.py`) -> RAG client
(`services/rag_client.py`, always sends `"service": "quizzes"`) -> RAG server -> ChromaDB retrieval
-> local LLM (`llama3.1:8b` via Ollama) for `/answer` -> back the same way. The page shows the
answer, a confidence badge (High/Medium/Low/None), how many records were used, and the cited
sources; a quiz source links to that quiz.

**Knowledge sources:** the connector (`rag-server/pipeline/connectors/quizzes.py`) reads the quiz
database API (`GET /quizzes`, `GET /quizzes/{id}`) and yields two kinds of record, 52 chunks from
the seed data:

| Entity | One record per | Fields |
| --- | --- | --- |
| `quiz` | quiz | title, subject, difficulty, description, number of questions, question texts |
| `quiz_question` | question | quiz, subject, question, answer options, correct answer, explanation |

Each question is its own record, repeating its quiz and subject, so "what is the answer to X" is
answered from that question rather than a neighbour in the same quiz. Deliberately not indexed:
quizzes with `source = ai_generated` (the model wrote every question, and would cite its own output
back as evidence), and attempts, since other students' scores are no help for self-study and are
not for others to search.

**Grounding and insufficient context:** the RAG server only gives the model the retrieved chunks.
If nothing is within the retrieval distance threshold it returns `Insufficient evidence.` with no
citations and confidence `None` without calling the model, and the page shows an insufficient-context
message instead of an answer.

**Validation:** five study-question benchmarks in `rag-server/eval.py` (a question's correct answer,
a concept, a "why" answered from an explanation, a "how do I" and which quiz covers a topic) all pass
at the P@5 ceiling with R@5 = 1.0.
The shared agentic loop's RAG mode (`--area rag --service quizzes`) checks the connector statically
and live, and reports the benchmarks; its output is in
`agentic_loop/runs/rag-review-for-quiz-manager.txt`. `scripts/rag_endpoint_test.sh` validates the
RAG server and every `/rag/*` route from the terminal, including a grounded and an
insufficient-context answer.

**Configuration:** `RAG_SERVER_URL` in `docker-compose.yml` (`http://localhost:5010`) and
`RAG_ENABLED` (default `true`). CI runs with `RAG_ENABLED=false`; `/rag/status` then reports
disabled and `/rag/answer` returns 403, which `quizzes.yml` asserts.

### Release 1: MCP

Release 1 registers four quiz study tools on the shared, non-containerised MCP server (`mcp/`,
`http://127.0.0.1:8000/mcp`, Streamable HTTP), which the MCP Tools page (`mcp.html`) runs through
the backend. They are for a student studying on their own: find a quiz, read its questions, revise
a topic, or practise one question at a time.

**Request flow:** Frontend (`mcp.html`) -> Backend/API (`/mcp/*`, `routes/mcp.py`) -> MCP client
(`services/mcp_client.py`) -> MCP server -> quiz tool (`mcp/quizzes_tools.py`) -> quiz database API
-> back the same way. The backend checks the request (a positive quiz ID, a known difficulty, a
non-blank keyword), calls exactly one tool, and returns `{status, tool, arguments, result}`; the
page shows a readable view of `result` with the raw tool result folded beneath it.

| Tool | Inputs | Result |
| --- | --- | --- |
| `quizzes_list` | optional `subject` (part of name or code), optional `difficulty` (Easy/Medium/Hard) | quiz summaries |
| `quizzes_get` | `quiz_id` | one quiz with every question, its options, correct answer and explanation |
| `quizzes_practice_question` | optional `subject`, optional `difficulty` | one random question with its options, correct answer and explanation (MCP-only) |
| `quizzes_search_questions` | `keyword` | up to 25 questions whose text, answers or explanation contain it (MCP-only) |

The page keeps answers hidden until the student asks for them: the quiz lookup has a Show answer
button per question (and Show all answers), and the practice question is answered first, then
checked, showing whether it was right and the explanation. Buttons rather than hover, so it works
on touch screens and from the keyboard.

**Tool boundaries:** every tool is read-only and about the study material. None returns attempts,
student names or scores, so no student can look up another's results (there is no login, so a name
could not be trusted anyway). No tool can create, edit or delete a quiz, submit an attempt or run AI
generation; those stay on the pages, behind the backend's validation. The tools read the database
API rather than the backend because the backend's routes return HTML for the pages. Bad input is
refused with an MCP tool error rather than an empty result: a non-positive or missing quiz ID, an
unknown difficulty, a subject with no quizzes and a blank or over-long keyword. The backend turns a
refused tool call into a 400 and an unreachable MCP server into a 503.

**Validation:** `mcp/test_tools.py quizzes` calls every quiz tool in-process, and the shared agentic
loop's MCP mode (`--area mcp --service quizzes`) cross-checks the tools against each other over the
running server: difficulty filters match the full list, every correct answer is one of its options,
practice questions honour their filter, a search finds the question its keyword came from, no tool
returns attempt or student data, each bad input above is refused, and no write tool is advertised. Its output is in
`agentic_loop/runs/mcp-review-for-quiz-manager.txt`. `scripts/mcp_endpoint_test.sh` validates
every `/mcp/*` route and its boundaries from the terminal.

**Configuration:** `MCP_SERVER_URL` in `docker-compose.yml` (`http://127.0.0.1:8000/mcp`) and
`MCP_ENABLED` (default `true`). CI runs with `MCP_ENABLED=false`; `/mcp/status` then reports
disabled and `/mcp/quiz` returns 403, which `quizzes.yml` asserts.

### Known Limitations

- If the Subject Management service is unreachable when generating a quiz, the AI is given only a
  generic "Subject #N" placeholder (no description), and may hallucinate an unrelated topic rather
  than failing outright. This is a deliberate trade-off so the feature still works standalone; in
  the integrated team application both services run together and this does not occur (verified).
- `qwen2.5:0.5b`-generated attempt feedback sometimes just restates the supplied context instead of
  giving new advice, a known quality limitation of very small models rather than a code defect.
- Editing a quiz's metadata or adding a question does not live-refresh the take-quiz form already
  open in the browser; re-opening the quiz shows the update. The quiz list refreshes automatically
  via the `quizzesChanged` HTMX trigger.
- RAG retrieval matches words, not meaning (the RAG server uses a hashed bag-of-words embedding),
  so questions work best using the words in the quiz, such as its title or the question's wording.
- AI-generated quizzes are not indexed for RAG (see *Release 1: RAG*), so RAG cannot answer
  questions about them; the MCP tools still list and return them.
- The RAG index is not updated automatically: run Ingest on the RAG Tools page after adding or
  editing quizzes.
- The RAG server, Ollama and the MCP server run on the host, not in Docker, so RAG and MCP only work
  when their servers have been started separately (`rag-server/run.ps1` or `run.sh`, and
  `mcp/run.ps1` or `run.sh`). A grounded answer from the local model takes around 30-60 seconds.
- The MCP tools are read-only by design, so no MCP client can change quiz data.

### Additional Notes

Verified locally, both standalone and as part of the full integrated stack (root `docker-compose.yml`
building access + subjects + quizzes together via `include:`): `docker compose up --build`, and all
nine ports across the three features (3000/5000/6000, 3001/5001/6001, 3004/5004/6004) reachable and
returning HTTP 200/302 as expected, matching the CI smoke-check in
[`quizzes.yml`](../.github/workflows/quizzes.yml). All CRUD paths (create, update, delete, add
question), quiz-taking and grading, attempt history, AI quiz generation, and AI attempt feedback were
exercised directly against a live Ollama instance, not mocked, after the frontend/backend were
restructured to the Bootstrap multi-page convention. The Learning Hub's "Quiz Manager" card and the
shared navbar's "Quizzes" link were both confirmed to point at the right URLs.

On Windows/Mac, `network_mode: host` (used across this whole repo) requires Docker Desktop's
"Enable host networking" setting (Settings > Resources > Network) to be turned on, plus a restart
of Docker Desktop; each container may also need one `docker restart` after that if its port isn't
immediately forwarded to the host. This is a Docker Desktop limitation, not specific to this
feature - every team member's containers need this to be reachable at `localhost` from Windows/Mac.

In Release 1 the CI workflow also starts the stack with `MCP_ENABLED=false` and `RAG_ENABLED=false`,
probes the MCP and RAG pages, and verifies that both are reported disabled and refused with 403.

#### Running Release 1 locally

1. Start Ollama with `llama3.1:8b` pulled.
2. Start the quiz containers: `docker compose up -d --build` in `quizzes/` (or the root compose).
3. Start the MCP server: `mcp/run.ps1` (Windows) or `mcp/run.sh`.
4. Start the RAG server: `rag-server/init.ps1` once, then `rag-server/run.ps1` (or the `.sh`
   equivalents).
5. Open `http://localhost:3004`, then RAG Tools (Ingest first) or MCP Tools.
6. Terminal validation: `bash scripts/mcp_endpoint_test.sh` and `bash scripts/rag_endpoint_test.sh`
   from `quizzes/`, and `.venv/Scripts/python.exe test_tools.py quizzes` from `mcp/` (venv created
   by `mcp/run.ps1`; `.venv/bin/python` on Linux/macOS).
7. Agentic loop: `agentic_loop/run.ps1 --skip-report-download --area mcp --service quizzes`, and
   the same with `--area rag`.
