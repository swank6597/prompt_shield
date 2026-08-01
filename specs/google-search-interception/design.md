# Design Document: Google Search & New Tab AI Interception

## Overview

This design extends PromptShield's existing modular architecture to cover five new
interception surfaces. The approach reuses the content-script pipeline (site
definitions -> detector -> observer -> scan -> review dialog) for Google web surfaces,
and adds two new background-worker-level mechanisms for NTP and built-in AI.

The key architectural principle: **use content scripts wherever possible** (same
proven pattern), and fall back to background-worker interception only for surfaces
where content scripts can't reach (`chrome://newtab`, built-in AI features).

## Architecture

```
+--------------------------------------------------------------------------------+
|                        Content Script Layer (google.com/*)                       |
+--------------------------------------------------------------------------------+
|                                                                                 |
|  +---------------------+  +---------------------+  +---------------------+     |
|  | google-search-ai    |  | google-ai-mode      |  | google-homepage     |     |
|  | (AI Overviews)      |  | (udm=50 chat)       |  | (/ search bar)      |     |
|  | site-definitions.js |  | site-definitions.js |  | site-definitions.js |     |
|  +----------+----------+  +----------+----------+  +----------+----------+     |
|             |                        |                        |                 |
|             +------------------------+------------------------+                 |
|                                      v                                         |
|                    +------------------------------------------+                 |
|                    |  detector.js + observer.js               |                 |
|                    |  (existing pattern, unchanged core)      |                 |
|                    +--------------------+---------------------+                 |
|                                         |                                      |
|                    +------------------------------------------+                 |
|                    |  chip-interceptor.js (NEW)               |                 |
|                    |  Intercepts suggestion chip clicks,      |                 |
|                    |  extracts text, feeds into scanClient    |                 |
|                    +--------------------+---------------------+                 |
|                                         |                                      |
+--------------------------------------------------------------------------------+
                                          | chrome.runtime.sendMessage
                                          v
+--------------------------------------------------------------------------------+
|                        Background Worker (background.js)                         |
+--------------------------------------------------------------------------------+
|                                                                                 |
|  +------------------------------+   +---------------------------------------+  |
|  | PROMPT_GUARDIAN_SCAN_PROMPT   |   | NTP Navigation Interceptor (NEW)     |  |
|  | (existing message handler)   |   | chrome.webNavigation.onCommitted     |  |
|  |                               |   | - detect google.com/search from NTP  |  |
|  |                               |   | - extract ?q= param                  |  |
|  |                               |   | - scan via API                       |  |
|  |                               |   | - redirect to interstitial if needed |  |
|  +------------------------------+   +---------------------------------------+  |
|                                                                                 |
|  +-------------------------------------------------------------------------+   |
|  | Gemini Nano Monitor (NEW)                                                |   |
|  | chrome.webRequest.onBeforeRequest                                        |   |
|  | - filter: generativelanguage.googleapis.com/*                            |   |
|  | - extract text from requestBody                                          |   |
|  | - scan via API                                                           |   |
|  | - notify user via chrome.notifications if not SAFE                       |   |
|  +-------------------------------------------------------------------------+   |
|                                                                                 |
+--------------------------------------------------------------------------------+
                                          |
                                          v fetch()
                                  +------------------+
                                  | Backend API      |
                                  | POST /api/scan   |
                                  +------------------+
```

## Component Design

### 1. Site Definitions (`content/site-definitions.js`)

Add two new site definitions. Google AI surfaces (AI Overviews follow-up and AI Mode)
share one definition since they're on the same domain and differ only by URL
path/parameters. The homepage is separate to avoid matching search result pages.

```javascript
createSiteDefinition({
  id: "google-search-ai",
  label: "Google Search AI",
  hosts: ["www.google.com", "google.com"],
  pathPrefixes: ["/search"],
  promptSelectors: [
    // AI Mode conversational input
    "textarea[aria-label*='Search' i]",
    "div[contenteditable='true'][aria-label*='Search' i]",
    "div[contenteditable='true'][role='textbox']",
    // AI Overviews follow-up input
    "input[aria-label*='Ask a follow up' i]",
    "textarea[aria-label*='follow' i]",
    // Standard search refinement
    "textarea[name='q']",
    "input[name='q']",
    // Generic fallbacks
    ...COMMON_PROMPT_SELECTORS
  ],
  sendSelectors: [
    "button[aria-label*='Search' i]",
    "button[aria-label*='Send' i]",
    "button[aria-label*='Ask' i]",
    "button[type='submit']",
    ...COMMON_SEND_SELECTORS
  ],
  promptScopeSelectors: [
    "form[action='/search']",
    "[role='search']",
    ...COMMON_SCOPE_SELECTORS
  ],
  sendScopeSelectors: [
    "form[action='/search']",
    "[role='search']",
    ...COMMON_SCOPE_SELECTORS
  ],
  promptHints: ["search", "ask", "follow up", "query", "ai mode"],
  sendHints: ["search", "send", "submit", "ask"]
})
```

```javascript
createSiteDefinition({
  id: "google-homepage",
  label: "Google Homepage",
  hosts: ["www.google.com", "google.com"],
  // Custom matchUrl logic needed: match "/" and "/webhp" but NOT "/search*"
  promptSelectors: [
    "textarea[name='q']",
    "input[name='q']",
    "textarea[aria-label*='Search' i]",
    ...COMMON_PROMPT_SELECTORS
  ],
  sendSelectors: [
    "input[name='btnK']",
    "input[name='btnI']",
    "button[aria-label*='Google Search' i]",
    "button[type='submit']",
    ...COMMON_SEND_SELECTORS
  ],
  promptScopeSelectors: [
    "form[action='/search']",
    "[role='search']",
    ...COMMON_SCOPE_SELECTORS
  ],
  sendScopeSelectors: [
    "form[action='/search']",
    "[role='search']",
    ...COMMON_SCOPE_SELECTORS
  ],
  promptHints: ["search", "google", "query"],
  sendHints: ["search", "submit", "feeling lucky"]
})
```

**Ordering matters:** `google-search-ai` must appear before `google-homepage` in the
`SITE_DEFINITIONS` array so that `/search` URLs are matched by the more specific
definition first. `findSiteDefinition` returns the first match.

**Homepage path matching:** The `google-homepage` definition needs a custom `matchUrl`
override (or a post-match filter in `createSiteDefinition`) that returns `false` when
the pathname starts with `/search`. This can be done by adding a `pathExclusions`
option to `createSiteDefinition`:

```javascript
// Addition to createSiteDefinition:
matchUrl(url) {
  try {
    const parsedUrl = new URL(url);
    const hostMatches = matchesHostname(parsedUrl.hostname, site.hosts);
    const pathExcluded = site.pathExclusions?.some(
      (prefix) => parsedUrl.pathname.startsWith(prefix)
    );
    if (pathExcluded) return false;
    const pathMatches = !site.pathPrefixes?.length
      ? true
      : site.pathPrefixes.some((prefix) => parsedUrl.pathname.startsWith(prefix));
    return hostMatches && pathMatches;
  } catch {
    return false;
  }
}
```

The homepage definition uses: `pathExclusions: ["/search", "/maps", "/mail", "/drive"]`
to avoid activating on non-search Google services.

### 2. Suggestion Chip Interceptor (`content/chip-interceptor.js` — NEW)

Google AI Mode renders suggestion chips as clickable elements containing pre-set
follow-up queries. These bypass the text input entirely — the user clicks, and the
query is sent without typing. We need to intercept these clicks.

**Interface:**

```javascript
/**
 * Creates a chip interceptor that monitors clicks on suggestion elements
 * and routes their text through the scan pipeline before allowing.
 *
 * @param {{
 *   Logger: { info: Function, warn: Function, error: Function },
 *   scanClient: { scanPrompt: (text: string) => Promise<object> },
 *   reviewDialog: { show: (payload: object) => void, hide: () => void },
 *   chipSelectors: string[],
 *   documentRef: Document,
 *   windowRef: Window
 * }} params
 * @returns {{ start: () => void, stop: () => void }}
 */
export function createChipInterceptor(params) { ... }
```

**Chip selectors** (to be refined via live DOM inspection of Google AI Mode):

```javascript
const GOOGLE_CHIP_SELECTORS = [
  // AI Mode suggestion chips
  "[data-chip-action]",
  "[data-followup-text]",
  ".suggestion-chip",
  "[role='listitem'] button",
  ".related-question-pair button",
  // AI Overviews follow-up suggestions
  "[data-q]",
  "[jsname] [data-ved] a[data-ti]"
];
```

**Interception flow:**

1. Attach a `click` listener on `document` in the capture phase
2. On click, check if `event.target` (or closest ancestor) matches a chip selector
3. If matched:
   - `event.preventDefault()` + `event.stopImmediatePropagation()`
   - Extract the chip's query text from `innerText`, `data-followup-text`, `data-q`,
     or similar attribute
   - Call `scanClient.scanPrompt(chipText)`
   - If SAFE: set bypass flag, replay the click via `element.click()`
   - If SANITIZE/BLOCK: show review dialog
     - Cancel: do nothing (chip click dropped)
     - Send Original: set bypass flag, replay click
     - Send Sanitized: write sanitized text to the prompt input and trigger submit
       (if input is available); otherwise treat as "Send Original" since chip text
       can't be modified in-place

**Integration with observer.js:** The chip interceptor runs alongside the existing
observer. It's started in `content.js` after the observer, sharing the same
`scanClient` and `reviewDialog` instances.

### 3. NTP Navigation Interceptor (`background/ntp-interceptor.js` — NEW)

Since content scripts cannot inject into `chrome://newtab`, we use
`chrome.webNavigation.onCommitted` to detect when a search navigation from the NTP
lands on Google, then immediately redirect to an interstitial before the page renders.

**Why `onCommitted`?** In MV3, there is no blocking webNavigation API.
`onBeforeNavigate` fires early but can't cancel navigation. `onCommitted` fires after
the navigation is committed but before visual render — at this point
`chrome.tabs.update()` can redirect the tab before the user sees Google's page.

**Interface:**

```javascript
/**
 * Starts the NTP navigation interceptor in the background service worker.
 *
 * @param {{
 *   Logger: { info: Function, warn: Function },
 *   scanPrompt: (prompt: string, endpoint?: string) => Promise<object>
 * }} params
 */
export function startNtpInterceptor({ Logger, scanPrompt }) { ... }
```

**Detection logic for NTP-originated searches:**

```javascript
chrome.webNavigation.onCommitted.addListener(async (details) => {
  // Only main frame navigations
  if (details.frameId !== 0) return;

  // Determine if this came from the NTP
  // transitionType "typed" or "generated" with transitionQualifiers
  // including "from_address_bar" indicates NTP/omnibox origin
  const isFromNtp =
    details.transitionType === "typed" ||
    details.transitionType === "generated" ||
    (details.transitionQualifiers || []).includes("from_address_bar");

  if (!isFromNtp) return;

  // Verify destination is a Google Search URL
  const url = new URL(details.url);
  if (!isGoogleSearchUrl(url)) return;

  const query = url.searchParams.get("q");
  if (!query || !query.trim()) return;

  // Check bypass flag (user already approved this query via interstitial)
  const bypassKey = `bypass_${details.tabId}`;
  const bypassData = await chrome.storage.session.get(bypassKey);
  if (bypassData[bypassKey]) {
    await chrome.storage.session.remove(bypassKey);
    Logger.info("NTP bypass: query pre-approved, allowing through");
    return;
  }

  // Scan the query
  Logger.info(`NTP Search Intercepted: "${query}"`);
  const result = await scanPrompt(query);

  if (String(result.status).toUpperCase() === "SAFE") {
    Logger.info("NTP Search: SAFE, allowing navigation");
    return;
  }

  // Store scan results for the interstitial page
  await chrome.storage.session.set({
    [`scan_${details.tabId}`]: {
      originalUrl: details.url,
      query,
      result,
      timestamp: Date.now()
    }
  });

  // Redirect to interstitial
  Logger.info(`NTP Search: ${result.status}, redirecting to interstitial`);
  chrome.tabs.update(details.tabId, {
    url: chrome.runtime.getURL(
      `interstitial/review.html?tabId=${details.tabId}`
    )
  });
}, {
  url: [{ hostContains: "google", pathPrefix: "/search" }]
});
```

**Helper:**

```javascript
function isGoogleSearchUrl(url) {
  const hostname = url.hostname;
  return (
    (hostname === "www.google.com" || hostname === "google.com" ||
     hostname.endsWith(".google.com")) &&
    url.pathname.startsWith("/search")
  );
}
```

### 4. Interstitial Review Page (`interstitial/` — NEW)

A standalone extension page that displays scan results for navigation-intercepted
queries. Located at `browser-extension/interstitial/`.

**Files:**
- `interstitial/review.html` — page shell, loads review.js
- `interstitial/review.js` — reads scan data from storage, renders UI, handles actions
- `interstitial/review.css` — styles (reuses design language from modal.js)

**Data flow:**

1. Background worker stores scan results in `chrome.storage.session` keyed by tab ID:
   `scan_<tabId>` containing `{ originalUrl, query, result, timestamp }`
2. Interstitial page reads `tabId` from URL params, then fetches
   `chrome.storage.session.get("scan_<tabId>")`
3. Renders the review UI (same visual language as the in-page modal)
4. User action handlers:
   - **Cancel**: `chrome.tabs.update(tabId, { url: "chrome://newtab" })` or
     `window.close()`
   - **Send Original**: Set bypass flag
     `chrome.storage.session.set({ bypass_<tabId>: true })`, then
     `chrome.tabs.update(tabId, { url: originalUrl })`
   - **Send Sanitized**: Set bypass flag, then
     `chrome.tabs.update(tabId, { url: buildGoogleSearchUrl(sanitizedQuery) })`
5. Clean up: remove `scan_<tabId>` from session storage after rendering

**UI sections** (matching the in-page modal):
- Header: "PromptShield" eyebrow + "Review Search Before Sending" title
- Status badge (SANITIZE / BLOCK)
- Reason summary
- Detected issues list (entity type, value, confidence)
- ECI analysis section (if available)
- Original query (pre element)
- Sanitized query (pre element)
- Action buttons: Cancel (secondary), Send Original (danger, hidden on BLOCK),
  Send Sanitized (primary, hidden if no sanitized changes)

**Error states:**
- If scan data is missing/expired: show "Scan data not found" with a "Go Back" button
- If storage read fails: same error state

### 5. Gemini Nano Monitor (`background/gemini-monitor.js` — NEW)

Best-effort monitoring of Chrome's built-in AI features via webRequest observation.

**Interface:**

```javascript
/**
 * Starts monitoring outbound requests to Google's generative AI endpoints.
 *
 * @param {{
 *   Logger: { info: Function, warn: Function },
 *   scanPrompt: (prompt: string, endpoint?: string) => Promise<object>
 * }} params
 */
export function startGeminiMonitor({ Logger, scanPrompt }) { ... }
```

**Target URLs:**

```javascript
const GEMINI_API_URL_PATTERNS = [
  "*://generativelanguage.googleapis.com/*",
  "*://alkali-pa.googleapis.com/*",
  "*://content-push.googleapis.com/upload/*"
];
```

**Request body extraction:**

```javascript
function extractTextFromRequestBody(requestBody) {
  if (!requestBody?.raw?.length) return null;

  try {
    const decoder = new TextDecoder();
    const rawData = requestBody.raw
      .map((part) => decoder.decode(part.bytes))
      .join("");

    const parsed = JSON.parse(rawData);

    // Gemini API format: contents[].parts[].text
    if (parsed.contents && Array.isArray(parsed.contents)) {
      return parsed.contents
        .flatMap((c) => c.parts || [])
        .filter((p) => p.text)
        .map((p) => p.text)
        .join("\n");
    }

    // Alternative formats
    if (typeof parsed.prompt === "string") return parsed.prompt;
    if (typeof parsed.text === "string") return parsed.text;
    if (typeof parsed.input === "string") return parsed.input;

    return null;
  } catch {
    // Opaque/binary/encrypted payload - skip gracefully
    return null;
  }
}
```

**Notification on detection:**

```javascript
if (result.status !== "SAFE") {
  chrome.notifications.create(`gemini-warn-${Date.now()}`, {
    type: "basic",
    iconUrl: chrome.runtime.getURL("icons/icon128.png"),
    title: "PromptShield - Sensitive Data Detected",
    message: result.reason || "PII or enterprise data found in a Chrome AI request.",
    priority: 2
  });
}
```

**Note:** This is best-effort. Many Chrome AI features may use encrypted/binary
protocols that `extractTextFromRequestBody` cannot parse. The system fails gracefully
(returns `null`, skips scan) rather than erroring.

### 6. Anti-Double-Interception Coordination

To prevent a query from being scanned twice (once by NTP interceptor, once by content
script on the resulting Google page), we use a session storage coordination mechanism.

**Background -> Content Script flow:**

1. When the NTP interceptor allows a navigation (SAFE result, or user approved via
   interstitial), it sets: `chrome.storage.session.set({ bypass_tab_<tabId>: true })`
2. On the Google Search page, `content.js` checks for the bypass flag on init:
   ```javascript
   const tabId = await getOwnTabId(); // via chrome.runtime.sendMessage
   const bypassKey = `bypass_tab_${tabId}`;
   const data = await chrome.storage.session.get(bypassKey);
   if (data[bypassKey]) {
     await chrome.storage.session.remove(bypassKey);
     Logger.info("Bypass flag set: skipping first interception cycle");
     // Skip binding the first send attempt, or set observer.bypassOnce = true
   }
   ```

**Getting the tab ID in a content script:** Content scripts don't have direct access
to their tab ID. Add a message handler in the background worker:

```javascript
// In background.js
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "PROMPT_GUARDIAN_GET_TAB_ID") {
    sendResponse({ tabId: sender.tab?.id ?? null });
    return false;
  }
  // ... existing handlers
});
```

**Cleanup:** Bypass flags include a timestamp and are auto-cleaned by the background
worker after 30 seconds to prevent stale state from accumulating.

### 7. Manifest Changes

Additions to the existing `manifest.json` (merged with current entries):

```json
{
  "permissions": ["webNavigation", "webRequest", "notifications"],
  "host_permissions": [
    "https://www.google.com/*",
    "https://google.com/*",
    "*://generativelanguage.googleapis.com/*",
    "*://alkali-pa.googleapis.com/*",
    "*://content-push.googleapis.com/*"
  ],
  "content_scripts": [
    {
      "matches": [
        "https://www.google.com/*",
        "https://google.com/*"
      ]
    }
  ],
  "web_accessible_resources": [
    {
      "resources": ["interstitial/*"],
      "matches": ["<all_urls>"]
    }
  ]
}
```

These are additions — `content_scripts[0].matches` and `host_permissions` arrays get
the Google entries appended; the `web_accessible_resources` array gets a new entry for
the interstitial; `permissions` gets the three new API permissions.

### 8. Content Script Bootstrap Changes (`content/content.js`)

The bootstrapper needs two additions:

1. Import and start the chip interceptor alongside the observer
2. Check for the anti-double-interception bypass flag on init

```javascript
// After observer.start():
if (site.id === "google-search-ai" || site.id === "google-ai-mode") {
  const { createChipInterceptor } = await import(
    chrome.runtime.getURL("content/chip-interceptor.js")
  );
  const chipInterceptor = createChipInterceptor({
    Logger,
    scanClient,
    reviewDialog,
    chipSelectors: GOOGLE_CHIP_SELECTORS,
    documentRef: document,
    windowRef: window
  });
  chipInterceptor.start();
}
```

## Error Handling

| Condition | Behavior |
|---|---|
| Scan API unavailable | Allow query/navigation to proceed (fail-open, matching existing behavior) |
| DOM selectors don't match (Google UI update) | Content script stays inert, logs `[Prompt Guardian] No prompt area found` |
| webRequest body is opaque/encrypted | Skip scan gracefully, log for debugging |
| NTP interception race (page loads before redirect) | Content script handles it as fallback (normal in-page interception) |
| Interstitial storage data missing/expired | Show error state with "Go Back" button |
| Notification permission not granted | Log warning, skip notification silently |
| Google homepage definition accidentally matches /maps, /mail | `pathExclusions` prevents activation on non-search pages |

## Testing Strategy

- **Site definitions**: Unit tests verifying URL matching:
  - `google.com/search?q=test` -> google-search-ai
  - `google.com/search?q=test&udm=50` -> google-search-ai
  - `google.com/` -> google-homepage
  - `google.com/webhp` -> google-homepage
  - `google.com/search?q=test` does NOT match google-homepage
  - `google.com/maps` does NOT match either Google definition
  - Existing sites (chatgpt.com, gemini.google.com, etc.) remain unaffected
- **Chip interceptor**: Manual test on live Google AI Mode — click a suggestion chip
  containing or simulating PII text, verify interception fires
- **NTP interceptor**: Manual test — new tab -> type PII in address bar -> verify
  redirect to interstitial before Google page renders
- **Interstitial page**: Load directly with mock data in session storage -> verify UI
  renders, all three action buttons work correctly
- **Gemini monitor**: Observe DevTools network tab for Chrome AI feature requests,
  verify the monitor logs scan activity
- **Anti-double-interception**: New tab -> type PII -> approve in interstitial ->
  verify content script does NOT re-intercept on the Google Search page
- **Regression**: Existing sites (ChatGPT, Gemini, Claude, DeepSeek, Copilot) still
  function identically after these changes
