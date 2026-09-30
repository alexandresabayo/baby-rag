#!/usr/bin/env python3
"""Evaluate retrieval hit@k over eval/questions.jsonl.

Each line: {"question": "...", "expected_path": "sample-....txt"}.
Requires an already-ingested corpus. Usage:
    python scripts/eval_retrieval.py [--k 3] [--api http://localhost:8000]
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--file", default=str(HERE.parent / "eval" / "questions.jsonl"))
    args = parser.parse_args()

    questions = [
        json.loads(line)
        for line in Path(args.file).read_text().splitlines()
        if line.strip()
    ]
    hits = 0
    for q in questions:
        req = urllib.request.Request(
            f"{args.api}/api/search",
            data=json.dumps({"query": q["question"], "top_k": args.k}).encode(),
            headers={"content-type": "application/json"},
        )
        results = json.loads(urllib.request.urlopen(req).read())["results"]
        paths = {r["path"] for r in results}
        ok = q["expected_path"] in paths
        hits += ok
        mark = "hit " if ok else "miss"
        print(f"{mark}  {q['question'][:60]:60s} -> {sorted(paths)}")

    rate = hits / len(questions) if questions else 0.0
    print(f"\nhit@{args.k}: {hits}/{len(questions)} = {rate:.1%}")
    sys.exit(0 if questions else 1)


if __name__ == "__main__":
    main()
