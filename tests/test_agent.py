import json

import httpx
import pytest

from netops_agent.agent import Agent, OpenAICompatibleChat


def tool_call(i, name, args):
    return {"id": f"c{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


class ScriptedLLM:
    """Plays back assistant messages and records what it was sent."""

    def __init__(self, replies):
        self.replies = iter(replies)
        self.seen = []

    def complete(self, messages, tools):
        self.seen.append((list(messages), tools))
        return next(self.replies)


def test_agent_runs_tools_then_answers(client):
    llm = ScriptedLLM(
        [
            {
                "content": None,
                "tool_calls": [tool_call(1, "get_device_statuses", {"org_id": "1000001", "status": "offline"})],
            },
            {"content": "sjc-ap2 is offline."},
        ]
    )
    r = Agent(llm, client).ask("Which devices are offline?")
    assert r.answer == "sjc-ap2 is offline."
    assert r.api_calls == 1
    assert r.tool_calls[0]["name"] == "get_device_statuses"
    tool_msg = llm.seen[1][0][-1]
    assert tool_msg["role"] == "tool" and "sjc-ap2" in tool_msg["content"]
    assert {t["function"]["name"] for t in llm.seen[0][1]} >= {"list_organizations", "get_network_events"}


def test_agent_returns_tool_errors_to_model(client):
    llm = ScriptedLLM(
        [
            {"content": None, "tool_calls": [tool_call(1, "nope", {}), tool_call(2, "list_networks", {"bad": 1})]},
            {"content": "done"},
        ]
    )
    Agent(llm, client).ask("x")
    msgs = llm.seen[1][0]
    assert "unknown tool" in msgs[-2]["content"]
    assert "TypeError" in msgs[-1]["content"]


def test_agent_stops_at_step_limit(client):
    loop = {"content": None, "tool_calls": [tool_call(1, "list_organizations", {})]}
    r = Agent(ScriptedLLM([loop] * 3), client, max_steps=3).ask("x")
    assert "step limit" in r.answer and r.api_calls == 3


def test_openai_compatible_request_shape(monkeypatch):
    sent = {}

    def handler(req):
        sent["url"] = str(req.url)
        sent["auth"] = req.headers["authorization"]
        sent["body"] = json.loads(req.content)
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "hi"}}]})

    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    chat = OpenAICompatibleChat(api_key="sk", transport=httpx.MockTransport(handler))
    assert chat.complete([{"role": "user", "content": "q"}], [])["content"] == "hi"
    assert sent["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert sent["auth"] == "Bearer sk"
    assert sent["body"]["model"] == "google/gemma-4-31b-it:free"


def test_missing_llm_key_is_clear(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        OpenAICompatibleChat()
