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

### Backend/API Functions

- `GET /quizzes` - list all quizzes
- `GET /quizzes/{id}` - quiz details (renders the take-quiz form)
- `GET /quizzes/{id}/edit` - edit form fragment for a quiz
- `POST /quizzes/{id}/attempts` - submit a quiz attempt (grades it and returns the results view)
- `GET /quizzes/{id}/attempts` - previous attempts for a quiz
- `POST /subjects/{id}/quizzes/generate` - generate an AI practice quiz for a subject
- `POST /attempts/{id}/feedback` - generate/fetch AI feedback for an attempt's incorrect answers

Plus supporting CRUD used by the management UI, following the same flat-route/`HX-Redirect`
convention as the subjects feature: `POST /quizzes` (create), `POST /quizzes/update`,
`POST /quizzes/delete`, `POST /quizzes/{id}/questions` (add question), and `POST /quizzes/generate`
(the form-friendly equivalent of the subject-scoped generate endpoint, since a plain HTML form can't
submit a path parameter without page-specific server rendering).

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
