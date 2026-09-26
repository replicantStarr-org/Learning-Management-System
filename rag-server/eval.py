"""Retrieval precision and recall at k against the seed data of each service.

Run after ingesting with every implemented service up. A result counts as
relevant when its chunk id starts with one of the benchmark's expected prefixes.
Each connector adds its own benchmarks here (see pipeline/connectors/AGENTS.md).
"""

from pathlib import Path

from pipeline.querying import retrieve_context

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


def evaluate_query(benchmark: dict) -> dict:
    results = retrieve_context(benchmark["query"], K).get("results", [])
    relevant = [r for r in results if is_relevant(r["chunk_id"], benchmark["relevant"])]
    found_records = {p for p in benchmark["relevant"] if any(r["chunk_id"].startswith(p) for r in results)}

    return {
        "query": benchmark["query"],
        "retrieved_chunk_ids": [r["chunk_id"] for r in results],
        "relevant_chunk_ids": [r["chunk_id"] for r in relevant],
        "p_at_k": round(len(relevant) / K, 2),
        "r_at_k": round(len(found_records) / len(benchmark["relevant"]), 2),
    }


def write_metrics_report(results: list[dict]) -> None:
    lines = ["# Retrieval Metrics", ""]
    for result in results:
        lines.append(f"## {result['query']}")
        lines.append(f"- Retrieved: {result['retrieved_chunk_ids']}")
        lines.append(f"- Relevant: {result['relevant_chunk_ids']}")
        lines.append(f"- P@{K}: {result['p_at_k']}")
        lines.append(f"- R@{K}: {result['r_at_k']}")
        lines.append("")
    METRICS_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    results = []
    for benchmark in BENCHMARKS:
        result = evaluate_query(benchmark)
        results.append(result)
        print("Query:", result["query"])
        print("Retrieved:", result["retrieved_chunk_ids"])
        print("Relevant:", result["relevant_chunk_ids"])
        print(f"P@{K}:", result["p_at_k"])
        print(f"R@{K}:", result["r_at_k"])
        print("---")
    write_metrics_report(results)


if __name__ == "__main__":
    main()
