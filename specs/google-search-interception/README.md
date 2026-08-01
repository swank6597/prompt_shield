# Spec: Google Search & New Tab AI Interception

**Status: not started.** Extends PromptShield's interception coverage from dedicated
AI chat sites to Google Search AI surfaces (AI Overviews follow-ups, AI Mode), the
google.com homepage search bar, Chrome's New Tab Page search, and best-effort
monitoring of Chrome's built-in Gemini Nano/AI features.

## Documents (Kiro spec-driven workflow, requirements -> design -> tasks)

- **[`requirements.md`](requirements.md)** — EARS-style acceptance criteria covering
  each interception surface, UX behavior, and edge cases.
- **[`design.md`](design.md)** — architecture additions to the existing extension
  (site definitions, manifest changes, webNavigation interception, interstitial page,
  webRequest monitoring), with diagrams and component interfaces.
- **[`tasks.md`](tasks.md)** — implementation task breakdown with dependency graph;
  tasks checked off as they land.

## Why these surfaces matter

Users routinely paste enterprise data and PII into Google Search thinking it's "just
search" — but AI Overviews, AI Mode, and Chrome's built-in AI all send that text to
LLMs for processing. PromptShield's existing coverage only catches dedicated AI chat
UIs, leaving a significant data leakage vector unprotected.

## Surfaces covered

| Surface | Interception method | UX |
|---|---|---|
| Google AI Overviews (follow-up input) | Content script on `google.com/search` | In-page review dialog |
| Google AI Mode (`udm=50`) | Content script on `google.com/search` | In-page review dialog |
| google.com homepage search | Content script on `google.com` | In-page review dialog |
| Chrome New Tab Page search | `webNavigation.onCommitted` in background worker | Interstitial review page |
| Chrome built-in AI (Gemini Nano) | `webRequest.onBeforeRequest` in background worker | Chrome notification |

## If you're changing this system further

Update `requirements.md`/`design.md` first, then `tasks.md`, before editing
code directly — maintain the spec-driven workflow established in this project.
