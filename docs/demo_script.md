# Demo Script

A suggested run-through for showing PromptShield live. Sample prompts and expected
outcomes are drawn from [`tests/test_scenarios.md`](../tests/test_scenarios.md), which
is the source of truth if behavior ever seems to drift from this script.

## Setup (before the audience sees anything)

1. Start the backend (see [`backend/README.md`](../backend/README.md)):
   ```powershell
   .\start-backend.ps1
   ```
   or manually: `cd backend && uvicorn app:app --reload --port 8081`.
2. Confirm it's healthy: open `http://localhost:8081/health`.
3. For fast, reliable LLM responses during the demo, set the cloud strategy in
   `backend/.env` rather than relying on local Ollama (which can take 30–180s on CPU):
   ```ini
   PROMPTSHIELD_LLM_STRATEGY=cloud
   PROMPTSHIELD_LLM_CLOUD_PROVIDER=groq
   PROMPTSHIELD_GROQ_API_KEY=gsk_...
   ```
4. Load the extension: `chrome://extensions` → Developer mode → Load unpacked →
   select `browser-extension/`.
5. Open a supported site (ChatGPT, Gemini, Claude, DeepSeek, or Copilot) and open
   DevTools console to show the `[Prompt Guardian]` logs live if useful.

## Script

### 1. Baseline — nothing to hide

Type: `Hi, how are you?`

- Expected: sent immediately, no popup (`ALLOW`/`SAFE`). Point out in the console log
  that this resolved via the trivial-prompt check with zero backend/LLM latency.

### 2. Simple PII → sanitize

Type: `My email is john.doe@example.com and my phone is 555-123-4567`

- Expected: send is intercepted, review modal opens showing `EMAIL_ADDRESS` and
  `PHONE_NUMBER` detected, with a sanitized version (`<EMAIL_ADDRESS>`, `<PHONE_NUMBER>`)
  available. Click **Send Sanitized** to show the composer text getting swapped before
  sending.

### 3. A secret/credential → hard block

Type: `My GitHub token is ghp_123456789012345678901234567890123456.`

- Expected: modal opens with `BLOCK` styling and **no "Send Original" option** — this
  is the one case the user cannot override from the UI. Explain this is intentional:
  secrets always force a block regardless of anything else in the prompt.

### 4. Public technical question → no LLM, no popup

Type: `Explain OAuth2.`

- Expected: sent immediately (`ALLOW`). This is the key "no false positive" moment —
  point out that older keyword-overlap approaches would have flagged this because it
  shares vocabulary with the internal knowledge base; the TF-IDF lexical tier correctly
  scores it `PUBLIC` and skips the LLM entirely.

### 5. The same vocabulary, but enterprise-specific → escalation + BLOCK

Type: `Explain our OAuth2 implementation.`

- Expected: this one *does* reach the LLM (ECI) because "our" plus internal-architecture
  framing pushes it past the lexical/semantic thresholds. Expect `containsInternalArchitecture: true`
  and a `BLOCK` decision. Good moment to open the modal's "AI Context Analysis" section
  and narrate the intent/confidence/risk-flag output.

### 6. Enterprise process question, not architecture → warn, not block

Type: `What are NovaBank's three enterprise data classification levels, and roughly what kind of information falls into each?`

- Expected: `WARN` (shown as `SANITIZE` to the user) — enterprise knowledge is required,
  but it's not architecture/source-code sensitive, so it doesn't escalate to `BLOCK`.

### 7. Fail-open resilience (optional, if time allows)

Stop the backend process, then type any prompt.

- Expected: the extension logs "API unavailable" and sends the prompt anyway (`SAFE`
  fallback) rather than blocking the user's workflow — demonstrates the fail-open
  design choice for the network path, in contrast to the fail-closed design of the ECI
  classifier itself when the LLM can't be reached.

## Backup talking points

- **Why three tiers before the LLM?** Local CPU inference can take 30–180s; routing
  everything to an LLM would make the extension unusable. The lexical/semantic
  pre-classifier resolves the large majority of prompts in under 200ms with zero LLM
  cost — see [`docs/architecture.md`](architecture.md).
- **Why is the risk score explainable?** The final ALLOW/WARN/MASK/BLOCK decision comes
  from declarative rules in `backend/policy/rules.json`, not a black-box model score —
  every decision can be traced to specific matched rules.
- **What's still rough?** Be upfront about known gaps if asked — see
  [`docs/roadmap.md`](roadmap.md) and `tests/test_scenarios.md`'s "known gap" sections
  (e.g. `BANK_ACCOUNT` currently unreachable, lone infrastructure identifiers under-flagged).
