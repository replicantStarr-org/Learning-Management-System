# Quizzes: Release 2 report notes (draft)

Draft text for the group report. Each line says whether it was observed or is still to do.
Replace every "TO DO" with real evidence before the report is submitted.

## Multi-Agent integration

- Quizzes plugs into the shared multi-agent server (PR #53) with a read-only connector
  (`multi-agent-server/connectors/quizzes.py`), relay routes (`quizzes/backend/routes/multi_agent.py`)
  and a page (`quizzes/frontend/multi-agent.html`). The connector reads quiz content only, never attempts or scores.
- Flow: Frontend UI -> Quizzes backend `/multi-agent/*` -> Multi-Agent Server (port 15004) -> Planner -> Worker ->
  Reviewer -> Human Review -> response to the frontend UI.
- Observed on 2026-10-21 on a local machine through the frontend (port 3004), with the real model `llama3.1:8b`
  for all three agents and no environment overrides: workflows finished with planner, worker and reviewer all
  `success` in 41 s to 87 s (4 of 4 runs). The earlier default model `qwen2.5:0.5b` failed in 3 of 4 runs (two outputs cut off at
  the token limit and one timeout), so the shared default was changed to `llama3.1:8b`.
- Human review: the human records Accept, Partially Accept or Reject, with a name, a reason and the evidence used.
  A correction is recorded as Partially Accept, with the correction written in the reason. The server accepts one
  decision for each workflow. Observed from the terminal: a decision was recorded with
  `multi-agent-server/workflow_runner.py --workflow-id ... --decision "Partially Accept"`, and a second decision was
  refused ("A human decision has already been recorded").
- Switch: with `MULTI_AGENT_ENABLED=false` the routes return 403 and the page link is hidden (observed locally in a
  headless browser). In the cloud the default is off.
- Not done: TO DO: record a real human decision for the run shown in the report, and take screenshots for the video.
- Agentic loop, Multi-Agent Coordination mode: `agentic_loop/runs/multi-agent-review-for-quiz-manager.txt`.
  The static checks passed. The loop approved the human-decision gating. The output is short and the review
  model only agreed with the implementation model; the report should say what a human decided about it.

## Post-commit CI/CD testing

- Endpoints tested: `POST /quizzes` and `POST /quizzes/{id}/attempts`, 6 tests in `tests/quizzes/test_quiz_endpoints.py`.
  Twenty-one more tests in `tests/quizzes/test_multi_agent_routes.py` check the multi-agent switch, the 503 mapping and the
  request bodies, and 5 in `tests/quizzes/test_multi_agent_connector.py` check what the connector reads.
- Workflow: `.github/workflows/quizzes.yml`, jobs Build Images, Smoke Check, Endpoint Tests and Evidence Upload. It runs on
  push and on pull request. The smoke check also confirms that the multi-agent routes return 403 when switched off.
- Observed on 2026-10-21: the four jobs passed on the PR #56 merge commit. TO DO: link the run and paste the counts
  from the `quizzes-ci-evidence` artifact.
- Agentic loop, Testing Review mode: the modes `pre_test` and `cicd_test` exist in `agentic_loop/config/review_config.py`.
  TO DO: run them for Quizzes and save the output as the validation log.

## Pre-commit security

- Shared checks from PR #54 (Ruff security rules, detect-secrets, pip-audit). Quizzes has three `# noqa` lines with reasons
  (two container bind addresses, one UPDATE statement with fixed column names).
- Observed on 2026-10-21: the hook was installed and all three scans passed during a commit (reports in
  `reports/pre-commit/`). The secret scan first flagged five false positives in the cloud files, which were marked with
  `# pragma: allowlist secret`. TO DO: copy the three JSON reports into the evidence.

## Cloud deployment

- Quizzes uses the group cloud setup (PR #57): the pages call the backend with relative URLs, nginx forwards the API paths
  (including `/multi-agent`), and `/config` reports the profile and the four AI flags. The cloud default turns AI-Mode,
  MCP, RAG and Multi-Agent off, and the bonus profile turns them on. The seed quiz question about the cloud baseline
  was corrected to match the brief.
- The Quizzes multi-agent routes default to off when `CLOUD_DEPLOYMENT` is set (covered by a unit test).
- Not done: TO DO: check the Quizzes pages and the multi-agent page on the bonus site, and save the deployment workflow run.
- Agentic loop, Cloud Deployment Review mode: the mode `deployment` exists. TO DO: run it for Quizzes after the cloud
  verification files are available.

## Contribution log (from git)

- PR #52: AI-Mode switch, endpoint tests, CI job, port fix for the multi-agent server.
- PR #56: Quizzes multi-agent connector, routes and page, seed-data fix, loop run output, merge with the cloud setup,
  route tests, terminal decision command, and the multi-agent model defaults.
