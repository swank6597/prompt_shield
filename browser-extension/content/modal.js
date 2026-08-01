const MODAL_HOST_ID = "promptshield-review-host";

import { resolveScanIssues } from "../utils/scan-utils.js";

/**
 * @typedef {{
 *   entityType: string,
 *   value: string,
 *   score?: number
 * }} ScanIssue
 */

/**
 * @typedef {{
 *   intent?: string,
 *   documentType?: string,
 *   requiresEnterpriseKnowledge?: boolean,
 *   containsInternalArchitecture?: boolean,
 *   containsImplementationDetails?: boolean,
 *   containsSourceCode?: boolean,
 *   containsCustomerData?: boolean,
 *   containsSecrets?: boolean,
 *   confidence?: number,
 *   reasoning?: string[]
 * }} EciResult
 */

/**
 * @typedef {{
 *   status?: string,
 *   reason?: string,
 *   originalPrompt?: string,
 *   sanitizedPrompt?: string,
 *   issues?: ScanIssue[],
 *   eci?: EciResult,
 *   allowOverride?: boolean
 * }} ReviewDialogPayload
 */

// Maps ECI boolean flags to their display label. Only flags that are true
// are shown - a wall of "false" badges would bury the ones that matter.
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
// Kept character-identical to ISSUES_EMPTY_STATE in
// interstitial/review.js - both surfaces render the same decision and must
// word it the same way. interstitial/review.test.mjs asserts they match.
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
 * @param {EciResult | undefined} eci
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
 * Creates the in-page review dialog shown after a prompt scan.
 *
 * @param {{
 *   onCancel: () => void,
 *   onSendSanitized: () => void,
 *   onSendOriginal: () => void
 * }} handlers
 * @returns {{ show: (payload: ReviewDialogPayload) => void, hide: () => void }}
 */
export function createReviewDialog(handlers) {
  let host = null;
  let shadow = null;

  // Persistent references to the action row and its buttons. Held here rather
  // than looked up per show() because show() detaches the send buttons that
  // aren't permitted for the current decision - once detached they are no
  // longer findable via shadow.getElementById().
  let actionsNode = null;
  let sendOriginalButton = null;
  let sendSanitizedButton = null;

  // Which send actions the currently-displayed decision permits. This is the
  // authority the click handlers check; button visibility alone is not enough
  // to enforce it. The dialog host uses an open shadow root, so page scripts
  // can reach the button nodes (and can hold a reference to a node from an
  // earlier, permissive dialog), and a detached node still fires its listeners.
  const actionState = {
    canSendOriginal: false,
    canSendSanitized: false
  };

  /**
   * Escapes HTML for safe rendering.
   *
   * @param {string} value
   * @returns {string}
   */
  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  /**
   * Builds the issues list markup.
   *
   * No ECI-derived entries are synthesised here. A ScanIssue is
   * {entityType, value, score} - a concrete span of text that was detected -
   * and an ECI flag has neither a span nor a value, so fitting one into that
   * shape means inventing a value and passing it through
   * resolveScanIssues()/normalizeIssueList(), which exist to normalise
   * *detected text*. The ECI signal is rendered as itself, by renderEci().
   *
   * @param {ScanIssue[]} issues
   * @param {"context" | "unavailable" | "none"} eciExplanation
   * @returns {string}
   */
  function renderIssues(issues, eciExplanation = "none") {
    if (!issues.length) {
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
   * Builds the AI (ECI) context-analysis markup, or "" when there's
   * nothing to show. Renders a distinct "fallback" notice when the
   * classifier couldn't run (Ollama unreachable / output failed
   * validation) rather than presenting a fallback's default field values
   * (all-false flags, 0% confidence) as if they were a real assessment.
   *
   * @param {EciResult | undefined} eci
   * @returns {string}
   */
  function renderEci(eci) {
    if (!eci) {
      return "";
    }

    if (describeEciExplanation(eci) === "unavailable") {
      // Defense in depth: the backend already caps fallback reasoning text
      // (see semantic_classifier.py's _truncate_reason()), but this popup
      // shouldn't depend on every backend caller getting that right - cap
      // here too so a long message (e.g. a raw exception string) never
      // balloons this small notice into a wall of text.
      const rawReason = eci.reasoning?.[0] ?? "classifier fallback";
      const reason =
        rawReason.length > 200 ? `${rawReason.slice(0, 200).trimEnd()}...` : rawReason;
      return `<p class="empty-state">AI context analysis unavailable (${escapeHtml(reason)}).</p>`;
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
   * Ensures the dialog host exists.
   */
  function ensureHost() {
    if (host && shadow) {
      return;
    }

    host = document.createElement("div");
    host.id = MODAL_HOST_ID;
    host.style.all = "initial";
    host.style.position = "fixed";
    host.style.inset = "0";
    host.style.zIndex = "2147483647";
    host.style.display = "none";

    shadow = host.attachShadow({ mode: "open" });
    shadow.innerHTML = `
      <style>
        :host { all: initial; }
        .overlay {
          position: fixed;
          inset: 0;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(15, 23, 42, 0.72);
          backdrop-filter: blur(8px);
          font-family: "Segoe UI", Arial, sans-serif;
          padding: 16px;
        }
        .card {
          width: min(720px, calc(100vw - 32px));
          max-height: calc(100vh - 32px);
          overflow: auto;
          border-radius: 20px;
          background: linear-gradient(180deg, #0f172a 0%, #111827 100%);
          color: #e2e8f0;
          border: 1px solid rgba(148, 163, 184, 0.2);
          box-shadow: 0 24px 60px rgba(0, 0, 0, 0.35);
          padding: 22px;
        }
        .eyebrow {
          margin: 0 0 8px;
          font-size: 12px;
          letter-spacing: 0.18em;
          text-transform: uppercase;
          color: #38bdf8;
        }
        h2 {
          margin: 0;
          font-size: 22px;
          line-height: 1.2;
        }
        .summary {
          margin: 12px 0 0;
          color: #cbd5e1;
          line-height: 1.5;
        }
        .status-badge {
          display: inline-block;
          margin-top: 12px;
          padding: 6px 10px;
          border-radius: 999px;
          font-size: 12px;
          font-weight: 700;
          letter-spacing: 0.04em;
          text-transform: uppercase;
        }
        .status-safe {
          background: rgba(34, 197, 94, 0.16);
          color: #86efac;
        }
        .status-sanitize {
          background: rgba(251, 191, 36, 0.16);
          color: #fcd34d;
        }
        .status-block {
          background: rgba(248, 113, 113, 0.16);
          color: #fca5a5;
        }
        .section {
          margin-top: 18px;
        }
        .section-title {
          margin: 0 0 8px;
          font-size: 13px;
          font-weight: 700;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          color: #94a3b8;
        }
        /* Set when there are no detected spans, so this section carries the
           whole explanation for the decision rather than supporting it. */
        .section[data-primary="true"] {
          padding: 14px;
          border-radius: 14px;
          background: rgba(167, 139, 250, 0.08);
          border-left: 3px solid rgba(167, 139, 250, 0.55);
        }
        .section[data-primary="true"] .section-title {
          color: #c4b5fd;
        }
        .prompt-box {
          margin: 0;
          padding: 12px 14px;
          border-radius: 12px;
          background: rgba(15, 23, 42, 0.72);
          border: 1px solid rgba(148, 163, 184, 0.18);
          color: #e2e8f0;
          white-space: pre-wrap;
          word-break: break-word;
          line-height: 1.5;
          font-size: 14px;
        }
        .issue-list {
          list-style: none;
          margin: 0;
          padding: 0;
          display: grid;
          gap: 10px;
        }
        .issue-item {
          padding: 12px 14px;
          border-radius: 12px;
          background: rgba(248, 113, 113, 0.08);
          border: 1px solid rgba(248, 113, 113, 0.18);
        }
        .issue-type {
          font-size: 12px;
          font-weight: 700;
          letter-spacing: 0.06em;
          text-transform: uppercase;
          color: #fca5a5;
        }
        .issue-value {
          margin-top: 6px;
          color: #f8fafc;
          word-break: break-word;
        }
        .issue-score {
          margin-top: 6px;
          font-size: 12px;
          color: #94a3b8;
        }
        .empty-state {
          margin: 0;
          color: #94a3b8;
        }
        .eci-summary {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 8px;
          margin-bottom: 10px;
        }
        .eci-pill {
          padding: 4px 10px;
          border-radius: 999px;
          background: rgba(167, 139, 250, 0.16);
          color: #c4b5fd;
          font-size: 12px;
          font-weight: 600;
        }
        .eci-confidence {
          font-size: 12px;
          color: #94a3b8;
        }
        .eci-flags {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          margin-bottom: 10px;
        }
        .eci-flag {
          padding: 6px 10px;
          border-radius: 10px;
          background: rgba(167, 139, 250, 0.1);
          border: 1px solid rgba(167, 139, 250, 0.28);
          color: #ddd6fe;
          font-size: 12px;
          font-weight: 600;
        }
        .eci-reasoning {
          margin: 0;
          padding-left: 18px;
          color: #cbd5e1;
          font-size: 13px;
          line-height: 1.6;
        }
        .actions {
          margin-top: 22px;
          display: flex;
          flex-wrap: wrap;
          gap: 12px;
          justify-content: flex-end;
        }
        button {
          border: 0;
          border-radius: 12px;
          padding: 10px 16px;
          font: inherit;
          cursor: pointer;
        }
        .secondary {
          background: rgba(148, 163, 184, 0.14);
          color: #e2e8f0;
        }
        .primary {
          background: #38bdf8;
          color: #0f172a;
          font-weight: 700;
        }
        .danger {
          background: rgba(248, 113, 113, 0.18);
          color: #fecaca;
          border: 1px solid rgba(248, 113, 113, 0.28);
        }
      </style>
      <div class="overlay" role="dialog" aria-modal="true" aria-labelledby="pg-review-title">
        <div class="card">
          <p class="eyebrow">PromptShield</p>
          <h2 id="pg-review-title">Review Prompt Before Sending</h2>
          <p class="summary" id="pg-review-summary"></p>
          <div id="pg-review-status"></div>

          <div class="section">
            <p class="section-title">Detected Issues</p>
            <div id="pg-review-issues"></div>
          </div>

          <div class="section" id="pg-review-eci-section">
            <p class="section-title">AI Context Analysis</p>
            <div id="pg-review-eci"></div>
          </div>

          <div class="section">
            <p class="section-title">Your Prompt</p>
            <pre class="prompt-box" id="pg-review-original"></pre>
          </div>

          <div class="section">
            <p class="section-title">Sanitized Prompt</p>
            <pre class="prompt-box" id="pg-review-sanitized"></pre>
          </div>

          <div class="actions" id="pg-review-actions">
            <button type="button" class="secondary" id="pg-review-cancel">Cancel</button>
            <button type="button" class="danger" id="pg-review-send-original">Send Original</button>
            <button type="button" class="primary" id="pg-review-send-sanitized">Send Sanitized</button>
          </div>
        </div>
      </div>
    `;

    actionsNode = shadow.getElementById("pg-review-actions");
    sendOriginalButton = shadow.getElementById("pg-review-send-original");
    sendSanitizedButton = shadow.getElementById("pg-review-send-sanitized");

    // Cancel is unconditional - the user always has a way out of the dialog.
    shadow.getElementById("pg-review-cancel")?.addEventListener("click", () => {
      hide();
      handlers.onCancel();
    });

    sendSanitizedButton?.addEventListener("click", () => {
      if (!actionState.canSendSanitized) {
        return;
      }
      hide();
      handlers.onSendSanitized();
    });

    sendOriginalButton?.addEventListener("click", () => {
      if (!actionState.canSendOriginal) {
        return;
      }
      hide();
      handlers.onSendOriginal();
    });

    (document.body || document.documentElement).appendChild(host);
  }

  /**
   * Displays the review dialog.
   *
   * @param {ReviewDialogPayload} payload
   */
  function show(payload) {
    ensureHost();

    const status = String(payload.status ?? "SANITIZE").toUpperCase();
    const originalPrompt = payload.originalPrompt ?? "";
    const sanitizedPrompt = payload.sanitizedPrompt ?? originalPrompt;
    const issues = resolveScanIssues({
      issues: payload.issues,
      reason: payload.reason,
      originalPrompt,
      sanitizedPrompt
    });
    const hasSanitizedChanges = sanitizedPrompt.trim() !== originalPrompt.trim();

    const titleNode = shadow?.getElementById("pg-review-title");
    const summaryNode = shadow?.getElementById("pg-review-summary");
    const statusNode = shadow?.getElementById("pg-review-status");
    const issuesNode = shadow?.getElementById("pg-review-issues");
    const eciSectionNode = shadow?.getElementById("pg-review-eci-section");
    const eciNode = shadow?.getElementById("pg-review-eci");
    const originalNode = shadow?.getElementById("pg-review-original");
    const sanitizedNode = shadow?.getElementById("pg-review-sanitized");

    if (titleNode) {
      titleNode.textContent =
        status === "BLOCK" ? "Prompt Should Be Blocked" : "Sensitive Data Detected";
    }

    if (summaryNode) {
      summaryNode.textContent =
        payload.reason ||
        (status === "BLOCK"
          ? "This prompt contains sensitive data and should not be sent as-is."
          : "Review the detected issues below and choose whether to send the sanitized or original prompt.");
    }

    if (statusNode) {
      const badgeClass =
        status === "BLOCK" ? "status-block" : status === "SAFE" ? "status-safe" : "status-sanitize";
      statusNode.innerHTML = `<span class="status-badge ${badgeClass}">${escapeHtml(status)}</span>`;
    }

    // What the ECI section can explain decides how the issues panel words its
    // empty state, so the two are computed from one value rather than each
    // guessing at the payload independently.
    const eciExplanation = describeEciExplanation(payload.eci);

    if (issuesNode) {
      issuesNode.innerHTML = renderIssues(issues, eciExplanation);
    }

    if (eciSectionNode) {
      eciSectionNode.hidden = !payload.eci;
      // When there are no detected spans, the ECI section is not supporting
      // detail - it is the whole reason for the decision, so it is styled as
      // the primary explanation instead of sitting below an apology.
      if (issues.length === 0 && eciExplanation !== "none") {
        eciSectionNode.setAttribute("data-primary", "true");
      } else {
        eciSectionNode.removeAttribute("data-primary");
      }
    }

    if (eciNode) {
      eciNode.innerHTML = renderEci(payload.eci);
    }

    if (originalNode) {
      originalNode.textContent = originalPrompt || "(empty)";
    }

    if (sanitizedNode) {
      sanitizedNode.textContent = hasSanitizedChanges
        ? sanitizedPrompt
        : "No sanitized version was produced. You can cancel or send the original prompt.";
    }

    // A policy BLOCK must not be sendable by ANY route. "Send Sanitized" used
    // to be gated only on hasSanitizedChanges, so a BLOCKed prompt whose only
    // masked span was incidental (an entity hit unrelated to the reason for the
    // block) could still be transmitted in full with one substring replaced.
    //
    // Callers that reuse the BLOCK styling for something that is not a policy
    // BLOCK opt out explicitly with allowOverride: true - see observer.js's
    // composer-write fallback, which needs to leave the user a way to send.
    const policyBlocked = status === "BLOCK" && payload.allowOverride !== true;
    actionState.canSendOriginal =
      !policyBlocked && (payload.allowOverride ?? status !== "BLOCK");
    actionState.canSendSanitized = !policyBlocked && hasSanitizedChanges;

    // Detach both send actions, then re-attach only the permitted ones. Doing
    // it in this order keeps the row in its canonical order (Cancel, Send
    // Original, Send Sanitized) and means a disallowed action is absent from
    // the tree rather than merely hidden inside it.
    sendOriginalButton?.remove();
    sendSanitizedButton?.remove();

    if (sendOriginalButton) {
      sendOriginalButton.hidden = !actionState.canSendOriginal;
      sendOriginalButton.disabled = !actionState.canSendOriginal;
      sendOriginalButton.textContent = "Send Original";
      if (actionState.canSendOriginal) {
        actionsNode?.appendChild(sendOriginalButton);
      }
    }

    if (sendSanitizedButton) {
      sendSanitizedButton.hidden = !actionState.canSendSanitized;
      sendSanitizedButton.disabled = !actionState.canSendSanitized;
      if (actionState.canSendSanitized) {
        actionsNode?.appendChild(sendSanitizedButton);
      }
    }

    if (host) {
      host.style.display = "block";
    }
  }

  /**
   * Hides the review dialog.
   */
  function hide() {
    // Revoke both send actions on the way out so a node reference captured
    // while the dialog was open cannot be clicked after it closes.
    actionState.canSendOriginal = false;
    actionState.canSendSanitized = false;

    if (host) {
      host.style.display = "none";
    }
  }

  return {
    show,
    hide
  };
}

/**
 * Backward-compatible alias for older imports.
 *
 * @param {{
 *   onCancel: () => void,
 *   onSendAnyway: () => void
 * }} handlers
 */
export function createWarningDialog(handlers) {
  return createReviewDialog({
    onCancel: handlers.onCancel,
    onSendSanitized: handlers.onSendAnyway,
    onSendOriginal: handlers.onSendAnyway
  });
}
