# Implementation Plan: Google Search & New Tab AI Interception

## Overview

Implements `requirements.md`/`design.md`: extends PromptShield's interception coverage
to Google Search AI surfaces (AI Overviews, AI Mode), google.com homepage, Chrome's
New Tab Page search, and best-effort monitoring of Chrome's built-in Gemini Nano/AI
features. Each task builds incrementally on the previous, producing a demoable result
at every step.

## Tasks

- [x] 1. Update manifest.json with Google permissions and new APIs
  - Add `"webNavigation"`, `"webRequest"`, `"notifications"` to `permissions` array
  - Add `"https://www.google.com/*"`, `"https://google.com/*"` to `host_permissions`
  - Add `"*://generativelanguage.googleapis.com/*"`, `"*://alkali-pa.googleapis.com/*"`,
    `"*://content-push.googleapis.com/*"` to `host_permissions`
  - Add `"https://www.google.com/*"`, `"https://google.com/*"` to
    `content_scripts[0].matches`
  - Add `"https://www.google.com/*"`, `"https://google.com/*"` to
    `web_accessible_resources[0].matches`
  - Add new `web_accessible_resources` entry for `"interstitial/*"` with
    `"matches": ["<all_urls>"]`
  - Verify extension loads in Chrome without manifest errors
  - _Requirements: 8.1_
  - _Demo: Extension loads without errors; visiting google.com shows Prompt Guardian
    service worker active in chrome://extensions_

- [x] 2. Add `pathExclusions` support to `createSiteDefinition`
  - Modify `createSiteDefinition` in `content/site-definitions.js` to accept an
    optional `pathExclusions` array
  - Update `matchUrl` to return `false` when the URL pathname starts with any entry
    in `pathExclusions`
  - Add unit-style verification: existing site definitions remain unaffected (no
    `pathExclusions` set = current behavior unchanged)
  - _Requirements: 3.2, 8.2_
  - _Demo: Existing sites (ChatGPT, Gemini, Claude, etc.) continue to match correctly;
    `createSiteDefinition` now supports exclusion patterns_

- [x] 3. Add Google Search AI site definition
  - Add `google-search-ai` entry to `SITE_DEFINITIONS` in `content/site-definitions.js`
  - Hosts: `["www.google.com", "google.com"]`
  - `pathPrefixes: ["/search"]`
  - Prompt selectors targeting AI Mode input, AI Overviews follow-up input, and
    standard search refinement boxes (see design.md Section 1)
  - Send selectors targeting Search/Send/Ask buttons
  - Prompt and send hints: `["search", "ask", "follow up", "query", "ai mode"]` /
    `["search", "send", "submit", "ask"]`
  - Position this entry BEFORE the google-homepage definition in the array
  - Test: `findSiteDefinition("https://www.google.com/search?q=test")` returns
    `google-search-ai`
  - Test: `findSiteDefinition("https://www.google.com/search?q=test&udm=50")` returns
    `google-search-ai`
  - _Requirements: 1.5, 2.2_
  - _Demo: Open google.com/search?q=test in Chrome, DevTools console shows
    `[Prompt Guardian] Google Search AI Detected`_

- [x] 4. Add Google Homepage site definition
  - Add `google-homepage` entry to `SITE_DEFINITIONS` after `google-search-ai`
  - Hosts: `["www.google.com", "google.com"]`
  - `pathExclusions: ["/search", "/maps", "/mail", "/drive", "/calendar", "/docs"]`
  - Prompt selectors targeting `textarea[name='q']`, `input[name='q']`,
    `textarea[aria-label*='Search' i]`
  - Send selectors targeting `input[name='btnK']`, `input[name='btnI']`,
    `button[aria-label*='Google Search' i]`, `button[type='submit']`
  - Test: `findSiteDefinition("https://www.google.com/")` returns `google-homepage`
  - Test: `findSiteDefinition("https://www.google.com/webhp")` returns `google-homepage`
  - Test: `findSiteDefinition("https://www.google.com/search?q=x")` does NOT return
    `google-homepage`
  - Test: `findSiteDefinition("https://www.google.com/maps")` returns `null` (excluded)
  - _Requirements: 3.1, 3.2_
  - _Demo: Open google.com in Chrome, DevTools console shows
    `[Prompt Guardian] Google Homepage Detected`_

- [x] 5. Checkpoint — content script activation on Google surfaces
  - Verify on live google.com: content script loads, correct site definition selected
  - Verify on google.com/search: content script loads, `google-search-ai` selected
  - Verify on google.com/search?udm=50 (AI Mode): same definition activates
  - Verify that existing supported sites still work correctly (regression check)
  - Verify the prompt text area and send button are found on google.com homepage
  - _Requirements: 1.5, 2.2, 3.1, 8.2_
  - _Demo: Type "my email is test@example.com" in google.com search bar, press Enter —
    the review dialog appears showing detected EMAIL_ADDRESS issue_

- [x] 6. Refine DOM detection for Google AI Mode and AI Overviews
  - Live-test on google.com/search?udm=50 (AI Mode): inspect the actual DOM to confirm
    or adjust prompt selectors, send selectors, and scope selectors
  - Live-test on google.com/search with AI Overviews visible: inspect the follow-up
    input DOM and adjust selectors if needed
  - Update `promptHints` and `sendHints` based on actual aria-labels and attributes
    found in the live DOM
  - Ensure `detector.js`'s weighted scoring picks the correct element when multiple
    textareas/inputs exist on a Google Search page
  - _Requirements: 1.1, 2.1, 2.5_
  - _Demo: In Google AI Mode, type a PII-containing query and press Enter — extension
    intercepts, scans, and shows review dialog. Choose "Send Sanitized" — the
    sanitized text replaces the input and the search submits_

- [x] 7. Implement suggestion chip interceptor (`content/chip-interceptor.js`)
  - Create `browser-extension/content/chip-interceptor.js` with
    `createChipInterceptor` function (see design.md Section 2)
  - Implement document-level click listener (capture phase) that detects clicks on
    elements matching chip selectors
  - Extract chip text from `innerText`, `data-followup-text`, `data-q`, or similar
  - On intercept: call `scanClient.scanPrompt(chipText)`
  - If SAFE: set bypass flag, replay click
  - If SANITIZE/BLOCK: show review dialog with appropriate options
  - Handle "Send Original" (replay click) and "Cancel" (drop click) actions
  - Handle "Send Sanitized" by writing to the prompt input if available and submitting
  - _Requirements: 1.4, 2.3_
  - _Demo: In Google AI Mode, click a suggestion chip — extension intercepts, shows
    the chip text being scanned, and presents the review dialog_

- [x] 8. Wire chip interceptor into content.js bootstrap
  - In `content/content.js`, conditionally import and start the chip interceptor when
    the site definition is `google-search-ai`
  - Add `chip-interceptor.js` to `web_accessible_resources` if not already covered by
    the `"content/*.js"` pattern
  - Verify chip interceptor and observer run side-by-side without conflicts
  - _Requirements: 1.4, 2.3, 6.1_
  - _Demo: Both typed queries (via observer) and chip clicks (via chip interceptor)
    are intercepted on Google AI Mode — full interception coverage on search pages_

- [x] 9. Checkpoint — full content-script interception on Google surfaces
  - End-to-end test: google.com homepage with PII -> review dialog -> send sanitized
    -> correct sanitized query submitted
  - End-to-end test: Google AI Mode typed query with PII -> review dialog -> cancel
    -> nothing sent
  - End-to-end test: Google AI Overviews follow-up with PII -> review dialog -> send
    original -> original query sent
  - End-to-end test: Google AI Mode suggestion chip click -> intercepted and scanned
  - Regression: ChatGPT, Gemini, Claude, DeepSeek, Copilot still work
  - _Requirements: 1.1-1.4, 2.1-2.5, 3.1-3.5, 6.1_
  - _Demo: Full demonstration of in-page interception across all three Google
    content-script surfaces (homepage, AI Overviews, AI Mode) including chip clicks_

- [x] 10. Implement NTP navigation interceptor (`background/ntp-interceptor.js`)
  - Create `browser-extension/background/ntp-interceptor.js` with
    `startNtpInterceptor` function (see design.md Section 3)
  - Add `chrome.webNavigation.onCommitted` listener filtered by
    `{ url: [{ hostContains: "google", pathPrefix: "/search" }] }`
  - Detect NTP origin via `transitionType` ("typed" / "generated") and
    `transitionQualifiers` ("from_address_bar")
  - Extract `q` parameter from the destination URL
  - Check bypass flag in `chrome.storage.session` before scanning
  - Call scan API; if SAFE, allow navigation to proceed
  - If SANITIZE/BLOCK: store scan results in `chrome.storage.session` keyed by tab ID,
    then redirect tab to `interstitial/review.html?tabId=<id>`
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.6, 8.3_
  - _Demo: Open a new tab, type "my SSN is 123-45-6789" in the address bar, press
    Enter — instead of Google loading, the tab redirects to the interstitial page
    (blank/placeholder at this stage)_

- [x] 11. Build interstitial review page (`interstitial/`)
  - Create `browser-extension/interstitial/review.html` — page shell with proper
    meta tags, links to review.css and review.js
  - Create `browser-extension/interstitial/review.css` — styles matching the in-page
    modal's dark theme, card layout, status badges, issue list (reuse design language
    from `content/modal.js`)
  - Create `browser-extension/interstitial/review.js`:
    - Read `tabId` from URL search params
    - Load scan data from `chrome.storage.session.get("scan_<tabId>")`
    - Render: status badge, reason, issues list, ECI section (if available), original
      query, sanitized query
    - Handle error state (missing/expired data): show "Scan data not found" with
      "Go Back" button
    - Wire action buttons:
      - Cancel: navigate to `chrome://newtab` or close tab
      - Send Original: set `bypass_<tabId>` in session storage, then
        `chrome.tabs.update(tabId, { url: originalUrl })`
      - Send Sanitized: set bypass flag, navigate to
        `google.com/search?q=<encoded sanitized query>`
    - Clean up scan data from session storage after rendering
  - _Requirements: 4.4, 4.5, 6.2, 6.4_
  - _Demo: After NTP interception redirects to interstitial, the page displays a
    polished review UI showing detected PII, original query, sanitized query, and
    three action buttons — all functional_

- [x] 12. Wire NTP interceptor into background.js
  - Import `startNtpInterceptor` in `background/background.js`
  - Call it with `{ Logger, scanPrompt }` (reuse existing `scanPrompt` function)
  - Ensure it doesn't conflict with the existing `PROMPT_GUARDIAN_SCAN_PROMPT`
    message handler
  - _Requirements: 4.1, 8.3_
  - _Demo: Full NTP interception flow works end-to-end: new tab -> type PII -> Enter
    -> interstitial appears -> choose action -> correct navigation occurs_

- [x] 13. Implement anti-double-interception coordination
  - In `background/ntp-interceptor.js`: when a query passes (SAFE or user-approved),
    set `chrome.storage.session.set({ bypass_tab_<tabId>: true })`
  - Add `PROMPT_GUARDIAN_GET_TAB_ID` message handler in `background/background.js`
    that responds with `sender.tab.id`
  - In `content/content.js`: on initialization, request own tab ID from background,
    check `chrome.storage.session.get("bypass_tab_<tabId>")`, and if set:
    - Clear the flag
    - Set `observer.bypassOnce = true` (or skip the first interception cycle)
    - Log: `[Prompt Guardian] Bypass flag set: skipping first interception`
  - Add cleanup: background worker removes bypass flags older than 30 seconds via a
    periodic check or alarm
  - Test: NTP search with PII -> approve in interstitial -> Google page loads ->
    content script does NOT re-intercept
  - Test: Regular navigation to google.com/search (not from NTP) -> content script
    intercepts normally (no bypass flag exists)
  - _Requirements: 7.1, 7.2, 7.3_
  - _Demo: Approve a query in the interstitial, Google Search loads immediately
    without a second interception popup_

- [x] 14. Checkpoint — NTP interception end-to-end
  - End-to-end test: New tab -> type PII query -> interstitial -> Cancel -> returns
    to new tab
  - End-to-end test: New tab -> type PII query -> interstitial -> Send Sanitized ->
    Google Search loads with sanitized query
  - End-to-end test: New tab -> type PII query -> interstitial -> Send Original ->
    Google Search loads with original query, no double-interception
  - End-to-end test: New tab -> type safe query -> Google Search loads immediately
    (no interstitial)
  - End-to-end test: Navigate to google.com/search from a bookmark (not NTP) ->
    content script handles interception (NTP interceptor does not fire)
  - _Requirements: 4.1-4.6, 7.1-7.3_
  - _Demo: Complete NTP interception workflow demonstrated across all paths (safe,
    sanitize, block, cancel) with no double-interception_

- [x] 15. Implement Gemini Nano monitor (`background/gemini-monitor.js`)
  - Create `browser-extension/background/gemini-monitor.js` with
    `startGeminiMonitor` function (see design.md Section 5)
  - Add `chrome.webRequest.onBeforeRequest` listener with URL filters for
    `generativelanguage.googleapis.com`, `alkali-pa.googleapis.com`,
    `content-push.googleapis.com`
  - Implement `extractTextFromRequestBody`: decode raw bytes, parse JSON, extract text
    from Gemini API payload structures (`contents[].parts[].text`, `prompt`, `text`,
    `input`)
  - Handle opaque/binary payloads gracefully (return null, skip scan)
  - Call scan API with extracted text
  - If not SAFE: create Chrome notification via `chrome.notifications.create()`
  - Log all monitored requests and scan results to console
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 8.4_
  - _Demo: Trigger a Chrome built-in AI feature (e.g., "Help me write") with PII in
    the input — a Chrome notification appears from PromptShield warning about
    sensitive data; DevTools shows the request was intercepted and scanned_

- [x] 16. Wire Gemini monitor into background.js
  - Import `startGeminiMonitor` in `background/background.js`
  - Call it with `{ Logger, scanPrompt }` after the NTP interceptor
  - Ensure webRequest listener runs without errors even when no Gemini requests occur
  - _Requirements: 5.1, 8.4_
  - _Demo: Extension runs normally with Gemini monitor active; no errors in service
    worker console during regular browsing_

- [x] 17. Update extension popup and documentation
  - Update `popup/popup.html` to list the new supported surfaces (Google Search AI,
    Google Homepage, NTP, Chrome AI)
  - Update `browser-extension/README.md`:
    - Add Google surfaces to "Supported Sites" section
    - Document NTP interception behavior
    - Document Gemini Nano monitoring (best-effort)
    - Update "Current Features" list
  - _Requirements: 6.3_
  - _Demo: Extension popup shows updated list of protected surfaces_

- [x] 18. Final checkpoint — feature complete
  - End-to-end: Google AI Overviews follow-up with PII -> review dialog -> send
    sanitized -> correct sanitized query sent
  - End-to-end: Google AI Mode typed query with PII -> review dialog -> cancel ->
    nothing sent
  - End-to-end: Google AI Mode chip click -> intercepted and scanned
  - End-to-end: Google homepage search with PII -> review dialog -> send original ->
    original query proceeds
  - End-to-end: NTP search with PII -> interstitial -> send sanitized -> Google loads
    with sanitized query, no double-interception
  - End-to-end: Chrome built-in AI with PII -> notification appears
  - Regression: ChatGPT, Gemini, Claude, DeepSeek, Copilot still work correctly
  - Performance: Google Search page load is not measurably slowed
  - Verify extension loads cleanly, no manifest warnings, no console errors during
    normal browsing
  - _Requirements: all_
  - _Demo: Full demonstration across all five surfaces — typed queries, chip clicks,
    NTP searches, and Chrome AI — PromptShield intercepts on every surface with
    appropriate UX (in-page dialog, interstitial, notification)_

## Notes

- Suggestion chip selectors will need refinement against live Google DOM — they change
  frequently. The initial set is best-guess from known patterns; Task 7 includes live
  DOM inspection and adjustment.
- The Gemini Nano monitor is explicitly best-effort (Requirement 5). If Chrome's AI
  payloads use binary/protobuf encoding that can't be parsed, the monitor gracefully
  skips those requests.
- Google frequently updates their DOM structure. The site definitions may need
  periodic maintenance. Consider adding a "selector health check" diagnostic in a
  future spec.

## Task Dependency Graph

```
1 (manifest)
 |
 v
2 (pathExclusions) --> 3 (google-search-ai def) --> 4 (google-homepage def)
                                                          |
                                                          v
                                                    5 (checkpoint: activation)
                                                          |
                                                          v
                                                    6 (refine DOM detection)
                                                          |
                                                          v
                                                    7 (chip-interceptor.js) --> 8 (wire into content.js)
                                                                                    |
                                                                                    v
                                                                              9 (checkpoint: content scripts)
                                                                                    |
                                              +-------------------------------------+
                                              |                                     |
                                              v                                     v
                                    10 (NTP interceptor)              15 (Gemini monitor)
                                              |                                     |
                                              v                                     v
                                    11 (interstitial page)            16 (wire Gemini into bg)
                                              |                                     |
                                              v                                     |
                                    12 (wire NTP into bg)                            |
                                              |                                     |
                                              v                                     |
                                    13 (anti-double-interception)                    |
                                              |                                     |
                                              v                                     |
                                    14 (checkpoint: NTP e2e)                         |
                                              |                                     |
                                              +-------------------------------------+
                                              |
                                              v
                                        17 (docs/popup update)
                                              |
                                              v
                                        18 (final checkpoint)
```
