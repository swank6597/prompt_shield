/**
 * Interstitial Review Page
 *
 * Reads scan data from chrome.storage.session, renders the review UI,
 * and wires up action buttons (Cancel, Send Original, Send Sanitized).
 */

// ECI boolean flags and their display labels
const ECI_FLAGS = [
  ["requiresEnterpriseKnowledge", "Requires Enterprise Knowledge"],
  ["containsInternalArchitecture", "Internal Architecture"],
  ["containsImplementationDetails", "Implementation Details"],
  ["containsSourceCode", "Source Code"],
  ["containsCustomerData", "Customer Data"],
  ["containsSecrets", "Possible Secrets"]
];

/**
 * Escapes HTML to prevent XSS in rendered content.
 * @param {string} str
 * @returns {string}
 */
function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

/**
 * Parses the tabId from the current page's URL search params.
 * @returns {number | null}
 */
function getTabIdFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const raw = params.get("tabId");
  if (!raw) return null;
  const parsed = parseInt(raw, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

/**
 * Builds a Google Search URL from a query string.
 * @param {string} query
 * @returns {string}
 */
function buildGoogleSearchUrl(query) {
  const url = new URL("https://www.google.com/search");
  url.searchParams.set("q", query);
  return url.toString();
}

/**
 * Shows the error state and hides the review card.
 */
function showErrorState() {
  const reviewCard = document.getElementById("review-card");
  const errorCard = document.getElementById("error-card");
  if (reviewCard) reviewCard.hidden = true;
  if (errorCard) errorCard.hidden = false;
}

/**
 * Renders the detected issues list.
 * @param {Array<{entityType: string, value: string, score?: number}>} issues
 * @returns {string}
 */
function renderIssues(issues) {
  if (!issues || issues.length === 0) {
    return `<p class="empty-state">No specific issue details were returned by the scanner.</p>`;
  }

  return `
    <ul class="issue-list">
      ${issues
        .map(
          (issue) => `
            <li class="issue-item">
              <div class="issue-type">${escapeHtml(issue.entityType || "UNKNOWN")}</div>
              <div class="issue-value">${escapeHtml(issue.value || "(hidden)")}</div>
              ${
                typeof issue.score === "number"
                  ? `<div class="issue-score">Confidence: ${Math.round(issue.score * 100)}%</div>`
                  : ""
              }
            </li>
          `
        )
        .join("")}
    </ul>
  `;
}

/**
 * Renders the ECI (Enterprise Context Intelligence) section.
 * @param {object | undefined} eci
 * @returns {string}
 */
function renderEci(eci) {
  if (!eci) return "";

  // Detect fallback state
  const isFallback =
    eci.confidence === 0 &&
    Array.isArray(eci.reasoning) &&
    eci.reasoning.some((entry) => /fallback/i.test(String(entry)));

  if (isFallback) {
    return `<p class="empty-state">AI context analysis unavailable (${escapeHtml(
      eci.reasoning?.[0] ?? "classifier fallback"
    )}).</p>`;
  }

  const activeFlags = ECI_FLAGS.filter(([key]) => eci[key]).map(([, label]) => label);
  const flagsMarkup = activeFlags.length
    ? `<div class="eci-flags">${activeFlags
        .map((label) => `<span class="eci-flag">${escapeHtml(label)}</span>`)
        .join("")}</div>`
    : `<p class="empty-state">No enterprise-context risk flags raised.</p>`;

  const reasoningMarkup =
    Array.isArray(eci.reasoning) && eci.reasoning.length
      ? `<ul class="eci-reasoning">${eci.reasoning
          .map((entry) => `<li>${escapeHtml(entry)}</li>`)
          .join("")}</ul>`
      : "";

  const confidencePct = Math.round((eci.confidence ?? 0) * 100);

  return `
    <div class="eci-summary">
      <span class="eci-pill">${escapeHtml(eci.intent || "Unknown intent")}</span>
      <span class="eci-pill">${escapeHtml(eci.documentType || "None")}</span>
      <span class="eci-confidence">AI confidence: ${confidencePct}%</span>
    </div>
    ${flagsMarkup}
    ${reasoningMarkup}
  `;
}

/**
 * Normalizes raw issue objects from the scan result.
 * @param {unknown} issues
 * @returns {Array<{entityType: string, value: string, score?: number}>}
 */
function normalizeIssues(issues) {
  if (!Array.isArray(issues)) return [];

  return issues
    .map((issue) => {
      if (!issue || typeof issue !== "object") return null;
      const entityType = String(issue.entityType ?? issue.entity_type ?? "UNKNOWN").trim();
      const value = String(issue.value ?? "").trim();
      if (!entityType || entityType === "UNKNOWN") return null;
      return {
        entityType,
        value: value || "(detected in prompt)",
        score: typeof issue.score === "number" ? issue.score : undefined
      };
    })
    .filter(Boolean);
}

/**
 * Main initialization — reads scan data, renders the UI, wires actions.
 */
async function init() {
  const tabId = getTabIdFromUrl();

  if (!tabId) {
    showErrorState();
    wireGoBackButton();
    return;
  }

  const storageKey = `scan_${tabId}`;

  let scanData;
  try {
    const result = await chrome.storage.session.get(storageKey);
    scanData = result[storageKey];
  } catch (err) {
    console.error("[PromptShield] Failed to read scan data from session storage:", err);
    showErrorState();
    wireGoBackButton();
    return;
  }

  if (!scanData) {
    showErrorState();
    wireGoBackButton();
    return;
  }

  const { originalUrl, query, result: scanResult } = scanData;

  if (!scanResult) {
    showErrorState();
    wireGoBackButton();
    return;
  }

  // Extract fields from the scan result
  const status = String(scanResult.status ?? "SANITIZE").toUpperCase();
  const reason = scanResult.reason || "";
  const originalQuery = query || scanResult.originalPrompt || "";
  const sanitizedQuery = scanResult.sanitizedPrompt || scanResult.sanitized_prompt || "";
  const issues = normalizeIssues(scanResult.issues);
  const eci = scanResult.eci || undefined;
  const hasSanitizedChanges =
    sanitizedQuery.trim() !== "" && sanitizedQuery.trim() !== originalQuery.trim();

  // Render status badge
  const statusEl = document.getElementById("review-status");
  if (statusEl) {
    const badgeClass = status === "BLOCK" ? "status-block" : "status-sanitize";
    statusEl.innerHTML = `<span class="status-badge ${badgeClass}">${escapeHtml(status)}</span>`;
  }

  // Render summary
  const summaryEl = document.getElementById("review-summary");
  if (summaryEl) {
    summaryEl.textContent =
      reason ||
      (status === "BLOCK"
        ? "This search contains sensitive data and should not be sent as-is."
        : "Review the detected issues below and choose how to proceed.");
  }

  // Render issues
  const issuesEl = document.getElementById("review-issues");
  if (issuesEl) {
    issuesEl.innerHTML = renderIssues(issues);
  }

  // Render ECI section
  const eciSection = document.getElementById("eci-section");
  const eciEl = document.getElementById("review-eci");
  if (eciSection && eciEl) {
    if (eci) {
      eciSection.hidden = false;
      eciEl.innerHTML = renderEci(eci);
    } else {
      eciSection.hidden = true;
    }
  }

  // Render original query
  const originalEl = document.getElementById("review-original");
  if (originalEl) {
    originalEl.textContent = originalQuery || "(empty)";
  }

  // Render sanitized query
  const sanitizedEl = document.getElementById("review-sanitized");
  if (sanitizedEl) {
    sanitizedEl.textContent = hasSanitizedChanges
      ? sanitizedQuery
      : "No sanitized version was produced.";
  }

  // Configure action buttons visibility
  const btnSendOriginal = document.getElementById("btn-send-original");
  const btnSendSanitized = document.getElementById("btn-send-sanitized");

  if (btnSendOriginal) {
    // Hide "Send Original" on BLOCK status
    btnSendOriginal.hidden = status === "BLOCK";
  }

  if (btnSendSanitized) {
    // Hide "Send Sanitized" if there are no sanitized changes
    btnSendSanitized.hidden = !hasSanitizedChanges;
  }

  // Wire action buttons
  const btnCancel = document.getElementById("btn-cancel");
  if (btnCancel) {
    btnCancel.addEventListener("click", () => {
      handleCancel(tabId);
    });
  }

  if (btnSendOriginal) {
    btnSendOriginal.addEventListener("click", () => {
      handleSendOriginal(tabId, originalUrl);
    });
  }

  if (btnSendSanitized) {
    btnSendSanitized.addEventListener("click", () => {
      handleSendSanitized(tabId, sanitizedQuery);
    });
  }

  // Clean up scan data from session storage after rendering
  try {
    await chrome.storage.session.remove(storageKey);
  } catch (err) {
    console.warn("[PromptShield] Failed to clean up scan data:", err);
  }
}

/**
 * Handles the Cancel action — navigate to new tab page or close tab.
 * @param {number} tabId
 */
async function handleCancel(tabId) {
  try {
    await chrome.tabs.update(tabId, { url: "chrome://newtab" });
  } catch {
    // Fallback: close the current tab or navigate away
    window.close();
  }
}

/**
 * Handles the Send Original action — sets bypass flag and navigates to original URL.
 * @param {number} tabId
 * @param {string} originalUrl
 */
async function handleSendOriginal(tabId, originalUrl) {
  if (!originalUrl) {
    console.error("[PromptShield] No original URL available");
    return;
  }

  try {
    // Set bypass flag so the background worker allows this navigation through
    await chrome.storage.session.set({ [`bypass_${tabId}`]: true });
    // Set content-script bypass flag so the content script on the Google Search
    // page does not re-intercept this already-reviewed query
    await chrome.storage.session.set({ [`bypass_tab_${tabId}`]: { timestamp: Date.now() } });
    await chrome.tabs.update(tabId, { url: originalUrl });
  } catch (err) {
    console.error("[PromptShield] Failed to send original:", err);
  }
}

/**
 * Handles the Send Sanitized action — sets bypass flag and navigates to sanitized search.
 * @param {number} tabId
 * @param {string} sanitizedQuery
 */
async function handleSendSanitized(tabId, sanitizedQuery) {
  if (!sanitizedQuery) {
    console.error("[PromptShield] No sanitized query available");
    return;
  }

  try {
    // Set bypass flag so the background worker allows this navigation through
    await chrome.storage.session.set({ [`bypass_${tabId}`]: true });
    // Set content-script bypass flag so the content script on the Google Search
    // page does not re-intercept this already-reviewed query
    await chrome.storage.session.set({ [`bypass_tab_${tabId}`]: { timestamp: Date.now() } });
    const sanitizedUrl = buildGoogleSearchUrl(sanitizedQuery);
    await chrome.tabs.update(tabId, { url: sanitizedUrl });
  } catch (err) {
    console.error("[PromptShield] Failed to send sanitized:", err);
  }
}

/**
 * Wires the "Go Back" button in the error state.
 */
function wireGoBackButton() {
  const btnGoBack = document.getElementById("btn-go-back");
  if (btnGoBack) {
    btnGoBack.addEventListener("click", () => {
      // Try navigating back, or close the tab
      if (window.history.length > 1) {
        window.history.back();
      } else {
        window.close();
      }
    });
  }
}

// Initialize when DOM is ready
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
