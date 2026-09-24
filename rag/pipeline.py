import json
import os
import sqlite3
import time
import uuid
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import chromadb
import requests

BASE_DIR = Path(__file__).resolve().parent
APP_DIR = BASE_DIR.parent
REPORTS_DIR = APP_DIR / "reports"
CORPUS_PATH = BASE_DIR / "corpus" / "corpus.jsonl"
AUDIT_PATH = BASE_DIR / "rag-audit.jsonl"
CHROMA_PATH = BASE_DIR / "chroma"
DATABASE_SERVICE_URL = os.getenv("DATABASE_SERVICE_URL", "http://database-service:5002")

DB_PATH_CANDIDATES = [
    APP_DIR / "database-service" / "data" / "enrolment.db",
    APP_DIR / "database-service" / "enrolment.db",
    APP_DIR / "enrolment.db",
]

REPORT_FILES = [
    "report.json",
    "run-report.md",
    "integration-report.md",
    "tool-review.md",
    "boundary-analysis.md",
]

COLLECTION_NAME = "student_enrolment_enterprise_context"
EMBED_VECTOR_SIZE = 256

_collection = None
_last_corpus_chunks: list[dict[str, Any]] = []


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_db_path() -> Path:
    for path in DB_PATH_CANDIDATES:
        if path.exists():
            return path
    return DB_PATH_CANDIDATES[0]





def get_collection():
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        _collection = client.get_or_create_collection(name=COLLECTION_NAME)
    return _collection


def reset_collection() -> None:
    global _collection
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    try:
        client.delete_collection(name=COLLECTION_NAME)
    except Exception:
        pass
    _collection = client.get_or_create_collection(name=COLLECTION_NAME)


def append_audit(
    tool_name: str,
    tool_input: dict[str, Any],
    tool_output: dict[str, Any],
    validation_status: str,
    outcome: str,
    start_time: float,
) -> None:
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    duration_ms = int((time.time() - start_time) * 1000)
    record = {
        "request_id": str(uuid.uuid4()),
        "trace_id": str(uuid.uuid4()),
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_output": tool_output,
        "timestamp": now_iso(),
        "duration_ms": duration_ms,
        "validation_status": validation_status,
        "outcome": outcome,
    }
    with AUDIT_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")









def build_corpus() -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    chunks.extend(load_database_chunks())
    chunks.extend(load_report_chunks())
    chunks.extend(load_repository_chunks())
    return chunks


def write_corpus(chunks: list[dict[str, Any]]) -> None:
    CORPUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CORPUS_PATH.open("w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk) + "\n")


def read_corpus() -> list[dict[str, Any]]:
    if not CORPUS_PATH.exists():
        return []

    chunks: list[dict[str, Any]] = []
    with CORPUS_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                chunks.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return chunks


def lexical_fallback_retrieve(query: str, k: int) -> list[dict[str, Any]]:
    corpus = _last_corpus_chunks or read_corpus()
    query_tokens = set((query or "").lower().split())
    tier_weight = {"tier_1": 3, "tier_2": 2, "tier_3": 1}

    scored = []
    for chunk in corpus:
        text = chunk.get("text", "")
        text_tokens = set(text.lower().split())
        overlap = len(query_tokens.intersection(text_tokens))
        scored.append(
            {
                "rank": 0,
                "chunk_id": chunk.get("chunk_id"),
                "source_id": chunk.get("source_id"),
                "authority_tier": chunk.get("authority_tier"),
                "distance": None,
                "text": text,
                "_score": overlap,
            }
        )

    scored.sort(
        key=lambda r: (
            tier_weight.get(r.get("authority_tier"), 0),
            r.get("_score", 0),
        ),
        reverse=True,
    )

    top = scored[: max(k, 1)]
    for i, row in enumerate(top, start=1):
        row["rank"] = i
        row.pop("_score", None)
    return top


def refresh_corpus(caller: str = "student") -> dict[str, Any]:
    global _last_corpus_chunks
    start = time.time()
    try:
        chunks = build_corpus()
        _last_corpus_chunks = chunks
        write_corpus(chunks)
        vector_store_status = "ready"
        vector_store_error = None

        try:
            reset_collection()
            collection = get_collection()

            if chunks:
                ids = [c["chunk_id"] for c in chunks]
                docs = [c["text"] for c in chunks]
                metas = [
                    {
                        "source_id": c["source_id"],
                        "authority_tier": c["authority_tier"],
                        "indexed_at": c["indexed_at"],
                    }
                    for c in chunks
                ]
                embeddings = embed_texts(docs)
                collection.add(ids=ids, documents=docs, metadatas=metas, embeddings=embeddings)
        except Exception as exc:
            vector_store_status = "degraded"
            vector_store_error = str(exc)

        output = {
            "status": "success",
            "caller": caller,
            "chunk_count": len(chunks),
            "collection": COLLECTION_NAME,
            "corpus_path": str(CORPUS_PATH),
            "vector_store_status": vector_store_status,
        }
        if vector_store_error:
            output["vector_store_error"] = vector_store_error
        append_audit("refresh_corpus", {"caller": caller}, output, "pass", "corpus_refreshed", start)
        return output
    except Exception as exc:
        output = {"status": "error", "error": str(exc)}
        append_audit("refresh_corpus", {"caller": caller}, output, "fail", "error", start)
        return output


def retrieve_context(query: str, k: int = 5, caller: str = "student") -> dict[str, Any]:
    start = time.time()
    try:
        retrieval_mode = "vector"
        ranked = []

        try:
            collection = get_collection()
            if collection.count() == 0:
                refreshed = refresh_corpus(caller="auto_refresh")
                if refreshed.get("status") != "success":
                    raise RuntimeError("empty_collection")

            query_embedding = embed_texts([query])
            results = collection.query(query_embeddings=query_embedding, n_results=k)

            ids = (results.get("ids") or [[]])[0]
            docs = (results.get("documents") or [[]])[0]
            metas = (results.get("metadatas") or [[]])[0]
            distances = (results.get("distances") or [[]])[0]

            for i, chunk_id in enumerate(ids):
                row_meta = metas[i] if i < len(metas) and isinstance(metas[i], dict) else {}
                ranked.append(
                    {
                        "rank": i + 1,
                        "chunk_id": chunk_id,
                        "source_id": row_meta.get("source_id"),
                        "authority_tier": row_meta.get("authority_tier"),
                        "distance": distances[i] if i < len(distances) else None,
                        "text": docs[i] if i < len(docs) else "",
                    }
                )

            tier_weight = {"tier_1": 3, "tier_2": 2, "tier_3": 1}
            ranked.sort(
                key=lambda x: (
                    tier_weight.get(x.get("authority_tier"), 0),
                    -(x.get("distance") if isinstance(x.get("distance"), (int, float)) else 1e9),
                ),
                reverse=True,
            )
        except Exception:
            retrieval_mode = "lexical_fallback"
            if not _last_corpus_chunks and not CORPUS_PATH.exists():
                refreshed = refresh_corpus(caller="auto_refresh")
                if refreshed.get("status") != "success":
                    return {"status": "error", "error": "corpus_unavailable"}
            ranked = lexical_fallback_retrieve(query, k)

        output = {
            "status": "success",
            "query": query,
            "caller": caller,
            "k": k,
            "retrieval_mode": retrieval_mode,
            "results": ranked,
        }

        append_audit(
            "retrieve_context",
            {"query": query, "k": k, "caller": caller},
            {"result_count": len(ranked), "chunk_ids": [r["chunk_id"] for r in ranked]},
            "pass",
            "context_retrieved",
            start,
        )
        return output
    except Exception as exc:
        output = {"status": "error", "error": str(exc), "query": query}
        append_audit(
            "retrieve_context",
            {"query": query, "k": k, "caller": caller},
            output,
            "fail",
            "error",
            start,
        )
        return output


def confidence_from_results(results: list[dict[str, Any]]) -> str:
    if not results:
        return "Unknown"
    tier_1 = sum(1 for r in results if r.get("authority_tier") == "tier_1")
    tier_2 = sum(1 for r in results if r.get("authority_tier") == "tier_2")
    if tier_1 >= 2 and len(results) >= 3:
        return "High"
    if tier_1 >= 1 or tier_2 >= 2:
        return "Medium"
    return "Low"


def extract_student_records(results: list[dict[str, Any]]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for row in results:
        text = row.get("text", "")
        if "Student record:" not in text:
            continue

        payload = text.split("Student record:", 1)[1].strip().rstrip(".")
        parts = [p.strip() for p in payload.split(",")]
        values: dict[str, str] = {}
        for part in parts:
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            values[key.strip()] = value.strip()

        if values.get("student_id") and values.get("subject_code"):
            records.append(values)

    # Keep stable ordering by numeric student_id when possible.
    def key_fn(item: dict[str, str]):
        sid = item.get("student_id", "")
        return (0, int(sid)) if sid.isdigit() else (1, sid)

    records.sort(key=key_fn)
    return records


def deterministic_answer(query: str, results: list[dict[str, Any]]) -> str | None:
    q = (query or "").lower()
    records = extract_student_records(results)
    if not records:
        return None

    if "student ids and subject codes" in q or "student id and subject code" in q:
        lines = [f"{r.get('student_id')} -> {r.get('subject_code')}" for r in records]
        return "Answer:\n" + "\n".join(lines)

    if "how many students" in q or "student count" in q:
        return f"Answer:\nThere are {len(records)} students in the retrieved evidence."

    return None


def generate_with_ollama(query: str, context: str) -> str:
    model_name = os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")
    ollama_generate_url = os.getenv("OLLAMA_GENERATE_URL", "http://host.docker.internal:11434/api/generate")
    prompt = f"""
You are a retrieval-grounded assistant.
Use only the provided context.
If evidence is missing, return exactly: Insufficient evidence.

QUESTION:
{query}

CONTEXT:
{context}

Return exactly:
Answer:
<answer>

Evidence:
<summary>
"""

    try:
        resp = requests.post(
            ollama_generate_url,
            json={"model": model_name, "prompt": prompt, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json().get("response", "Insufficient evidence.")
    except Exception as exc:
        return f"Ollama unavailable: {exc}"


def answer_question(query: str, k: int = 5, caller: str = "student") -> dict[str, Any]:
    start = time.time()
    retrieval = retrieve_context(query=query, k=k, caller=caller)
    if retrieval.get("status") != "success":
        output = {"status": "error", "query": query, "error": retrieval.get("error", "retrieval_failed")}
        append_audit(
            "answer_question",
            {"query": query, "k": k, "caller": caller},
            output,
            "fail",
            "retrieval_failed",
            start,
        )
        return output

    results = retrieval.get("results", [])
    context = "\n\n".join(r.get("text", "") for r in results)
    answer = deterministic_answer(query, results)
    if answer is None:
        answer = generate_with_ollama(query, context)

    citations = [
        {
            "chunk_id": r.get("chunk_id"),
            "source_id": r.get("source_id"),
            "authority_tier": r.get("authority_tier"),
        }
        for r in results
    ]

    confidence = confidence_from_results(results)
    output = {
        "status": "success",
        "query": query,
        "answer": answer,
        "citations": citations,
        "confidence_category": confidence,
        "retrieval_summary": {
            "k": k,
            "retrieved_count": len(results),
            "top_chunk": results[0].get("chunk_id") if results else None,
        },
    }

    append_audit(
        "answer_question",
        {"query": query, "k": k, "caller": caller},
        {"confidence_category": confidence, "citation_count": len(citations)},
        "pass",
        "answer_generated",
        start,
    )
    return output


if __name__ == "__main__":
    print(json.dumps(refresh_corpus(), indent=2))
    print(json.dumps(retrieve_context("students enrolled in ASD101", 5), indent=2))
    print(json.dumps(answer_question("Which students are enrolled in ASD101?", 5), indent=2))
