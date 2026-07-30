# Presentation Outline

Slide-by-slide notes for the PromptShield AI hackathon pitch. Pair with
[`demo_script.md`](demo_script.md) for the live portion and
[`architecture.md`](architecture.md) for diagrams to reuse.

## 1. Problem

Employees paste real prompts into public AI chat tools (ChatGPT, Gemini, Claude,
DeepSeek, Copilot). Those prompts can carry:

- Personal data (emails, phone numbers, national IDs, banking details)
- Secrets and credentials (API keys, tokens, private keys)
- Enterprise-sensitive content (internal architecture, source code, compliance-relevant
  business processes) that isn't PII at all, but still shouldn't leave the company

Existing DLP tools mostly catch the first two categories via regex/PII patterns. They
miss the third — a prompt with zero PII can still leak proprietary system design.

## 2. Solution

A browser extension that intercepts the prompt *before* it's sent, scans it through a
local detection API, and gives the user a clear choice: send sanitized, send as-is (when
allowed), or cancel. Nothing is silently blocked without explanation, and nothing is
silently sent without a check.

Two things make this different from keyword/regex-only DLP:

1. **Enterprise Context Intelligence (ECI)** — an LLM-based layer that judges *what a
   prompt is about*, not just what patterns appear in it, so "explain our OAuth2
   implementation" gets flagged even though it contains no PII or secrets.
2. **A fast pre-classification gate** in front of that LLM — most prompts never need it.

## 3. How it works (architecture)

Walk through the diagram in [`architecture.md`](architecture.md):

`Browser Extension → Presidio (PII/secrets) → Pre-Classifier (lexical + semantic gate)
→ ECI (LLM, only for ambiguous prompts) → Policy Engine → ALLOW/WARN/MASK/BLOCK`

Emphasize:
- Deterministic, explainable final decision (rules in `rules.json`, not a black box)
- Fail-open on network issues (never blocks typing), fail-closed on the AI classifier
  itself (never silently "safe"-passes a prompt when the LLM can't be reached)

## 4. Why the pre-classifier matters

- A naive design routes every non-trivial prompt to an LLM — 30–180s on local CPU
  hardware, unusable in a browser extension.
- The lexical (TF-IDF) tier resolves clearly-public and clearly-enterprise prompts in
  under 1ms using term-frequency statistics over the internal knowledge base, with no
  manual stopword list to maintain.
- The semantic tier (local MiniLM embeddings + FAISS) catches paraphrases/synonyms that
  keyword matching alone would miss, only for the genuinely ambiguous middle tier.
- Net effect: the LLM is reserved for a small fraction of requests, cutting both cost
  and latency, without sacrificing recall on real enterprise leaks.

## 5. Demo

Live walkthrough per [`demo_script.md`](demo_script.md): safe prompt → PII sanitize →
hard block on a secret → public technical question passes with no LLM call → the same
topic phrased as "our" implementation gets blocked with a visible AI Context Analysis.

## 6. What's built vs. what's next

Summarize from [`roadmap.md`](roadmap.md) — be specific and honest:

- **Built**: full detection pipeline, five-site browser extension, multi-provider LLM
  routing with fallback, property-tested pre-classifier.
- **Known gaps**: a couple of specific detection edge cases (documented, not hidden), a
  planned regex layer not yet built, sample fixtures not yet populated.
- **Next**: closing the documented detection gaps, audit logging, per-destination policy.

## 7. Team

See the [root README](../README.md#team) for current team/role listing.
