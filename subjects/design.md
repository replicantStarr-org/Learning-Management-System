# Subject Management Feature Design

This document details the design for the subject microservice and the 3 associated containers.
The design states the desired final state for the feature rather than current one as explained in the [application design](../design.md)

The subject management feature gives users the ability to view, create, update and delete subjects.
Additionally, AI can be used to ask questions about a given subject or to summarise the information about one.

### Functionality Breakdown

- View all subjects
- View details for a specific subject
    - The page for this should be navigated to from the page with all the subjects. The default view should include bubble boxes that display the information about subjects. Clicking on this should take you to the details for that subject.
- Edit subject, a button on the view subject details page should take you to a page for editing that subject
- Delete subject, a button should be shown in the view subject details page
- Create subject - this should be a button on the default view, this should take you to a similar page as the edit subject page where you can fill in the fields for a new subject
- Ask a question about a subject and get an AI-generated response, there should be some loading to show the call is pending since LLM calls can take a while. If possible with HTMX, implement streaming for the text part of the response or a text animation after receiving the full response.
- Generate/view an AI summary about the subject
    - This should be generated on demand when viewing subject details
    - There should be the classic AI sparkles icon to indicate the 'subject summary' is AI generated
    - All summaries will be saved in the database and should be re-used as described below
    - New summaries should be generated if the newest is older than a week or if the subjects last update timestamp is newer than the latest summary


Appropriate validation for the field lengths should be implemented, first as frontend input fields that prevent such inputs, and then repeated validation on the backend.

### Endpoint Testing

The browser checks below should be performed with the three containers running. The browser entry point is the frontend on port 3001; the HTML/HTMX backend is on port 5001, and the JSON database API is on port 6001. Use a disposable subject when testing create, update and delete operations.

| Function | Browser Validation | API Validation |
|---|---|---|
| Home page | Open `http://localhost:3001/` and confirm the Subjects page loads. | `curl -i http://localhost:3001/` |
| Service health | The home page should load its subject list without an error. | `curl -i http://localhost:5001/` and `curl -i http://localhost:6001/` |
| View all subjects | Open `http://localhost:3001/` and confirm subject cards are displayed. | `curl -i http://localhost:5001/subjects` |
| View subject details | Click a subject card, or open `http://localhost:3001/subject.html?id=1`. | `curl -i http://localhost:5001/subjects/1` |
| Subject not found | Open `http://localhost:3001/subject.html?id=999999999` and confirm a useful error and return link are shown. | `curl -i http://localhost:6001/subjects/999999999` (expected JSON 404), or `curl -i http://localhost:5001/subjects/999999999` (expected HTMX error response). |
| Create subject | Select **Create subject** on the list page, complete the form, submit, and confirm the success message/detail page. | `curl -i -X POST http://localhost:5001/subjects -d 'code=CI001' -d 'name=CI Test Subject' -d 'description=Created by endpoint test' -d 'semester=Spring' -d 'coordinator=CI Tester' -d 'status=Open'` |
| Edit subject | On a detail page select **Edit**, change a field, save, and confirm the updated value is displayed. | `curl -i -X POST http://localhost:5001/subjects/update -d 'subject_id=1' -d 'name=Updated Subject'` |
| Delete subject | On a detail page select **Delete**, confirm the prompt, and verify the subject disappears from the list. | `curl -i -X POST http://localhost:5001/subjects/delete -d 'subject_id=1'` |
| Subject validation | Submit the create/edit form with a blank required field or text beyond a maxlength and confirm an explanatory error is shown. | `curl -i -X POST http://localhost:5001/subjects -d 'code=CI001' -d 'name='` (expected validation error). |
| Generate AI summary | Open a subject detail page and wait for the **AI summary** panel to populate. Reload it to check that a cached summary is indicated when still fresh. | `curl -i -X POST http://localhost:5001/subjects/1/summary` (requires a locally available Ollama model). |
| Ask an AI question | On a subject detail page enter a question, submit it, observe the loading indicator, and confirm an answer appears. | `curl -i -X POST http://localhost:5001/subjects/questions -d 'subject_id=1' --data-urlencode 'question=What is this subject about?'` (requires Ollama). |
| List stored summaries | There is no separate browser control; summaries are visible in the subject detail view. | `curl -i http://localhost:6001/subjects/1/summaries` |
| Get stored summary | There is no separate browser control; this is exercised by the detail page's summary result. | First obtain an ID from `curl http://localhost:6001/subjects/1/summaries`, then run `curl -i http://localhost:6001/summaries/<summary_id>`. |
| Delete stored summary | API validation only; summaries are managed automatically by the subject detail flow. | `curl -i -X DELETE http://localhost:6001/summaries/<summary_id>` using an ID returned by the list endpoint. |

For a quick local run, use `bash scripts/endpoint_test_local.sh` from the `subjects` directory. This script includes the Ollama-dependent summary and question checks. It is intentionally not called by the GitHub Actions workflow; CI only runs `scripts/nfr_smoke.sh`, which makes no Ollama/model calls.

Replace `1` with an ID returned by the list endpoint if the local database does not contain that seed ID. Expected: browser flows display the relevant page, loading state, success state, or user-facing error. API checks return the documented HTTP status and response body.

### Non-functional requirements (NFRs)

The following requirements apply to the running subject frontend/backend/database compose. Unless stated otherwise, performance tests should be run after the containers have started and a warm-up request has completed.
AI-generation endpoints are excluded from the strict latency targets because their latency depends on the model.
They should instead meet the availability and user-feedback requirements below.

| ID | Quality attribute | Requirement / acceptance criterion | Quick verification |
| --- | --- | --- | --- |
| NFR-01 | Availability | The backend and database health endpoints (`GET /` on ports 5001 and 6001) return a successful response for at least 99 of 100 requests while the stack is healthy. | `for i in {1..100}; do curl -fsS http://localhost:5001/ >/dev/null \|\| echo failed; done` (repeat on port 6001). |
| NFR-02 | Availability | `GET http://localhost:5001/subjects` returns HTTP 200 for 100 sequential requests when the database is available. | Loop over `curl -s -o /dev/null -w '%{http_code}'` and assert every result is `200`. |
| NFR-03 | Availability | A valid subject detail request returns HTTP 200, while a request for a missing subject returns HTTP 404 (or the documented user-facing error) consistently. | Test `/subjects/1` and `/subjects/999999` repeatedly and count status codes. |
| NFR-04 | Performance | For 100 requests to `GET /subjects`, with up to five requests in flight on the assessment runner, the P99 response time is below 100 ms. | Use `xargs -P 5` with `curl -w '%{time_total}'`, sort the timings, and inspect the 99th percentile. |
| NFR-05 | Performance | Subject CRUD operations (create, read, update and delete) each complete in under 100 ms at the P95 for 20 sequential operations, excluding container start-up. | A bash script can create a uniquely named fixture, time each `curl`, verify the response, then remove the fixture. |
| NFR-06 | Scalability | The service handles a 100-request read burst, with up to five requests in flight, without connection errors, 5xx responses, or corrupted/incomplete HTML. | Run a five-worker `curl` request pool and assert exit status, HTTP status, and that each response contains the expected subject-list marker. |
| NFR-07 | Input validation | The public HTML backend rejects missing fields, blank values, and values over the documented limits (code 20, name 120, description 5,000, question 1,000 characters) without creating or changing data. The internal database API rejects malformed JSON objects and missing required fields. | Submit boundary and over-boundary form payloads to the backend and a missing-field JSON payload to the database API; assert a user error/4xx response and then check that no unintended subject was created. |
| NFR-08 | Data integrity | A successful create can be read back with all supplied fields; an update changes only supplied fields; and a delete makes the subject unavailable. | Perform the CRUD sequence with a unique fixture and compare JSON/HTML responses. |
| NFR-09 | Data integrity | Deleting a subject also removes its related AI summaries, and no summary can be created for a missing subject. | Create a subject and summary through the database API, delete the subject, then assert summary lookup returns 404 and creation returns 404. |
| NFR-10 | Consistency / idempotency | Repeating the same `PUT` leaves the same subject representation, and repeating `DELETE` returns the documented not-found response without creating side effects. | Send each request twice and compare the first and second results. |
| NFR-11 | Persistence | Subjects and summaries remain available after the database process/container is restarted when the configured volume is retained. | Create a fixture, run `docker compose restart subject-database`, wait for the health endpoint, and read the fixture back. |
| NFR-12 | Security | User-controlled subject and AI text is HTML-escaped before rendering; input such as `<script>alert(1)</script>` must not become executable markup. | Create a fixture containing HTML-special characters, fetch its page, and assert the response contains escaped text rather than a raw `<script>` element. |
| NFR-13 | Security | Prompt-injection patterns and empty/oversized AI questions are rejected without calling the model or storing unsafe output. | Submit representative invalid questions and assert the error response; verify no summary/question result is persisted. |
| NFR-14 | Fault tolerance | If the database is unavailable, the backend returns a clear error response rather than a traceback or blank page; once the database is restored, normal requests succeed again. | Stop `subject-database`, call `/subjects`, inspect the response for the documented error, restart it, and retry. |
| NFR-15 | Usability | List, detail, create and edit views provide clear loading/error/success feedback, and AI requests visibly indicate that work is in progress. | Inspect the HTML for `role="status"`, `aria-live`, `hx-indicator`, and actionable error messages; verify the flow manually in a browser. |
| NFR-16 | Accessibility / responsive UI | Pages have a `lang` attribute, labelled form controls, keyboard-operable controls, meaningful headings, and remain usable at desktop and mobile viewport widths. | Grep/HTML-check the static pages for labels and headings, then perform a short keyboard and browser viewport check. |
| NFR-17 | Maintainability | HTTP routing, business validation/AI logic, database access, and HTML rendering remain separated into their current modules. Repeated database or AI logic is not copied into route handlers. | Code review or a lightweight import/lint check. Confirm changes to validation do not require editing every route. |
| NFR-18 | Maintainability / operability | The service can be built and started from a clean checkout using the documented Docker Compose configuration, with no manually created files or host-specific source paths required. | Remove generated data, run `docker compose build` followed by `docker compose up -d`, and exercise the health endpoints. |

You can perform automated checks for most of these requirements after running the docker compose for the subject microservice by running `scripts/nfr_validation.sh`.


### Additional Notes

The subject feature should have a CI workflow as described in [the app design](../design.md).
