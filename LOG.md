# Build log

Dated record of steps, measurements, and issues. Raw eval output lives in `results/`.

## Metrics

| Date | Model | Correct / 30 | API calls per answer | Notes |
|---|---|---|---|---|
| 2026-11-16 | google/gemma-4-31b-it:free | 0 / 30 | n/a | every request 429 (upstream rate limit); no answers |
| 2026-11-16 | nvidia/nemotron-3-ultra-550b-a55b:free | 17 / 30 (17 / 17 answered) | 1.94 per answered question (1.1 over all 30) | q18-q30 not run: OpenRouter free daily quota (50 requests) used up |

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

### 2026-11-16: real sandbox

- New reserved DevNet Meraki sandbox key. `GET /organizations` on `https://api.meraki.com/api/v1` returned 401; the org's shard host `https://n190.dashboard.meraki.com/api/v1` returned 200. Retried api.meraki.com after the eval (about an hour later): 200. Recording and truth used the shard host.
- Recorded real fixtures (9 API calls). Org `DevNet-47LAwcsYS1sK`, one network `branch_office` (appliance, camera, switch, wireless), 4 devices (MX100, MS250-24, MR52, MV12W), all dormant, all unnamed. Switch has 30 ports, all Disconnected, no PoE. No clients in the last day; no events in any log.
- Secret check: grepped fixtures for both key values and for psk/password/secret/token/apikey. None found. Nothing scrubbed. NOTICE.txt now says real sandbox data.
- Tests now assert real values (org id/name, 4 devices, 30 disconnected ports, empty clients and events).

### 2026-11-16: truth from live sandbox

- `eval/build_truth.py` against the live API: 30 answers, 9 API calls.
- The sandbox is idle, so many answers are trivial: q11, q12, q25, q29 are "none"; q14, q18, q19, q22, q24, q26, q27, q28, q30 are 0. q16 is a four-way tie (any model counts). q23 is QBSB-DU4U-25UB with 0 connected ports. Device names are empty, so name answers use serials.
- No question is unanswerable, so none were changed. The score on this sandbox mostly measures tool use and "zero/none" phrasing, not hard reasoning.

### 2026-11-16: eval

- Default `google/gemma-4-31b-it:free`: all 30 questions failed with 429 ("temporarily rate-limited upstream", Google AI Studio shared pool). The LLM client had no retry; added 429 retry with backoff (Retry-After, else 5s, 10s, 20s, 40s). Probed again 3 times 20s apart: still 429. `google/gemma-4-26b-a4b-it:free` also 429.
- Switched to `nvidia/nemotron-3-ultra-550b-a55b:free` (free, lists `tools`). q01-q17 answered, all correct. From q18 on every request returned 429: the key's free-model daily quota (50 requests/day) was used up (55 used). Result: `results/2026-11-17_nvidia-nemotron-3-ultra-550b-a55b-free.json` (UTC date in file name).
- Next: rerun q18-q30 after the quota resets, or use a key with credit.

## Issues

- **api.meraki.com 401, shard host 200.** Symptom: new sandbox key got 401 `No valid authentication method found` on api.meraki.com, 200 on `n190.dashboard.meraki.com`. Cause: likely key propagation to the global host lags for a brand-new key. Fix: use the shard host via `MERAKI_BASE_URL` until api.meraki.com accepts the key; it did about an hour later, so the default works once propagated.
- **Free default model rate-limited.** gemma-4 free models returned 429 from the upstream shared pool. Fix: LLM client retries 429 with backoff; for this run, switched model.
- **OpenRouter free quota too small for one eval.** 50 free requests/day; a full run needs about 60 (2 per question). Not fixed: needs a paid key or two days. Temporary: partial run logged above.
- **Sandbox too idle for a hard eval.** No clients, no events, no connected ports. Half the truth is 0 or none. Not fixed: needs a sandbox with traffic.

- **DevNet always-on sandbox key rejected.** Symptom: 401 on `GET /organizations` with both published keys. Cause: unknown from outside; the key was rotated or the always-on sandbox was retired (no current Cisco page lists it). Worked around 2026-11-16 with a reserved DevNet sandbox key.
- **Fixtures and truth were synthetic.** Fixed 2026-11-16: replaced with real sandbox data.
- **mcp 2.x renamed FastMCP.** `from mcp.server.fastmcp import FastMCP` fails in 2.3.0. Fix: use `mcp.server.mcpserver.MCPServer`; tool schema attribute is `input_schema`.
- **Retry gave the wrong error.** The last 429 fell through to the generic HTTP error, so "rate limited" never surfaced. Caught by a test; fixed by breaking out on the final attempt.
- **OASF record rejected at first.** Validator flagged the skill path and `locators[].url`. Fix: full skill path from the schema (`ai_ml_engineering/retrieval_augmented_generation/...`) and `urls` as a list; MCP module needs `data.name` and `data.connections`.
