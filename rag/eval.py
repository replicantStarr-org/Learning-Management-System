"""Retrieval precision and recall at k against the seed data of each service.

Run after ingesting with every configured service up. A result counts as
relevant when its chunk id starts with one of the benchmark's expected prefixes.
"""

from pathlib import Path

from pipeline.querying import retrieve_context

METRICS_PATH = Path(__file__).resolve().parent / "retrieval-metrics.md"
K = 5

BENCHMARKS = [
    {
        "query": "When is the Release 0 Technical Report due?",
        "relevant": ["assignments:assignment:1:"],
    },
    {
        "query": "Who coordinates Database Systems?",
        "relevant": ["subjects:subject:2:"],
    },
    {
        "query": "What does CI/CD stand for?",
        "relevant": ["quizzes:quiz:1:", "assignments:assignment:3:"],
    },
    {
        "query": "Which assignments are due for AIT505 Applied Artificial Intelligence?",
        "relevant": ["assignments:assignment:10:", "assignments:assignment:11:", "assignments:assignment:12:"],
    },
    {
        "query": "Which subjects run in the Winter semester?",
        "relevant": ["subjects:subject:6:", "subjects:subject:7:", "subjects:subject:11:", "subjects:subject:13:"],
    },
    {
        "query": "Who wrote Attention Is All You Need?",
        "relevant": ["learning-resources:resource:1:"],
    },
    {
        "query": "What does alex.wong have on Tuesday?",
        "relevant": ["timetable:entry:3:", "timetable:entry:4:"],
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
