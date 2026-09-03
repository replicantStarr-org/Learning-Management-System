# Agentic Loop

A data quality reviewer for the rest of this application. It probes endpoints it
is told about, works out what is wrong with the data coming back, and writes a
report recommending what a developer should change.

**It never changes anything.** No service in this repository is modified,
imported or written to. The output is a markdown file.

## The loop

One iteration is one pass of Plan → Act → Observe → Adapt. Two local models
share the work and neither is trusted with the part it would be bad at.

| Step | Who | What happens |
| --- | --- | --- |
| **Plan** | `qwen2.5:0.5b` | Chooses which endpoints to probe next, from a shortlist this tool has already ordered. |
| **Act** | the runner | Sends a read-only GET to each chosen endpoint and keeps the response. |
| **Observe** | checks, then `qwen2.5:0.5b` | Python computes the findings; the model turns them into recommendations. |
| **Adapt** | `llama3.1:8b` | Rules on each recommendation against the evidence and names what the next pass should look at. |

The reviewer's decision feeds straight back into the next Plan, which is what
makes the second iteration different from the first.

### Why the work is split this way

Every finding is computed in Python, in `loop/observe.py`, and is true before
any model sees it. A 0.5B model handed a raw JSON body will describe fields that
are not there, so it is never the thing that decides whether a problem exists —
it only phrases the advice. The 8B model does the judging, because deciding
whether a claim is supported by evidence is the harder half.

That split also means the tool degrades rather than fails. Every finding has a
written remedy in `loop/recommend.py`, so with Ollama switched off entirely
(`--offline`) the report still comes out; it just loses the model's phrasing and
the reviewer's verdicts.

## Configuring it

Everything the loop knows about the other services is in `services.yml`. Adding
coverage means adding an entry there, and nothing else:

```yaml
services:
  - name: quizzes
    description: Quiz authoring, generation and attempts.
    endpoints:
      - name: list-quizzes
        url: http://localhost:6004/quizzes
        expect: json_array           # json_array | json_object | html | text
        identifier: quiz_id          # must be unique across rows
        required_fields: [quiz_id, title, difficulty]
        records_at: ""               # key holding the list, for json_object
        notes: Anything the models should know about this endpoint.
```

Only GET endpoints are accepted. A `method:` of anything else is rejected when
the file loads, so a probe can never create or delete another service's data.

## Running it

```bash
./run.sh                            # one run using services.yml
./run.sh --list                     # show what is configured, then stop
./run.sh --offline                  # checks only, no models
./run.sh --service quizzes          # probe one service and no others
./run.sh --service quizzes --service subjects   # or several
./run.sh --iterations 5 --reports /tmp/reports
./run.sh --fail-on-critical         # exit 1 on a critical finding, for CI
```

On Windows, `run.ps1` takes the same arguments:

```powershell
.\run.ps1 --offline --iterations 5
```

If PowerShell refuses to run it, the execution policy is the reason. Either
allow it for the current window with
`Set-ExecutionPolicy -Scope Process Bypass`, or call it as
`powershell -ExecutionPolicy Bypass -File run.ps1`.

Both scripts build `.venv/` on first use and reinstall only when
`requirements.txt` changes, so later runs start straight away. Arguments go
through to `agentic_loop.py`, which can equally be called directly from an
already activated environment.

Ollama is expected on the host at `http://localhost:11434`, the same instance
the other services use. Set `OLLAMA_URL` if it lives somewhere else.

Reports land in `reports/`, which is not committed.

Nothing else in the repository is involved in a run. This folder has no entry in
the root `docker-compose.yml` and no service was changed to accommodate it.

## What it checks

Transport: reachability, status, latency, empty bodies, `Content-Type`
agreement.

Structure: parseable JSON, the shape matching what was configured, rows that
arrive as positional lists instead of named objects, rows whose shape varies,
collections that come back empty.

Fields, across every row: required fields missing or inconsistently present,
values that are null or blank, a field that is empty in every row, types that
change between rows, filler values such as `todo` or `test`, untrimmed
whitespace, a field holding one value in every row, duplicate identifiers and
duplicate rows.

Markup, for `html` endpoints: leaked stack traces, blank fragments, and
unrendered template markers.

## Layout

```
.
├── agentic_loop.py      the loop itself, and the CLI
├── run.sh, run.ps1      venv bootstrap, one per platform
├── services.yml         the endpoints, edited by hand
├── prompts/             one prompt file per model role
└── loop/
    ├── config.py        reads and validates services.yml
    ├── plan.py          Plan
    ├── act.py           Act, the only code that calls another service
    ├── observe.py       Observe: the checks
    ├── recommend.py     Observe: findings into advice, plus the fallback remedies
    ├── adapt.py         Adapt
    ├── ollama_client.py the two model roles
    ├── state.py         what carries between iterations
    └── report.py        the markdown output
```
