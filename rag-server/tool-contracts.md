# RAG Tool Contracts

Exposed both as MCP tools (`server/mcp_server.py`) and HTTP endpoints (`server/http_server.py`, port in `config.toml`). Each HTTP endpoint is a function in `server/endpoints.py`. Start the HTTP server with `./run.sh` and stop it with Ctrl+C or `./run.sh stop` (`run.ps1` on Windows); requests in progress are finished before it exits, except with `run.ps1 stop` on Windows, which ends it at once. Start the MCP server from `rag-server/` with `.venv_rag/bin/python -m server.mcp_server`.
`service` is always optional and must name a connector in `pipeline/connectors/` (`subjects`, `assignments`, `quizzes`, `timetable`, `learning-resources`).

## ingest — `POST /ingest`
- Purpose: fetch every record from the service's database API, chunk, embed and upsert into Chroma; chunks for records that no longer exist are removed
- Input: `service` (optional, all services when omitted)
- Output: `status` (`success` | `partial` | `error` | `skipped`), `services[]` with `service`, `status`, `chunk_count`, `removed_count`, or `error`, or `reason` when skipped
- A connector with no entity functions is `skipped` and its index is left untouched; the overall status only counts services that were attempted, and is `skipped` when none were
- A service that cannot be reached keeps its previously indexed chunks
- Policy class: read + index update

## retrieve_context — `POST /retrieve`
- Purpose: retrieve the top `k` chunks within `retrieval.max_distance`
- Input: `query` (required), `k` (optional), `service` (optional)
- Output: `status`, `results[]` with `rank`, `chunk_id`, `service`, `entity`, `record_id`, `title`, `distance`, `text`
- Policy class: read

## answer_question — `POST /answer`
- Purpose: answer from retrieved context only, using the Ollama model in `config.toml`
- Input: `query` (required), `k` (optional), `service` (optional)
- Output: `answer`, `citations[]`, `confidence_category` (`High` | `Medium` | `Low` | `None`), `retrieval_summary` or `error`
- Returns `Insufficient evidence.` without calling the model when nothing is retrieved
- Policy class: read + grounded response

## Other endpoints
- `GET /health`
- `GET /services` — configured service names
