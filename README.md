# netops-agent

A Python agent that answers network operations questions ("which switch ports flapped today?", "which SSIDs have the most clients?") by calling the Cisco Meraki Dashboard API. The tools are exposed through an MCP server so other agents can call them, and the agent is described by an [AGNTCY OASF](https://docs.agntcy.org/oasf/open-agentic-schema-framework/) record.

Evaluated on 30 questions whose ground truth is computed by code from raw API responses.

Status: in progress. See [LOG.md](LOG.md) for each step, measurements, and issues.

## Layout

| Path | What |
|---|---|
| `src/netops_agent/client.py` | Meraki API client: bearer auth, 429 retry with `Retry-After`, `Link` pagination, call counter |
| `src/netops_agent/tools.py` | Tools as typed functions: orgs, networks, devices, device statuses, switch port statuses, clients per SSID, events |
| `src/netops_agent/server.py` | MCP server (official `mcp` SDK) exposing the tools |
| `src/netops_agent/agent.py` | Tool-calling loop over any OpenAI-compatible chat completions API |
| `eval/` | 30 questions, `build_truth.py` (ground truth from raw API data), `run.py` (scorer) |
| `agntcy/record.json` | OASF agent record, validated against the OASF schema server |
| `tests/` | Offline tests; API responses served from `tests/fixtures` |

## Setup

```sh
uv sync
cp .env.example .env   # then fill in keys
set -a; source .env; set +a
```

| Variable | Default | Purpose |
|---|---|---|
| `MERAKI_API_KEY` | none | Meraki Dashboard API key |
| `MERAKI_BASE_URL` | `https://api.meraki.com/api/v1` | API base URL; a brand-new key may briefly need its org's shard host (e.g. `https://n190.dashboard.meraki.com/api/v1`) |
| `LLM_BASE_URL` | `https://openrouter.ai/api/v1` | OpenAI-compatible endpoint |
| `LLM_API_KEY` | none | LLM key (needed only for the agent and `eval/run.py`) |
| `LLM_MODEL` | `google/gemma-4-31b-it:free` | Model with tool calling |

## Use

```sh
uv run netops-agent "Which devices are offline?"     # agent
uv run netops-mcp                                     # MCP server on stdio
uv run python eval/build_truth.py                     # ground truth from the live API
uv run python eval/build_truth.py --fixtures tests/fixtures   # offline
uv run python eval/run.py                             # score the agent, writes results/
uv run pytest                                         # offline tests
```

`eval/truth.json` and `tests/fixtures` come from a live DevNet Meraki sandbox recorded 2026-11-16. That sandbox is small and idle, so many answers are 0 or none (see LOG.md).
