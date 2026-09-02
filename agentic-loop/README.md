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
pip install -r requirements.txt

python agentic_loop.py              # one run using services.yml
python agentic_loop.py --list       # show what is configured, then stop
python agentic_loop.py --offline    # checks only, no models
python agentic_loop.py --iterations 5 --reports /tmp/reports
python agentic_loop.py --fail-on-critical   # exit 1 on a critical finding, for CI
```

Or in a container, against the same host Ollama the other services use:

```bash
docker compose run --rm agentic-loop
```

Reports land in `reports/`, which is not committed.

The container is behind a `tools` profile, so it does not start with the rest of
the application. Nothing in the root `docker-compose.yml` or any other service
was changed to add it.

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
