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

// Empty-state copy for the Detected Issues panel.
//
// The panel is fed from Presidio entity spans, so a decision driven purely by
// enterprise-context analysis has nothing to list - entityCount is 0 while the
// ECI flags and the policy reason carry the whole explanation. The old single
// string ("no details were returned") was wrong in that case: details *were*
// returned, just not as detected spans, and they are already on screen in the
// AI Context Analysis section directly below. Saying nothing came back
// contradicts that section and reads as a scanner malfunction on a decision
// that is entirely correct.
//
// Kept character-identical to ISSUES_EMPTY_STATE in content/modal.js - both
// surfaces render the same decision and must word it the same way.
// review.test.mjs asserts they match.
const ISSUES_EMPTY_STATE = {
  context:
    "No individual values were flagged in the text itself. This decision was driven by the enterprise-context analysis below.",
  unavailable:
    "No individual values were flagged in the text itself, and the context classifier could not complete its analysis, so this was held for review out of caution.",
  none: "No specific issue details were returned by the scanner."
};

/**
 * Classifies what, if anything, the ECI section is able to explain. Single
 * source of truth for the fallback test, so the issues panel and the ECI
 * section can never disagree about whether the classifier actually ran.
 *
 *  - "unavailable": the classifier fell back (unreachable provider, or output
 *    that failed validation). Its all-false flags and 0% confidence are
 *    defaults, not an assessment, so they must not be read as findings.
 *  - "context": the classifier ran and returned something that explains the
 *    decision - a raised flag, or reasoning describing what it saw.
 *  - "none": no ECI at all, or an assessment that raised nothing.
 *
 * @param {object | undefined} eci
 * @returns {"context" | "unavailable" | "none"}
 */
function describeEciExplanation(eci) {
  if (!eci) {
    return "none";
  }

  const isFallback =
    eci.confidence === 0 &&
    Array.isArray(eci.reasoning) &&
    eci.reasoning.some((entry) => /fallback/i.test(String(entry)));

  if (isFallback) {
    return "unavailable";
  }

  const hasFlags = ECI_FLAGS.some(([key]) => eci[key]);
  const hasReasoning = Array.isArray(eci.reasoning) && eci.reasoning.length > 0;

  return hasFlags || hasReasoning ? "context" : "none";
}

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
 *
 * No ECI-derived entries are synthesised here. An issue is
 * {entityType, value, score} - a concrete span of text that was detected -
 * and an ECI flag has neither a span nor a value, so fitting one into that
 * shape means inventing a value. The ECI signal is rendered as itself, by
 * renderEci().
 *
 * @param {Array<{entityType: string, value: string, score?: number}>} issues
 * @param {"context" | "unavailable" | "none"} eciExplanation
 * @returns {string}
 */
function renderIssues(issues, eciExplanation = "none") {
  if (!issues || issues.length === 0) {
    const copy = ISSUES_EMPTY_STATE[eciExplanation] ?? ISSUES_EMPTY_STATE.none;
    return `<p class="empty-state">${copy}</p>`;
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

  if (describeEciExplanation(eci) === "unavailable") {
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

  // What the ECI section can explain decides how the issues panel words its
  // empty state, so the two are computed from one value rather than each
  // guessing at the scan result independently.
  const eciExplanation = describeEciExplanation(eci);

  // Render issues
  const issuesEl = document.getElementById("review-issues");
  if (issuesEl) {
    issuesEl.innerHTML = renderIssues(issues, eciExplanation);
  }

  // Render ECI section
  const eciSection = document.getElementById("eci-section");
  const eciEl = document.getElementById("review-eci");
  if (eciSection && eciEl) {
    if (eci) {
      eciSection.hidden = false;
      eciEl.innerHTML = renderEci(eci);
      // When there are no detected spans, this section is not supporting
      // detail - it is the whole reason for the decision, so it is styled as
      // the primary explanation instead of sitting below an apology.
      if (issues.length === 0 && eciExplanation !== "none") {
        eciSection.setAttribute("data-primary", "true");
      } else {
        eciSection.removeAttribute("data-primary");
      }
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

  // Configure action availability.
  //
  // A BLOCK decision must not be sendable by ANY route. "Send Sanitized" used
  // to be gated only on whether sanitization changed anything, so a BLOCKed
  // query whose only masked span was incidental (a single entity hit that had
  // nothing to do with the reason for the block) could still be transmitted in
  // full with one substring replaced. Both send actions are now gated on the
  // decision itself.
  const isBlocked = status === "BLOCK";
  const canSendOriginal = !isBlocked;
  const canSendSanitized = !isBlocked && hasSanitizedChanges;

  const btnSendOriginal = document.getElementById("btn-send-original");
  const btnSendSanitized = document.getElementById("btn-send-sanitized");

  // Cancel is always wired - the user must always have a way out of this page.
  const btnCancel = document.getElementById("btn-cancel");
  if (btnCancel) {
    btnCancel.addEventListener("click", () => {
      handleCancel(tabId);
    });
  }

  // Defense in depth: a disallowed action is removed from the document AND its
  // click handler is never attached, so there is no hidden-but-focusable
  // element and no listener left to reach.
  if (canSendOriginal) {
    if (btnSendOriginal) {
      btnSendOriginal.addEventListener("click", () => {
        handleSendOriginal(tabId, originalUrl);
      });
    }
  } else {
    disableAction(btnSendOriginal);
  }

  if (canSendSanitized) {
    if (btnSendSanitized) {
      btnSendSanitized.addEventListener("click", () => {
        handleSendSanitized(tabId, sanitizedQuery);
      });
    }
  } else {
    disableAction(btnSendSanitized);
  }

  // Clean up scan data from session storage after rendering
  try {
    await chrome.storage.session.remove(storageKey);
  } catch (err) {
    console.warn("[PromptShield] Failed to clean up scan data:", err);
  }
}

/**
 * Takes an action button out of play: hidden, disabled, and detached from the
 * document. Called for actions that must not be available for the current
 * decision. No click handler is attached to these buttons either, so there is
 * nothing left to invoke.
 * @param {HTMLElement | null} button
 */
function disableAction(button) {
  if (!button) return;
  button.hidden = true;
  if ("disabled" in button) {
    button.disabled = true;
  }
  button.remove();
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
