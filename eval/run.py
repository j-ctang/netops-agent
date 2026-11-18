"""Run the agent on every eval question and score it against eval/truth.json.

uv run python eval/run.py [--fixtures tests/fixtures] [--limit N] [--start N] [--out FILE]
Writes results/<date>_<model>.json.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from netops_agent.agent import Agent, ChatModel, OpenAICompatibleChat
from netops_agent.client import FixtureTransport, MerakiClient
from netops_agent.evaluation import score

HERE = Path(__file__).parent
RESULTS = HERE.parent / "results"


def run(
    llm: ChatModel, client: MerakiClient, truth_file: Path, model: str, limit: int | None = None, start: int = 0
) -> dict:
    questions = [json.loads(line) for line in (HERE / "questions.jsonl").read_text().splitlines() if line.strip()]
    truth = json.loads(truth_file.read_text())
    agent = Agent(llm, client)
    rows = []
    for q in questions[start:limit]:
        expected = truth["truth"][q["id"]]
        try:
            r = agent.ask(q["question"])
            answer, calls, tools, err = r.answer, r.api_calls, r.tool_calls, None
        except Exception as e:  # noqa: BLE001 - record the failure, keep scoring
            answer, calls, tools, err = "", 0, [], f"{type(e).__name__}: {e}"
        rows.append(
            {
                "id": q["id"],
                "question": q["question"],
                "expected": expected,
                "answer": answer,
                "correct": score(answer, expected),
                "api_calls": calls,
                "tool_calls": tools,
                "error": err,
            }
        )
    n = len(rows)
    return {
        "model": model,
        "truth_source": truth["source"],
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "correct": sum(r["correct"] for r in rows),
        "total": n,
        "mean_api_calls": round(sum(r["api_calls"] for r in rows) / n, 2) if n else 0,
        "rows": rows,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures")
    ap.add_argument("--truth", default=str(HERE / "truth.json"))
    ap.add_argument("--limit", type=int)
    ap.add_argument("--start", type=int, default=0, help="skip the first N questions")
    ap.add_argument("--out", help="output path (default results/<date>_<model>.json)")
    args = ap.parse_args()
    client = (
        MerakiClient(api_key="offline", transport=FixtureTransport(args.fixtures)) if args.fixtures else MerakiClient()
    )
    llm = OpenAICompatibleChat()
    out = run(llm, client, Path(args.truth), llm.model, args.limit, args.start)
    RESULTS.mkdir(exist_ok=True)
    path = (
        Path(args.out)
        if args.out
        else RESULTS / f"{datetime.now(UTC):%Y-%m-%d}_{re.sub(r'[^A-Za-z0-9.-]+', '-', llm.model)}.json"
    )
    path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"{out['correct']}/{out['total']} correct, {out['mean_api_calls']} API calls per answer -> {path}")


if __name__ == "__main__":
    main()
