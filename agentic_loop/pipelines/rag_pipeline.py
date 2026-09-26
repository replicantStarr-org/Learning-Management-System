def build_implementation_prompt(task_prompt: str, evidence: str) -> str:
    return f"""
{task_prompt}

Review Scope:
RAG Server (rag-server/)

Observed Evidence:
{evidence}

Validate that:
1. All required RAG server Python files are present
2. The 5 HTTP endpoints (GET /health, GET /services, POST /ingest,
   POST /retrieve, POST /answer) are defined in the ROUTES table of
   server/http_server.py
3. Each endpoint is callable: its route is bound to a function defined in
   server/endpoints.py
4. POST /answer is expected to return citations and a confidence category;
   the evidence is static, so state this as unverified rather than confirmed

Reply in at most 40 words and stay evidence-based.
""".strip()


def build_review_prompt(implementation_output: str, evidence: str) -> str:
    return f"""
Implementation Recommendation:
{implementation_output}

Observed Evidence:
{evidence}

Validate the RAG server assessment against the evidence.
Check that every claimed endpoint and handler appears in the evidence, and
flag any claim about runtime behaviour, retrieval quality or citation
grounding that the static evidence cannot support.

Reply in at most 40 words and stay evidence-based.
""".strip()
