"""Compute ground truth for eval/questions.jsonl from raw Meraki API data.

Live:     uv run python eval/build_truth.py
Offline:  uv run python eval/build_truth.py --fixtures tests/fixtures
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from netops_agent.client import FixtureTransport, MerakiClient
from netops_agent.evaluation import Snapshot, truth

HERE = Path(__file__).parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", help="serve API responses from this directory instead of the live API")
    ap.add_argument("--out", default=str(HERE / "truth.json"))
    args = ap.parse_args()
    client = (
        MerakiClient(api_key="offline", transport=FixtureTransport(args.fixtures)) if args.fixtures else MerakiClient()
    )
    snap = Snapshot.fetch(client)
    questions = [json.loads(line) for line in (HERE / "questions.jsonl").read_text().splitlines() if line.strip()]
    out = {
        "source": f"fixtures:{args.fixtures}" if args.fixtures else client.base_url,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "api_calls": client.calls,
        "truth": {q["id"]: truth(q["kind"], q["params"], snap) for q in questions},
    }
    Path(args.out).write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {args.out}: {len(questions)} answers from {out['source']} ({client.calls} API calls)")


if __name__ == "__main__":
    main()
