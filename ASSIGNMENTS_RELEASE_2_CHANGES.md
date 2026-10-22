# Assignments Release 2 Change Record

**Baseline:** `69cf3d4` (`origin/main` at the time the Assignment changes began). No release tag was present in the checkout, so this records the local Release 2 contribution relative to that pulled baseline. It is a code-change summary, not the group technical report.

## Summary

Assignments was connected to the shared non-containerised Multi-Agent Server. The integrated feature now has an Assignments evidence connector, backend proxy routes, a frontend workflow page with human decision controls, and a local Compose configuration for the shared server. The service CI now runs two named endpoint-function tests and publishes their output with its workflow evidence. The shared agentic loop also writes its review/validation results to timestamped Markdown files.

The repository already had the integrated Azure Container Apps deployment, review modes (`pre_test`, `cicd_test`, and `deployment`), Assignment CRUD, and Assignment MCP/RAG integrations at the baseline. Those were retained, not reimplemented here.

## File Changes

| File | Change |
| --- | --- |
| `multi-agent-server/connectors/assignments.py` | Adds a read-only connector that fetches Assignment records, validates required fields, caps records and text size, and excludes fields outside an explicit allowlist. Defaults to `http://localhost:6003`, matching local connector conventions; `ASSIGNMENTS_DATABASE_URL` can override it. |
| `multi-agent-server/connectors/__init__.py` | Registers the `assignments` connector alongside the existing service connectors. |
| `multi-agent-server/agents/model_client.py` | Defaults Planner/Worker to `qwen2.5:0.5b` and Reviewer to `llama3.1:8b`, retaining environment-variable overrides. This avoids the observed Planner timeout when all roles fell back to the 8B model. |
| `assignments/backend/services/multi_agent_service.py` | Adds the fixed-identity `assignments` relay for workflow creation, status/history lookup, and human decisions. Defaults to the shared server at port `15004`. |
| `assignments/backend/routes/multi_agent.py` | Adds the status, workflow, history, and decision endpoints, including the feature-flag 403 behavior and upstream error handling. |
| `assignments/backend/app.py` | Registers the Multi-Agent API under `/api/multi-agent`. |
| `assignments/docker-compose.yml` | Passes the feature flag, shared-server URL, and long workflow timeout to the backend; local Multi-Agent remains enabled by default. |
| `assignments/frontend/multi-agent.html` | Adds the page for selecting Assignment evidence, submitting a task, loading workflow history, and recording a human decision. |
| `assignments/frontend/multi-agent.js` | Implements same-origin API calls, enable/disable state, workflow/status display, and the separate human decision submission. Failed workflows permit only rejection, consistent with server rules. |
| `assignments/frontend/Dockerfile` | Copies the new page and script into the frontend image. |
| `assignments/frontend/nginx.conf` | Proxies `/api/multi-agent` to the Assignment backend. |
| `assignments/frontend/index.html` | Adds navigation to the Multi-Agent page. |
| `tests/assignments/test_assignments_api.py` | Tests `GET /assignments` (`all_assignments`) and `POST /assignments` (`add_assignment`); the POST test verifies returned fields and deletes its disposable record. |
| `tests/assignments/test_multi_agent_connector.py` | Tests the connector URL, allowlisted fields, truncation limit, source reference, and truncation limitation. |
| `.github/workflows/assignments.yml` | Adds push-to-main, PR, and reusable workflow triggers for relevant files, including the Assignment-specific agent prompt; builds and starts the service; probes the new page and disabled Multi-Agent route; runs the two endpoint tests; uploads pytest output with the existing CI report. |
| `agentic_loop/main.py` | Saves each completed review invocation to a unique timestamped Markdown log in `agentic_loop/runs/`. |
| `agentic_loop/README.md` | Documents the review-log output instead of saying reviews print only. |

## Verification

- `python -m pytest tests/assignments -v --color=no`: **3 passed** (2 endpoint tests and 1 connector unit test) after the final `localhost` default/expectation alignment. The live endpoint tests used `ASSIGNMENTS_BACKEND_URL=http://127.0.0.1:5003` for this Windows Docker host.
- `docker compose -f assignments/docker-compose.yml config --quiet`: passed.
- Python compilation and JavaScript syntax checks: passed.
- Assignment backend Multi-Agent status/history relay: returned HTTP 200.
- Assignment 1's live `description` and `requirements` were restored to the clean values in `assignments/database/init_db.py` through a targeted backend update and then verified with a GET; no database reset was performed.
- Rebuilt Assignment frontend: the Multi-Agent page was present; Nginx configuration validation passed.
- Live Assignment workflow through the backend: Planner, Worker, and Reviewer completed successfully. The workflow remains pending human decision; no approval was recorded.
- Agentic-loop review-log and Python changes compiled successfully.

## Notes and Remaining Evidence

The first live model attempt timed out at Planner before the default model split was corrected. That failed run remains in local workflow history. After Assignment 1 was restored, workflow `8296f370-7fe5-4d2d-8d5d-a552f75dfa67` completed Planner, Worker, and Reviewer successfully and remains pending human review. The earlier successful run and its Reviewer recommendation were based on the corrupted text; its pending decision and all historical records remain unchanged. The source default and unit-test expectation were aligned to `localhost` by request. On this Windows Docker setup, set `ASSIGNMENTS_DATABASE_URL=http://127.0.0.1:6003` when launching the non-containerised server if `localhost` does not resolve to the forwarded IPv4 port.

CI execution on GitHub, cloud deployment verification, and the final human decision still require their own evidence. Local pre-commit evidence confirms Ruff and detect-secrets passed; pip-audit had not returned a final result when this record was updated. No PDF technical report or showcase video was created here.
