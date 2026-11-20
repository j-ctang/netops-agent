"""Run the agent on every eval question and score it against eval/truth.json.

uv run python eval/run.py [--synthetic | --fixtures DIR] [--limit N] [--start N] [--out FILE]
Writes results/<date>_<model>.json.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from netops_agent.agent import Agent, ChatModel, OpenAICompatibleChat
from netops_agent.client import DEFAULT_BASE_URL, FixtureTransport, MerakiClient
from netops_agent.evaluation import score, score_json

HERE = Path(__file__).parent
RESULTS = HERE.parent / "results"
JSON_INSTRUCTIONS = (
    "\n\nReturn only JSON. Use an integer for a count, an array of strings for a list of names "
    "(an empty array if none), or a string for a single name. If multiple names tie for most, give one."
)


def run(
    llm: ChatModel,
    client: MerakiClient,
    truth_file: Path,
    model: str,
    limit: int | None = None,
    start: int = 0,
    *,
    json_answers: bool = False,
) -> dict:
    questions = [json.loads(line) for line in (HERE / "questions.jsonl").read_text().splitlines() if line.strip()]
    truth = json.loads(truth_file.read_text())
    agent = Agent(llm, client)
    rows = []
    scorer = score_json if json_answers else score
    suffix = JSON_INSTRUCTIONS if json_answers else ""
    stop = start + limit if limit is not None else None
    for q in questions[start:stop]:
        expected = truth["truth"][q["id"]]
        before = client.calls
        try:
            r = agent.ask(q["question"] + suffix)
            answer, tools, err = r.answer, r.tool_calls, None
        except Exception as e:  # noqa: BLE001 - record the failure, keep scoring
            answer, tools, err = "", [], f"{type(e).__name__}: {e}"
        rows.append(
            {
                "id": q["id"],
                "question": q["question"],
                "expected": expected,
                "answer": answer,
                "correct": err is None and scorer(answer, expected),
                "api_calls": client.calls - before,
                "tool_calls": tools,
                "error": err,
            }
        )
    n = len(rows)
    correct = sum(r["correct"] for r in rows)
    return {
        "model": model,
        "truth_source": truth["source"],
        "answer_format": "json" if json_answers else "text",
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "correct": correct,
        "total": n,
        "accuracy": correct / n if n else 0,
        "mean_api_calls": round(sum(r["api_calls"] for r in rows) / n, 2) if n else 0,
        "rows": rows,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    suite = ap.add_mutually_exclusive_group()
    suite.add_argument("--fixtures", type=Path)
    suite.add_argument("--synthetic", action="store_true", help="use the synthetic fixtures and exact JSON scoring")
    ap.add_argument("--truth", type=Path)
    ap.add_argument("--limit", type=int, help="maximum number of questions after --start")
    ap.add_argument("--start", type=int, default=0, help="skip the first N questions")
    ap.add_argument("--out", help="output path (default results/<date>_<model>.json)")
    args = ap.parse_args()
    if args.start < 0 or (args.limit is not None and args.limit < 0):
        ap.error("--start and --limit must be non-negative")
    fixtures = HERE / "fixtures" / "synthetic" if args.synthetic else args.fixtures
    truth_file = args.truth or HERE / ("truth.synthetic.json" if args.synthetic else "truth.json")
    client = (
        MerakiClient(api_key="offline", base_url=DEFAULT_BASE_URL, transport=FixtureTransport(fixtures))
        if fixtures
        else MerakiClient()
    )
    llm = OpenAICompatibleChat()
    out = run(llm, client, truth_file, llm.model, args.limit, args.start, json_answers=args.synthetic)
    model_slug = re.sub(r"[^A-Za-z0-9.-]+", "-", llm.model)
    suite_suffix = "_synthetic" if args.synthetic else ""
    path = Path(args.out) if args.out else RESULTS / f"{datetime.now(UTC):%Y-%m-%d}_{model_slug}{suite_suffix}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"{out['correct']}/{out['total']} correct, {out['mean_api_calls']} API calls per answer -> {path}")


if __name__ == "__main__":
    main()
