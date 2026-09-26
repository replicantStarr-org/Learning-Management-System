"""Answers questions from the indexed chunks: embed, top-k search, then Ollama."""

import time
from typing import Any

import requests

from .audit import append_audit
from .common import settings
from .vectors import embed_texts, get_collection, tokenise

INSUFFICIENT_EVIDENCE = "Insufficient evidence."


def retrieve_context(query: str, k: int | None = None, service: str | None = None) -> dict[str, Any]:
    start = time.time()
    k = k or settings()["retrieval"]["k"]
    tool_input = {"query": query, "k": k, "service": service}
    try:
        results = search(query, k, service)
    except Exception as exc:
        output = {"status": "error", "query": query, "error": str(exc)}
        append_audit("retrieve_context", tool_input, output, "error", start)
        return output

    output = {"status": "success", "query": query, "k": k, "results": results}
    append_audit(
        "retrieve_context",
        tool_input,
        {"result_count": len(results), "chunk_ids": [r["chunk_id"] for r in results]},
        "context_retrieved",
        start,
    )
    return output


def search(query: str, k: int, service: str | None) -> list[dict[str, Any]]:
    """Top-k chunks for the query, dropping any beyond the distance cut-off."""
    # A query made only of stopwords embeds to the zero vector, which has no
    # meaningful distance to anything.
    if not tokenise(query):
        return []

    collection = get_collection()
    if collection.count() == 0:
        return []

    found = collection.query(
        query_embeddings=embed_texts([query]),
        n_results=k,
        where={"service": service} if service else None,
    )
    max_distance = settings()["retrieval"]["max_distance"]
    results = []
    for chunk_id, text, metadata, distance in zip(
        found["ids"][0], found["documents"][0], found["metadatas"][0], found["distances"][0]
    ):
        if distance > max_distance:
            continue
        results.append(
            {
                "rank": len(results) + 1,
                "chunk_id": chunk_id,
                "service": metadata["service"],
                "entity": metadata["entity"],
                "record_id": metadata["record_id"],
                "title": metadata["title"],
                "distance": round(distance, 4),
                "text": text,
            }
        )
    return results


def confidence_from_results(results: list[dict[str, Any]]) -> str:
    if not results:
        return "None"
    best = results[0]["distance"]
    if best <= 0.6:
        return "High"
    if best <= 0.75:
        return "Medium"
    return "Low"


def generate_with_ollama(query: str, context: str) -> str:
    ollama = settings()["ollama"]
    # The chat endpoint with the rules in a system message: given the same text
    # as a single /api/generate prompt, qwen2.5:0.5b refused answerable questions.
    system = (
        "You answer questions about a university Learning Management System using only "
        "the records the user provides. Answer briefly. If the records do not contain "
        f"the answer, say exactly: {INSUFFICIENT_EVIDENCE}"
    )
    response = requests.post(
        ollama["url"].rstrip("/") + "/api/chat",
        json={
            "model": ollama["model"],
            "stream": False,
            # Temperature 0 keeps answers repeatable and stops the small model wandering.
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"Records:\n{context}\n\nQuestion: {query}"},
            ],
        },
        timeout=ollama["timeout_seconds"],
    )
    response.raise_for_status()
    return response.json().get("message", {}).get("content", "").strip() or INSUFFICIENT_EVIDENCE


def answer_question(query: str, k: int | None = None, service: str | None = None) -> dict[str, Any]:
    start = time.time()
    tool_input = {"query": query, "k": k, "service": service}
    retrieval = retrieve_context(query=query, k=k, service=service)
    if retrieval["status"] != "success":
        output = {"status": "error", "query": query, "error": retrieval["error"]}
        append_audit("answer_question", tool_input, output, "retrieval_failed", start)
        return output

    results = retrieval["results"]
    # Nothing close enough was found, so there is nothing to ground an answer
    # in; asking the model anyway would only invite it to make one up.
    if not results:
        answer = INSUFFICIENT_EVIDENCE
    else:
        context = "\n\n".join(r["text"] for r in results)
        try:
            answer = generate_with_ollama(query, context)
        except requests.RequestException as exc:
            output = {"status": "error", "query": query, "error": f"ollama unavailable: {exc}"}
            append_audit("answer_question", tool_input, output, "generation_failed", start)
            return output

    citations = [
        {"chunk_id": r["chunk_id"], "service": r["service"], "title": r["title"]} for r in results
    ]
    confidence = confidence_from_results(results)
    output = {
        "status": "success",
        "query": query,
        "answer": answer,
        "citations": citations,
        "confidence_category": confidence,
        "retrieval_summary": {
            "k": retrieval["k"],
            "retrieved_count": len(results),
            "top_chunk": results[0]["chunk_id"] if results else None,
        },
    }
    append_audit(
        "answer_question",
        tool_input,
        {"confidence_category": confidence, "citation_count": len(citations)},
        "answer_generated",
        start,
    )
    return output
