"""Retrieval precision and recall at k against the seed data of each service.

Run after ingesting with every implemented service up:

    .venv_rag/bin/python eval.py                    every benchmark; writes retrieval-metrics.md
    .venv_rag/bin/python eval.py --service NAME     only that service's benchmarks
    .venv_rag/bin/python eval.py --json             the results as JSON, writing nothing

The agentic loop's RAG review runs `--service NAME --json` and reports what
comes back, so everything about how retrieval is scored lives here.

A result counts as relevant when its chunk id starts with one of the benchmark's
expected prefixes. Each connector adds its own benchmarks here (see
pipeline/connectors/AGENTS.md).

A benchmark passes when P@k reaches its ceiling and R@k is 1.0. P@k is judged
against its ceiling rather than 1.0: a benchmark with one relevant record can
have at most one relevant result in the top k, so 1/k is the best it can score.
"""

import argparse
import json
from pathlib import Path

import chromadb
from chromadb.errors import NotFoundError

from pipeline.common import resolve_path, settings
from pipeline.querying import retrieve_context
from pipeline.vectors import embedding_signature

METRICS_PATH = Path(__file__).resolve().parent / "retrieval-metrics.md"
K = 5

BENCHMARKS = [
    {
        "query": "Who wrote Attention Is All You Need?",
        "relevant": ["learning-resources:learning_resource:1:"],
    },
    {
        "query": "Which papers are about generative adversarial networks?",
        "relevant": ["learning-resources:learning_resource:2:"],
    },
    {
        # Matched only through the tags: no title or description says mathematics.
        "query": "What authors have written about mathematics?",
        "relevant": [
            "learning-resources:learning_resource:14:",
            "learning-resources:learning_resource:15:",
            "learning-resources:learning_resource:16:",
            "learning-resources:learning_resource:17:",
        ],
    },
]


def is_relevant(chunk_id: str, prefixes: list[str]) -> bool:
    return any(chunk_id.startswith(prefix) for prefix in prefixes)


def inspect_index(service: str | None) -> tuple[int, str | None]:
    """How many chunks are indexed (for the service, if named), and why the index
    cannot be evaluated, if it cannot.

    Opened directly and read only, before anything goes through
    pipeline.vectors.get_collection(): that rebuilds the collection empty when
    config.toml's embedding differs from the one the index was built with, and
    measuring the index must never wipe it.
    """
    chroma = settings()["chroma"]
    client = chromadb.PersistentClient(path=str(resolve_path(chroma["path"])))
    try:
        collection = client.get_collection(chroma["collection"])
    except NotFoundError:
        return 0, "no index has been built yet; start the RAG server and ingest"

    built_with = (collection.metadata or {}).get("embedding")
    if built_with != embedding_signature():
        return 0, (
            f"the index was built with embedding {built_with} but config.toml now asks for "
            f"{embedding_signature()}; restart the RAG server and re-ingest"
        )

    indexed = len(collection.get(where={"service": service} if service else None, include=[])["ids"])
    if not indexed:
        return 0, f"nothing is indexed{f' for {service}' if service else ''}; ingest first"
    return indexed, None


def evaluate_query(benchmark: dict) -> dict:
    results = retrieve_context(benchmark["query"], K).get("results", [])
    relevant = [r for r in results if is_relevant(r["chunk_id"], benchmark["relevant"])]
    found_records = {p for p in benchmark["relevant"] if any(r["chunk_id"].startswith(p) for r in results)}

    p_at_k = round(len(relevant) / K, 2)
    r_at_k = round(len(found_records) / len(benchmark["relevant"]), 2)
    p_ceiling = round(min(len(benchmark["relevant"]), K) / K, 2)
    return {
        "query": benchmark["query"],
        "retrieved_chunk_ids": [r["chunk_id"] for r in results],
        "relevant_chunk_ids": [r["chunk_id"] for r in relevant],
        "p_at_k": p_at_k,
        "p_ceiling": p_ceiling,
        "r_at_k": r_at_k,
        "passed": p_at_k >= p_ceiling and r_at_k == 1.0,
    }


def evaluate(service: str | None = None) -> dict:
    """Every benchmark for the service (all of them when None), scored against the
    index as it stands, or the reason the index could not be scored."""
    benchmarks = [
        b for b in BENCHMARKS
        if service is None or any(prefix.startswith(f"{service}:") for prefix in b["relevant"])
    ]
    indexed, problem = inspect_index(service)
    output = {"k": K, "service": service, "indexed": indexed, "benchmarks": len(benchmarks)}
    if problem:
        return {**output, "unavailable": problem, "results": []}
    return {**output, "results": [evaluate_query(b) for b in benchmarks]}


def write_metrics_report(results: list[dict]) -> None:
    lines = ["# Retrieval Metrics", ""]
    for result in results:
        lines.append(f"## {result['query']}")
        lines.append(f"- Retrieved: {result['retrieved_chunk_ids']}")
        lines.append(f"- Relevant: {result['relevant_chunk_ids']}")
        lines.append(f"- P@{K}: {result['p_at_k']} (ceiling {result['p_ceiling']})")
        lines.append(f"- R@{K}: {result['r_at_k']}")
        lines.append(f"- {'PASS' if result['passed'] else 'FAIL'}")
        lines.append("")
    METRICS_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Score retrieval against the benchmarks.")
    parser.add_argument("--service", help="only this service's benchmarks, e.g. learning-resources")
    parser.add_argument("--json", action="store_true", help="print the results as JSON and write nothing")
    args = parser.parse_args()

    evaluation = evaluate(args.service)
    if args.json:
        print(json.dumps(evaluation))
        return 0
    if "unavailable" in evaluation:
        print("Cannot evaluate:", evaluation["unavailable"])
        return 1

    for result in evaluation["results"]:
        print("Query:", result["query"])
        print("Retrieved:", result["retrieved_chunk_ids"])
        print("Relevant:", result["relevant_chunk_ids"])
        print(f"P@{K}:", result["p_at_k"], f"(ceiling {result['p_ceiling']})")
        print(f"R@{K}:", result["r_at_k"])
        print("PASS" if result["passed"] else "FAIL")
        print("---")
    write_metrics_report(evaluation["results"])
    return 0 if all(result["passed"] for result in evaluation["results"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
