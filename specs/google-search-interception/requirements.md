# Requirements Document

## Introduction

PromptShield currently intercepts prompts only on dedicated AI chat sites (ChatGPT,
Gemini, Claude, DeepSeek, Microsoft Copilot). However, users frequently enter
sensitive data — PII, enterprise-internal information, proprietary code — into Google
Search surfaces that now feed directly into AI models: AI Overviews with follow-up
inputs, Google AI Mode (the conversational search interface at `udm=50`), and
Chrome's built-in AI features (Help me write, summarize, etc.).

This spec extends PromptShield's interception to cover these surfaces, using the same
scan -> review -> user-choice flow that existing sites use, adapted to each surface's
technical constraints.

## Glossary

- **AI Overviews**: Google Search's AI-generated answer panel shown at the top of
  search results, which includes a follow-up input box for conversational queries.
- **AI Mode**: Google Search's dedicated conversational AI interface, accessible via
  `google.com/search?udm=50`, featuring a chat-style input and suggestion chips.
- **NTP (New Tab Page)**: Chrome's built-in `chrome://newtab` page, which includes a
  search bar that navigates to Google Search.
- **Suggestion Chips**: Clickable follow-up query buttons rendered by Google AI Mode
  within the conversational panel.
- **Interstitial Page**: An extension-hosted HTML page shown to the user for review
  when the interception happens at the navigation level (not in-page).
- **Gemini Nano**: Chrome's built-in on-device/cloud AI features (Help me write,
  summarize, etc.) that communicate with Google's generative AI endpoints.

## Requirements

### Requirement 1: Google Search AI Overviews Interception

**User Story:** As a user searching on Google, I want PromptShield to scan my
follow-up queries in AI Overviews before they're sent, so that I don't accidentally
leak PII or enterprise data through conversational search.

#### Acceptance Criteria

1. WHEN a user types a query in the AI Overviews follow-up input and presses Enter or
   clicks the send button, THE system SHALL intercept the submission before it reaches
   Google's servers.
2. THE system SHALL extract the text from the follow-up input, send it to the scan
   API, and display the review dialog if the result is SANITIZE or BLOCK.
3. WHEN the scan result is SAFE, THE system SHALL allow the submission to proceed
   without user interruption.
4. WHEN the user clicks a suggestion chip in the AI Overviews panel, THE system SHALL
   extract the chip's text content, scan it, and intercept if the result is not SAFE.
5. THE system SHALL only activate on pages matching `google.com/search*` where the AI
   Overviews panel is present in the DOM.

### Requirement 2: Google AI Mode Interception

**User Story:** As a user using Google's AI Mode, I want PromptShield to scan my
conversational queries before they're sent, so that I'm protected from data leakage
in this chat-like search interface.

#### Acceptance Criteria

1. WHEN a user types a query in the AI Mode input area and submits (Enter key, send
   button, or form submit), THE system SHALL intercept the submission before it
   reaches Google's servers.
2. THE system SHALL recognize AI Mode pages (URLs containing `udm=50` or the AI Mode
   conversational panel DOM structure) and activate the full interception flow.
3. WHEN the user clicks a suggestion chip or follow-up prompt in AI Mode, THE system
   SHALL extract the chip's text, scan it, and show the review dialog if not SAFE.
4. THE system SHALL support the same review dialog UX as existing sites: show
   detected issues, original query, sanitized query, and Cancel / Send Sanitized /
   Send Original actions.
5. WHEN Send Sanitized is chosen, THE system SHALL replace the query text in the
   input with the sanitized version and replay the submission.

### Requirement 3: Google Homepage Search Interception

**User Story:** As a user searching from google.com's homepage, I want PromptShield
to scan my search query before it's sent, so that even initial searches containing
sensitive data are caught.

#### Acceptance Criteria

1. WHEN a user types a query in the google.com homepage search bar and submits (Enter
   key, click "Google Search" button, or form submit), THE system SHALL intercept the
   submission before the page navigates to search results.
2. THE system SHALL NOT activate on Google Search results pages (those are handled by
   Requirements 1 and 2) — only on the homepage (`/` path or empty path).
3. WHEN the scan result is SAFE, THE system SHALL allow the form submission / navigation
   to proceed immediately.
4. WHEN Send Sanitized is chosen, THE system SHALL update the search input value with
   the sanitized text and replay the form submission.
5. THE system SHALL handle Google's autocomplete/suggestion dropdown: if the user
   selects a suggestion and submits, the final submitted text is what gets scanned.

### Requirement 4: Chrome New Tab Page Search Interception

**User Story:** As a user searching from Chrome's New Tab Page, I want PromptShield
to catch my query before it reaches Google, so that PII typed directly into the
address bar or NTP search box is scanned.

#### Acceptance Criteria

1. WHEN a search query originating from Chrome's New Tab Page results in a navigation
   to `google.com/search?q=...`, THE system SHALL intercept the navigation before the
   Google Search page loads visually.
2. THE system SHALL extract the `q` parameter from the destination URL and send it to
   the scan API.
3. WHEN the scan result is SAFE, THE system SHALL allow the navigation to proceed
   without interruption.
4. WHEN the scan result is SANITIZE or BLOCK, THE system SHALL redirect the tab to an
   extension-hosted interstitial review page displaying the scan results and user
   actions.
5. THE interstitial page SHALL provide the same choices as the in-page review dialog:
   Cancel (close tab or navigate back), Send Sanitized (navigate to Google with the
   sanitized query), Send Original (navigate to the original URL).
6. THE system SHALL NOT intercept navigations to `google.com/search` that originate
   from pages other than the NTP (those are handled by the content script on the
   target page itself, avoiding double-interception).

### Requirement 5: Chrome Built-in AI (Gemini Nano) Best-Effort Monitoring

**User Story:** As a user using Chrome's built-in AI features, I want PromptShield to
monitor outbound AI requests and warn me if sensitive data is being sent, so that
browser-level AI features don't bypass my data protection.

#### Acceptance Criteria

1. THE system SHALL monitor outbound HTTP requests to known Google generative AI
   endpoints (e.g., `generativelanguage.googleapis.com`, and other discovered
   Gemini/AI endpoints).
2. WHEN a monitored request's body contains text content, THE system SHALL extract
   that text and send it to the scan API.
3. WHEN the scan result is SANITIZE or BLOCK, THE system SHALL display a Chrome
   notification to the user indicating that sensitive data was detected in an AI
   request.
4. THE system SHALL NOT block Chrome built-in AI requests (best-effort monitoring
   only) — it SHALL warn the user via notification but allow the request to proceed.
5. WHEN request payloads are opaque (encrypted, binary, or in an unrecognized format),
   THE system SHALL skip scanning gracefully without errors or user disruption.
6. THE system SHALL log monitored requests and scan results to the extension's console
   for debugging purposes.

### Requirement 6: Consistent Review Dialog UX

**User Story:** As a user, I want the same familiar review experience across all
intercepted surfaces, so that I always know how to respond to PromptShield alerts
regardless of where I'm browsing.

#### Acceptance Criteria

1. THE in-page review dialog shown on Google Search surfaces SHALL be visually and
   functionally identical to the existing review dialog used on ChatGPT, Gemini,
   Claude, etc.
2. THE interstitial review page (for NTP interception) SHALL use the same visual
   design language (dark theme, card layout, status badges, issue list, ECI section)
   as the in-page modal.
3. THE Chrome notification (for built-in AI monitoring) SHALL clearly identify
   PromptShield as the source and include the scan status and a brief reason.
4. ALL review surfaces SHALL show: scan status (SANITIZE/BLOCK), reason summary,
   detected issues with type/value/confidence, ECI analysis when available, and the
   original text.

### Requirement 7: No Double-Interception

**User Story:** As a user, I want to be prompted only once per query, not repeatedly
by overlapping interception mechanisms.

#### Acceptance Criteria

1. WHEN a search query from the NTP is intercepted by the webNavigation listener and
   redirected to the interstitial, THE content script on the eventual Google Search
   page SHALL NOT re-intercept that same query.
2. THE system SHALL use a coordination mechanism (e.g., session flag, tab state, or
   URL parameter) to communicate between the background worker and content scripts
   that a query has already been reviewed.
3. WHEN a user chooses "Send Original" or "Send Sanitized" from the interstitial, the
   resulting navigation to Google Search SHALL be marked as pre-approved and bypass
   content-script interception.

### Requirement 8: Extension Permissions and Performance

**User Story:** As a technical architect, I want the extension to request only
necessary permissions and maintain acceptable performance on Google pages.

#### Acceptance Criteria

1. THE manifest SHALL add only the minimum permissions needed: `webNavigation` (for
   NTP interception), `webRequest` (for Gemini Nano monitoring), and host permissions
   for `google.com`.
2. THE content script SHALL NOT measurably slow Google Search page load (MutationObserver
   should debounce re-scans using `requestAnimationFrame`, matching existing behavior).
3. THE webNavigation listener SHALL filter events efficiently (only process navigations
   matching `google.com/search` from NTP tabs) to avoid unnecessary background worker
   activity.
4. THE webRequest listener SHALL filter by URL pattern (only AI API endpoints) to
   minimize performance impact on general browsing.
