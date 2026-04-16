"""
Retrieval evaluation script.

Runs a set of gold queries against the live search API and reports:
  - Recall@K: fraction of queries where a relevant result appears in top-K
  - MRR: Mean Reciprocal Rank
  - Average latency

Usage:
    # With the API running on localhost:8000:
    python scripts/eval_retrieval.py

    # Point at a different API:
    API_URL=http://my-api:8000 python scripts/eval_retrieval.py

    # Use a gold dataset file (JSON):
    python scripts/eval_retrieval.py --gold eval/gold_queries.json

Gold dataset format (JSON array):
    [
      {
        "query": "what is the notice period for termination",
        "expected_keywords": ["notice", "termination", "30 days"],
        "expected_files": ["employee-handbook.pdf"]
      },
      ...
    ]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import httpx
except ImportError:
    print("Install httpx: pip install httpx")
    sys.exit(1)

API_URL = os.getenv("API_URL", "http://localhost:8000")
TOP_K = int(os.getenv("EVAL_TOP_K", "5"))

# Built-in demo gold queries — replace with your own after uploading test docs.
_BUILTIN_GOLD: list[dict] = [
    {
        "query": "termination notice period",
        "expected_keywords": ["notice", "terminat"],
        "expected_files": [],
    },
    {
        "query": "employee benefits and leave policy",
        "expected_keywords": ["leave", "benefit", "policy"],
        "expected_files": [],
    },
    {
        "query": "show me org chart or team structure diagram",
        "expected_keywords": ["org", "team", "structure"],
        "expected_files": [],
    },
]


def _hit_check(result: dict, query_spec: dict) -> bool:
    """Return True if result satisfies any expected keyword or file name."""
    snippet = (result.get("snippet") or "").lower()
    file_name = (result.get("fileName") or "").lower()

    for kw in query_spec.get("expected_keywords", []):
        if kw.lower() in snippet or kw.lower() in file_name:
            return True

    for fname in query_spec.get("expected_files", []):
        if fname.lower() in file_name:
            return True

    return False


def _reciprocal_rank(results: list[dict], query_spec: dict) -> float:
    for rank, result in enumerate(results, start=1):
        if _hit_check(result, query_spec):
            return 1.0 / rank
    return 0.0


def run_eval(gold_queries: list[dict], top_k: int = TOP_K) -> None:
    client = httpx.Client(base_url=API_URL, timeout=30)

    hits = 0
    rr_sum = 0.0
    latencies = []
    failed = []

    print(f"\nRunning {len(gold_queries)} queries against {API_URL} (top_k={top_k})\n")
    print(f"{'Query':<55} {'Hit':>5}  {'RR':>6}  {'ms':>6}")
    print("-" * 78)

    for spec in gold_queries:
        query = spec["query"]
        try:
            t0 = time.monotonic()
            resp = client.post(
                "/search",
                json={"query": query, "topK": top_k, "includeAnswer": False},
            )
            latency = int((time.monotonic() - t0) * 1000)
            resp.raise_for_status()

            results = resp.json().get("results", [])
            hit = any(_hit_check(r, spec) for r in results)
            rr = _reciprocal_rank(results, spec)

            hits += int(hit)
            rr_sum += rr
            latencies.append(latency)

            q_display = query[:53] + ".." if len(query) > 55 else query
            print(f"{q_display:<55} {'✓' if hit else '✗':>5}  {rr:>6.3f}  {latency:>5}ms")

        except Exception as exc:
            failed.append((query, str(exc)))
            print(f"{query[:55]:<55} {'ERR':>5}  {'—':>6}  {'—':>6}  {exc}")

    n = len(gold_queries) - len(failed)
    if n == 0:
        print("\nNo successful queries — is the API running?")
        return

    recall_at_k = hits / n
    mrr = rr_sum / n
    p95 = sorted(latencies)[int(0.95 * len(latencies))] if latencies else 0

    print("\n" + "=" * 78)
    print(f"  Queries evaluated : {n}")
    print(f"  Recall@{top_k:<3}          : {recall_at_k:.2%}")
    print(f"  MRR               : {mrr:.4f}")
    print(f"  Avg latency       : {sum(latencies)//len(latencies) if latencies else 0} ms")
    print(f"  p95 latency       : {p95} ms")
    if failed:
        print(f"\n  Failed queries ({len(failed)}):")
        for q, e in failed:
            print(f"    - {q[:60]}: {e}")
    print("=" * 78)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate retrieval quality")
    parser.add_argument(
        "--gold", help="Path to JSON gold query file", default=None
    )
    parser.add_argument(
        "--top-k", type=int, default=TOP_K, help=f"Top-K to evaluate (default {TOP_K})"
    )
    args = parser.parse_args()

    if args.gold:
        with open(args.gold) as f:
            gold = json.load(f)
    else:
        gold = _BUILTIN_GOLD
        print("No --gold file specified. Using built-in demo queries.")
        print("Upload test documents first, then create a gold dataset.")

    run_eval(gold, top_k=args.top_k)


if __name__ == "__main__":
    main()
