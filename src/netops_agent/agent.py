"""Tool-calling agent loop over any OpenAI-compatible chat completions endpoint."""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from .client import MerakiClient
from .schema import bind, openai_schema
from .tools import TOOLS

DEFAULT_LLM_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_LLM_MODEL = "google/gemma-4-31b-it:free"

SYSTEM_PROMPT = (
    "You are a network operations assistant for a Cisco Meraki deployment. "
    "Answer only from tool results; call tools to look up organizations, networks, devices, "
    "port statuses, clients, and events. Start with list_organizations if you need an org id. "
    "Give a short, direct final answer with exact numbers and names."
)


class ChatModel(Protocol):
    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        """Return the assistant message dict (content and optional tool_calls)."""
        ...


class OpenAICompatibleChat:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        transport: httpx.BaseTransport | None = None,
        max_retries: int = 4,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.max_retries = max_retries
        self.sleep = sleep
        self.model = model or os.environ.get("LLM_MODEL") or DEFAULT_LLM_MODEL
        key = api_key if api_key is not None else os.environ.get("LLM_API_KEY", "")
        if not key:
            raise RuntimeError("LLM_API_KEY is not set")
        self._http = httpx.Client(
            base_url=(base_url or os.environ.get("LLM_BASE_URL") or DEFAULT_LLM_BASE_URL).rstrip("/"),
            headers={"Authorization": f"Bearer {key}"},
            timeout=120.0,
            transport=transport,
        )

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        payload = {"model": self.model, "messages": messages, "tools": tools, "temperature": 0}
        for attempt in range(self.max_retries + 1):
            resp = self._http.post("/chat/completions", json=payload)
            if resp.status_code != 429 or attempt == self.max_retries:
                break
            self.sleep(float(resp.headers.get("Retry-After", 5 * 2**attempt)))
        resp.raise_for_status()
        body = resp.json()
        if "choices" not in body:
            raise RuntimeError(f"LLM error: {body}")
        return body["choices"][0]["message"]


@dataclass
class AgentResult:
    answer: str
    api_calls: int
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    steps: int = 0


class Agent:
    def __init__(self, llm: ChatModel, client: MerakiClient, max_steps: int = 10) -> None:
        self.llm = llm
        self.client = client
        self.max_steps = max_steps
        self.tools = {fn.__name__: bind(fn, client) for fn in TOOLS}
        self.schemas = [openai_schema(f) for f in self.tools.values()]

    def ask(self, question: str) -> AgentResult:
        start_calls = self.client.calls
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]
        log: list[dict[str, Any]] = []
        for step in range(1, self.max_steps + 1):
            msg = self.llm.complete(messages, self.schemas)
            calls = msg.get("tool_calls") or []
            messages.append(
                {"role": "assistant", "content": msg.get("content"), **({"tool_calls": calls} if calls else {})}
            )
            if not calls:
                return AgentResult(msg.get("content") or "", self.client.calls - start_calls, log, step)
            for call in calls:
                name = call["function"]["name"]
                output = self._run_tool(name, call["function"].get("arguments") or "{}")
                log.append({"name": name, "arguments": call["function"].get("arguments")})
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": output})
        return AgentResult("(no answer: step limit reached)", self.client.calls - start_calls, log, self.max_steps)

    def _run_tool(self, name: str, raw_args: str) -> str:
        fn = self.tools.get(name)
        if fn is None:
            return json.dumps({"error": f"unknown tool {name}"})
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            return json.dumps(fn(**args), default=str)
        except Exception as e:  # noqa: BLE001  # tool errors go back to the model, not up the stack
            return json.dumps({"error": f"{type(e).__name__}: {e}"})


def main() -> None:
    question = " ".join(sys.argv[1:]) or "Which devices are offline?"
    result = Agent(OpenAICompatibleChat(), MerakiClient()).ask(question)
    print(result.answer)
    print(f"[api_calls={result.api_calls} steps={result.steps}]", file=sys.stderr)


if __name__ == "__main__":
    main()
