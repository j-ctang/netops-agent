import importlib.util
import json
from pathlib import Path

from netops_agent.evaluation import Snapshot, score, truth

ROOT = Path(__file__).parent.parent


def load_run():
    spec = importlib.util.spec_from_file_location("eval_run", ROOT / "eval" / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_score_kinds():
    assert score("There are 25 connected ports.", {"type": "number", "value": 25})
    assert not score("There are 250 ports.", {"type": "number", "value": 25})
    assert score("1,024 clients", {"type": "number", "value": 1024})
    assert score("sjc-ap2 and rtp-ap2", {"type": "set", "value": ["rtp-ap2", "sjc-ap2"]})
    assert not score("only sjc-ap2", {"type": "set", "value": ["rtp-ap2", "sjc-ap2"]})
    assert score("No devices are offline.", {"type": "set", "value": []})
    assert score("MR36", {"type": "any_of", "value": ["MR36", "MR46"]})


def test_truth_from_fixtures(client):
    s = Snapshot.fetch(client)
    assert truth("device_count", {"product_type": "switch"}, s) == {"type": "number", "value": 1}
    assert truth("top_ssid", {}, s) == {"type": "set", "value": []}
    assert truth("port_count", {"status": "Disconnected"}, s)["value"] == 30
    assert truth("devices_with_status", {"status": "dormant"}, s)["value"] == [
        "QBSA-BT9H-9GNH",
        "QBSB-DU4U-25UB",
        "QBSC-C83J-XEMY",
        "QBSD-CF57-HTY7",
    ]


def test_every_question_has_truth(client):
    s = Snapshot.fetch(client)
    qs = [json.loads(line) for line in (ROOT / "eval" / "questions.jsonl").read_text().splitlines()]
    assert len(qs) == 30 and len({q["id"] for q in qs}) == 30
    for q in qs:
        truth(q["kind"], q["params"], s)


def test_run_scores_with_mock_llm(client, tmp_path):
    t = {"source": "test", "truth": {f"q{i:02d}": {"type": "number", "value": 1} for i in range(1, 31)}}
    (tmp_path / "truth.json").write_text(json.dumps(t))

    class OneLLM:
        def complete(self, messages, tools):
            if messages[-1]["role"] == "user":
                return {
                    "content": None,
                    "tool_calls": [{"id": "a", "function": {"name": "list_organizations", "arguments": "{}"}}],
                }
            return {"content": "The answer is 1."}

    out = load_run().run(OneLLM(), client, tmp_path / "truth.json", "mock", limit=3)
    assert (out["correct"], out["total"], out["mean_api_calls"]) == (3, 3, 1.0)
