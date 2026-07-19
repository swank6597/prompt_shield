# Ollama + Phi-4-mini — Research Notes

Research into using Ollama with the Phi-4-mini model as the local AI risk-classification
engine for PromptShield AI. Goal: confirm it can reliably analyze text and return a
structured risk score + findings that our backend can parse.

## Setup

1. Install Ollama: https://ollama.com/download/windows
2. Verify install:
   ```
   ollama --version
   ```
3. Pull the model:
   ```
   ollama pull phi4-mini
   ```
   (~2.5GB download)
4. Quick interactive test:
   ```
   ollama run phi4-mini
   ```
5. Ollama exposes a local REST API automatically at `http://localhost:11434` — no
   separate server setup needed. This is what our ASP.NET backend will call via
   `HttpClient`.

## System requirements observed

- RAM: ~4GB used during inference (model itself is 2.5GB on disk)
- CPU-only inference works fine, no GPU required
- Tested on: 16GB RAM, Windows — no issues running alongside other dev tools

## Test methodology

All tests hit the `/api/generate` endpoint directly via `curl` before any C# code was
written, to validate the model's behavior in isolation first.

Base prompt template used for all tests:

```
Analyze this text for sensitive data. Respond with ONLY a raw JSON object,
no markdown formatting, no code fences, no backticks, no explanation.
Findings should be category labels only (e.g. EMAIL, PASSWORD, API_KEY),
not the actual sensitive values.
Format: {"risk": 0-100, "findings": [list]}.
Text: <test text here>
```

## Findings

### 1. Basic API connectivity — Pass
`/api/generate` responds correctly with a `response` field containing the model's output.

### 2. JSON output format — Pass, with caveat
The model reliably returns valid JSON content, but **frequently wraps it in markdown
code fences** (` ```json ... ``` `) even when explicitly instructed not to.

**Mitigation required:** strip everything before the first `{` and after the last `}`
in the response string before attempting to parse it as JSON. Do not rely on prompt
wording alone to guarantee fence-free output.

### 3. Determinism — Solved with `temperature: 0`
- Default settings: same input produced **different risk scores across runs**
  (e.g., 85 vs. 50 for the identical email-only test case). Not acceptable for a
  system that needs consistent policy decisions.
- With `"options": {"temperature": 0}` added to the request: ran the identical
  prompt **3 times in a row, got byte-identical output every time.**
- **Decision: always set `temperature: 0` in production calls.**

### 4. Severity scaling — Pass
Risk score scales sensibly with the number/type of sensitive items found:

| Test input | Risk Score | Findings |
|---|---|---|
| "The weather is nice today" | 0 | `[]` |
| "My email is john@company.com" | 20 | `["EMAIL"]` |
| "My password is Summer2024! and my email is john@company.com" | 75 | `["PASSWORD", "EMAIL"]` |

Multiple sensitive items correctly increase the risk score rather than just detecting
one and ignoring the rest.

### 5. Reliability note
Encountered one transient error during testing:
```
{"error":"model runner has unexpectedly stopped, this may be due to resource
limitations or an internal error, check ollama server logs for details"}
```
Recovered on retry with no further issues. Cause unclear (possibly memory pressure
from other running apps). Not seen as a repeatable blocker, but worth having a
retry/fallback in the actual backend code, and worth keeping demo-day machines free
of unnecessary background apps.

## Example working request

```
curl http://localhost:11434/api/generate -d "{\"model\": \"phi4-mini\", \"prompt\": \"Analyze this text for sensitive data. Respond with ONLY a raw JSON object, no markdown formatting, no code fences, no backticks, no explanation. Findings should be category labels only (e.g. EMAIL, PASSWORD, API_KEY), not the actual sensitive values. Format: {\\\"risk\\\": 0-100, \\\"findings\\\": [list]}. Text: My password is Summer2024! and my email is john@company.com\", \"stream\": false, \"options\": {\"temperature\": 0}}"
```

Example response:
```json
{
  "risk": 75,
  "findings": ["PASSWORD", "EMAIL"]
}
```
(after stripping markdown fences from the raw response)

## Decisions for the actual build

1. Always call Ollama with `"options": {"temperature": 0}` for consistent output.
2. Always strip markdown code fences from the response before `JsonSerializer.Deserialize`.
3. Proposed risk thresholds for the Policy Engine (to be tuned further once combined
   with regex-based hard rules):
   - `risk < 30` → Allow
   - `30–70` → Mask
   - `> 70` → Block
4. Regex-based detection (emails, API keys, JWTs, etc.) should remain the source of
   truth for *what* was found, since it's fully deterministic — Ollama's role is
   the overall risk judgment layer, not the primary detection mechanism.

## Next steps

- Wire this into the actual ASP.NET `/analyze` endpoint via `HttpClient`
- Combine with Presidio (Gaurav's prototype) and regex detectors
- Test combined pipeline end-to-end before building the Chrome extension
