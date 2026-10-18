# Quizzes: Release 2 report notes (draft)

Draft text for the group report. Each line says whether it was observed or is still to do.
Replace every "TO DO" with real evidence before the report is submitted.

## Multi-Agent integration

- Quizzes plugs into the shared multi-agent server (PR #53) with a read-only connector
  (`multi-agent-server/connectors/quizzes.py`), relay routes (`quizzes/backend/routes/multi_agent.py`)
  and a page (`quizzes/frontend/multi-agent.html`). The connector reads quiz content only, never attempts or scores.
- Observed on 2026-10-18 on a local machine, with the real models (qwen2.5:latest for planner and worker,
  llama3.1:8b for reviewer): one workflow for quiz 1 ("study plan") finished with planner, worker and reviewer
  all `success` in 90.8 s. The reviewer recommended Reject because the evidence had no performance data.
  No human decision has been recorded for that workflow. TO DO: record a real human decision for the run shown in the report.
- Agentic loop, Multi-Agent Coordination mode: `agentic_loop/runs/multi-agent-review-for-quiz-manager.txt`.
  The static checks passed. The loop approved the human-decision gating. The output is short and the review
  model only agreed with the implementation model; the report should say what a human decided about it.
- Not done: browser walk-through of the page (TO DO: screenshots for the video).

## Post-commit CI/CD testing

- Endpoints tested: `POST /quizzes` and `POST /quizzes/{id}/attempts`, 6 tests in `tests/quizzes/test_quiz_endpoints.py`.
- Workflow: `.github/workflows/quizzes.yml`, job `endpoint-tests`. It runs on push and on pull request.
- Observed locally: 6 passed. TO DO: link the successful GitHub Actions run and paste the JUnit counts from the `quizzes-ci-evidence` artifact.
- Agentic loop, Testing Review mode: not available. The mode does not exist in `agentic_loop/config/review_config.py`. TO DO: group decision on who adds it.

## Pre-commit security

- Shared checks from PR #54 (Ruff security rules, detect-secrets, pip-audit). Quizzes has two `# noqa` lines with reasons
  (container bind address, UPDATE statement with fixed column names).

## Cloud deployment

- Quizzes can run outside localhost: addresses come from environment variables (`quizzes/design.md`, "Cloud settings").
  The four AI flags must be `false`. The seed quiz question about the cloud baseline was corrected to match the brief.
- Not done: deployment to Azure. The deployment workflow and resource group belong to the cloud owner
  (`learning-hub-demo`). TO DO: build and push the three Quizzes images, create the container apps, set the variables,
  save the successful workflow run.
- Agentic loop, Cloud Deployment Review mode: not available (same reason as Testing Review).

## Contribution log (from git)

- PR #52: AI-Mode switch, endpoint tests, CI job, port fix for the multi-agent server.
- PR #56: Quizzes multi-agent connector, routes and page, cloud address settings, seed-data fix, loop run output.
