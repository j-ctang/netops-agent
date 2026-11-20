import importlib.util
import json
import sys
from pathlib import Path

from netops_agent.client import FixtureTransport, MerakiClient
from netops_agent.evaluation import Snapshot, score, score_json, truth

ROOT = Path(__file__).parent.parent
SYNTHETIC_TRUTH = ROOT / "eval" / "truth.synthetic.json"


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


def test_json_scoring_rejects_incidental_matches():
    count = {"type": "number", "value": 1}
    assert score_json("1", count)
    assert not score_json("There are 2 APs, including 1 in the lobby.", count)
    assert not score_json("true", count)
    assert not score_json("1.0", count)

    names = {"type": "set", "value": ["HQ-Lab", "Harbor-Access"]}
    assert score_json('```json\n["Harbor-Access", "hq-lab"]\n```', names)
    assert not score_json('["HQ-Lab", "Harbor-Access", "HQ-Access"]', names)
    assert not score_json('["HQ-Lab", "Harbor-Access", "HQ-Lab"]', names)
    assert not score_json('["HQ-Lab-Backup", "Harbor-Access"]', names)
    assert score_json("[]", {"type": "set", "value": []})
    tied = {"type": "any_of", "value": ["MR36", "MS120-8LP"]}
    assert score_json('"MR36"', tied)
    assert score_json('"MS120-8LP"', tied)
    assert not score_json('"MR36 or MR46"', tied)


def synthetic_client():
    return MerakiClient(api_key="offline", transport=FixtureTransport(ROOT / "eval" / "fixtures" / "synthetic"))


def test_synthetic_truth_is_current_and_nonempty():
    client = synthetic_client()
    snapshot = Snapshot.fetch(client)
    questions = [json.loads(line) for line in (ROOT / "eval" / "questions.jsonl").read_text().splitlines()]
    checked = json.loads(SYNTHETIC_TRUTH.read_text())
    computed = {q["id"]: truth(q["kind"], q["params"], snapshot) for q in questions}
    assert checked["truth"] == computed
    assert checked["api_calls"] == client.calls == 21
    assert all(answer["value"] for answer in computed.values())
    # Staff wins across all sites, although Guest wins at headquarters and wired is the largest group.
    assert computed["q25"]["value"] == ["Staff"]
    assert computed["q26"]["value"] == 16
    # HQ-Lab logs the most switch events overall, but HQ-Access logs the most port_status events.
    assert computed["q28"]["value"] == 10
    assert computed["q29"]["value"] == ["HQ-Access"]
    assert computed["q30"]["value"] == 7


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


def test_synthetic_run_scores_tool_results_and_counts_failed_rows(monkeypatch, tmp_path):
    class EventLLM:
        model = "mock"

        def complete(self, messages, tools):
            question = messages[1]["content"]
            assert "Return only JSON." in question
            wireless = "wireless events" in question
            most = "most port_status" in question
            if messages[-1]["role"] == "user":
                network_ids = ["L_900000000000000101", "L_900000000000000102"]
                if not wireless:
                    network_ids.append("L_900000000000000201")
                params = (
                    {"product_type": "wireless"}
                    if wireless
                    else {"product_type": "switch", "event_type": "port_status"}
                )
                return {
                    "tool_calls": [
                        {
                            "id": network_id,
                            "function": {
                                "name": "get_network_events",
                                "arguments": json.dumps(dict(params, network_id=network_id)),
                            },
                        }
                        for network_id in network_ids
                    ]
                }
            events = [event for msg in messages if msg["role"] == "tool" for event in json.loads(msg["content"])]
            if most:
                raise RuntimeError("model failed after tools")
            if wireless:
                return {"content": f"There were 8 events, including {len(events)} wireless events."}
            return {"content": json.dumps(len(events))}

    runner = load_run()
    report = tmp_path / "benchmark.json"
    monkeypatch.setattr(runner, "OpenAICompatibleChat", EventLLM)
    monkeypatch.setenv("MERAKI_BASE_URL", "https://example.invalid/unrelated/prefix")
    monkeypatch.setattr(sys, "argv", ["run.py", "--synthetic", "--start", "27", "--limit", "3", "--out", str(report)])
    runner.main()
    out = json.loads(report.read_text())
    assert out["answer_format"] == "json"
    assert (out["correct"], out["total"], out["accuracy"], out["mean_api_calls"]) == (1, 3, 1 / 3, 2.67)
    assert [row["id"] for row in out["rows"]] == ["q28", "q29", "q30"]
    assert [row["api_calls"] for row in out["rows"]] == [3, 3, 2]
    assert [row["correct"] for row in out["rows"]] == [True, False, False]
    assert out["rows"][1]["error"] == "RuntimeError: model failed after tools"
