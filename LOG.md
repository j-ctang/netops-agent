# Build log

Dated record of steps, measurements, and issues. Raw eval output lives in `results/`.

## Metrics

| Date | Model | Correct / 30 | API calls per answer | Notes |
|---|---|---|---|---|

No agent runs yet: no LLM key available.

## Steps

### 2026-11-16: sandbox check

- Tried both read-only keys Cisco has published for the DevNet always-on Meraki sandbox (`6bec40cf...` from a Cisco staff reply in the [DevNet community](https://community.cisco.com/t5/devnet-sandbox/wrong-api-key-in-sandbox-for-meraki-dashboard/m-p/4500222), and `75dd5334...`). `GET https://api.meraki.com/api/v1/organizations` returned `401 {"errors":["No valid authentication method found"]}` for both.
- The current Meraki getting-started page no longer prints a sandbox key, and the old DevNet sandbox catalog URL redirects to a generic sandbox page with no Meraki always-on entry. Stopped the live part here.

### 2026-11-16: client and tools

- `MerakiClient` (httpx): bearer auth, retries 429 using `Retry-After` (exponential fallback), follows `Link: rel=next`, counts every HTTP request so the eval can report API calls per answer.
- Seven tools as plain typed functions. Filters (status, product type, network) are applied client side so one call answers most questions.
- Fixtures in `tests/fixtures` are synthetic (see Issues). `python -m netops_agent.record` saves real responses in the same layout once a key works.

### 2026-11-16: MCP server and OASF record

- `netops-mcp` exposes the tools with the official `mcp` SDK (2.3.0). `bind()` strips the client argument so the MCP schema and the LLM schema come from the same signature.
- AGNTCY: wrote `agntcy/record.json`, an OASF agent record with skills, domains, a source locator, and the `integration/mcp` module that says how to start the server. It validates with 0 errors against `https://schema.oasf.outshift.com/api/validate/object/record` (schema 1.1.0).

### 2026-11-16: agent loop

- OpenAI-compatible chat completions with tool calling via httpx. Tool errors go back to the model as JSON; 10 step limit.
- Default model `google/gemma-4-31b-it:free`: listed by OpenRouter's `/api/v1/models` on 2026-11-16 as free with `tools` in `supported_parameters`. Free models on OpenRouter change often; override with `LLM_MODEL`.
- Tests drive the loop with a scripted LLM; no key needed.

### 2026-11-16: eval harness

- 30 questions in `eval/questions.jsonl`. Each has a `kind`; `build_truth.py` fetches raw responses once and computes the answer in code (`netops_agent/evaluation.py`). Ties are stored as "any of".
- Scoring: numbers must appear in the answer; sets need every name present; "none" counts for an empty set.
- `eval/truth.json` was generated from the synthetic fixtures (14 API calls), not the live sandbox.

### 2026-11-16: CI

- GitHub Actions: `uv sync --locked`, ruff check, ruff format check, pytest. Offline only.

## Issues

- **DevNet always-on sandbox key rejected.** Symptom: 401 on `GET /organizations` with both published keys. Cause: unknown from outside; the key was rotated or the always-on sandbox was retired (no current Cisco page lists it). Not fixed. Needs a working key (a reservable DevNet Meraki sandbox or a personal org).
- **Fixtures and truth are synthetic.** Consequence of the issue above. Fixtures follow the v1 response shapes but every value is made up. Temporary: rerun `python -m netops_agent.record tests/fixtures` and `eval/build_truth.py` with a working key.
- **mcp 2.x renamed FastMCP.** `from mcp.server.fastmcp import FastMCP` fails in 2.3.0. Fix: use `mcp.server.mcpserver.MCPServer`; tool schema attribute is `input_schema`.
- **Retry gave the wrong error.** The last 429 fell through to the generic HTTP error, so "rate limited" never surfaced. Caught by a test; fixed by breaking out on the final attempt.
- **OASF record rejected at first.** Validator flagged the skill path and `locators[].url`. Fix: full skill path from the schema (`ai_ml_engineering/retrieval_augmented_generation/...`) and `urls` as a list; MCP module needs `data.name` and `data.connections`.
