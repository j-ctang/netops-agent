"""Compute ground truth for eval/questions.jsonl from raw Meraki API data.

Live:     uv run python eval/build_truth.py
Offline:  uv run python eval/build_truth.py --fixtures tests/fixtures
Synthetic: uv run python eval/build_truth.py --synthetic
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from netops_agent.client import DEFAULT_BASE_URL, FixtureTransport, MerakiClient
from netops_agent.evaluation import Snapshot, truth

HERE = Path(__file__).parent


def main() -> None:
    ap = argparse.ArgumentParser()
    suite = ap.add_mutually_exclusive_group()
    suite.add_argument("--fixtures", type=Path, help="serve API responses from this directory")
    suite.add_argument("--synthetic", action="store_true", help="build reproducible truth for the synthetic suite")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    fixtures = Path("eval/fixtures/synthetic") if args.synthetic else args.fixtures
    fixture_dir = HERE / "fixtures" / "synthetic" if args.synthetic else fixtures
    output = args.out or HERE / ("truth.synthetic.json" if args.synthetic else "truth.json")
    client = (
        MerakiClient(api_key="offline", base_url=DEFAULT_BASE_URL, transport=FixtureTransport(fixture_dir))
        if fixture_dir
        else MerakiClient()
    )
    snap = Snapshot.fetch(client)
    questions = [json.loads(line) for line in (HERE / "questions.jsonl").read_text().splitlines() if line.strip()]
    out = {
        "source": f"fixtures:{fixtures.as_posix()}" if fixtures else client.base_url,
        **({} if args.synthetic else {"generated_at": datetime.now(UTC).isoformat(timespec="seconds")}),
        "api_calls": client.calls,
        "truth": {q["id"]: truth(q["kind"], q["params"], snap) for q in questions},
    }
    output.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {output}: {len(questions)} answers from {out['source']} ({client.calls} API calls)")


if __name__ == "__main__":
    main()
