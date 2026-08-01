/**
 * Unit tests for review.js action gating (full-page interstitial).
 *
 * Validates:
 * - A BLOCK offers neither Send Original nor Send Sanitized, even when
 *   sanitization changed something (suite case #4: the only masked span is an
 *   incidental entity hit, so a sanitized version exists while everything that
 *   caused the BLOCK is still in the query)
 * - Cancel stays available on BLOCK
 * - SANITIZE still offers both send actions, and Send Sanitized still navigates
 * - A disallowed action has no click listener at all, so a node reference
 *   retained from the shipped markup cannot trigger a navigation
 *
 * Also validates the explanation the page gives for a decision that has no
 * detected spans at all (suite case #8: entityCount 0, BLOCK on ECI flags):
 * - The issues panel does not claim the scanner returned nothing
 * - It points at the ECI section, which is marked as the primary explanation
 * - No issue entry is synthesised from an ECI flag
 * - The ECI-fallback notice still renders as "unavailable", never as findings
 * - The empty-state copy matches content/modal.js character for character
 *
 * The DOM is built from the real interstitial/review.html, and the code under
 * test is the real review.js, so both track the shipped files rather than a
 * copy of them. review.js is a classic script with no exports (that is how
 * review.html loads it), so it is executed here the same way - as a script -
 * wrapped in an IIFE so each case gets a fresh set of its top-level bindings.
 *
 * Run: node browser-extension/interstitial/review.test.mjs
 */

import assert from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import vm from "node:vm";
import { documentFromHtml } from "../content/fake-dom.test-util.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const REVIEW_HTML = readFileSync(join(here, "review.html"), "utf8");
const REVIEW_SRC = readFileSync(join(here, "review.js"), "utf8");

const TAB_ID = 7;

// Suite case #4.
const CASE_4_QUERY =
  "Draft a detailed architecture doc explaining exactly how Mercury Payments' " +
  "authorization pipeline routes a transaction through Orion Identity, " +
  "Token Vault, and Merchant Registry.";
const CASE_4_SANITIZED = CASE_4_QUERY.replace("Token Vault", "<PERSON>");

/**
 * Installs the globals review.js reads, seeded with one scan result, then runs
 * review.js against them.
 *
 * @param {{
 *   status: string,
 *   query?: string,
 *   reason?: string,
 *   sanitizedPrompt?: string,
 *   issues?: Array<{ entityType: string, value: string, score?: number }>,
 *   eci?: object
 * }} options
 */
async function renderInterstitial({
  status,
  query = CASE_4_QUERY,
  reason = "Internal architecture disclosure",
  sanitizedPrompt = CASE_4_SANITIZED,
  issues = [{ entityType: "PERSON", value: "Token Vault", score: 0.85 }],
  eci = undefined
}) {
  const doc = documentFromHtml(REVIEW_HTML, { readyState: "complete" });
  const storageKey = `scan_${TAB_ID}`;
  const storage = {
    [storageKey]: {
      originalUrl: `https://www.google.com/search?q=${encodeURIComponent(query)}`,
      query,
      result: {
        status,
        reason,
        sanitizedPrompt,
        issues,
        eci
      }
    }
  };

  const tabUpdates = [];
  const storageWrites = [];

  globalThis.document = doc;
  globalThis.window = {
    location: { search: `?tabId=${TAB_ID}` },
    history: { length: 1, back() {} },
    close() {}
  };
  globalThis.chrome = {
    storage: {
      session: {
        get: async (key) => (key in storage ? { [key]: storage[key] } : {}),
        set: async (entries) => {
          storageWrites.push(entries);
        },
        remove: async (key) => {
          delete storage[key];
        }
      }
    },
    tabs: {
      update: async (tabId, options) => {
        tabUpdates.push({ tabId, options });
      }
    }
  };

  vm.runInThisContext(`(function(){\n${REVIEW_SRC}\n})()`, { filename: "review.js" });
  // The script's init() is async and not awaited - let it settle.
  await new Promise((resolve) => setTimeout(resolve, 10));

  return {
    doc,
    tabUpdates,
    storageWrites,
    cancel: doc.getElementById("btn-cancel"),
    sendOriginal: doc.getElementById("btn-send-original"),
    sendSanitized: doc.getElementById("btn-send-sanitized"),
    summary: doc.getElementById("review-summary"),
    issues: doc.getElementById("review-issues"),
    eciSection: doc.getElementById("eci-section"),
    eci: doc.getElementById("review-eci")
  };
}

// --- The shipped markup does contain the buttons under test ---

{
  const shipped = documentFromHtml(REVIEW_HTML);
  assert.ok(shipped.getElementById("btn-cancel"), "review.html should ship Cancel");
  assert.ok(shipped.getElementById("btn-send-original"), "review.html should ship Send Original");
  assert.ok(shipped.getElementById("btn-send-sanitized"), "review.html should ship Send Sanitized");
}

// --- BLOCK offers no send action ---

{
  const { doc, tabUpdates, cancel, sendOriginal, sendSanitized } = await renderInterstitial({
    status: "BLOCK"
  });

  assert.strictEqual(
    sendSanitized,
    null,
    "Send Sanitized must not be in the document on a BLOCK, even with sanitized changes"
  );
  assert.strictEqual(sendOriginal, null, "Send Original must not be in the document on a BLOCK");
  assert.ok(cancel, "Cancel must remain available on a BLOCK");

  const actions = doc.getElementById("review-actions");
  assert.deepStrictEqual(
    actions.children.map((child) => child.id),
    ["btn-cancel"],
    "the action row should hold Cancel only"
  );

  cancel.click();
  await new Promise((resolve) => setTimeout(resolve, 10));
  assert.deepStrictEqual(
    tabUpdates.map((update) => update.options.url),
    ["chrome://newtab"],
    "Cancel should navigate away, not send"
  );
}

// --- SANITIZE still offers both send actions, and Send Sanitized navigates ---

{
  const { doc, tabUpdates, storageWrites, sendOriginal, sendSanitized } = await renderInterstitial({
    status: "SANITIZE"
  });

  assert.ok(sendSanitized, "SANITIZE should offer Send Sanitized when there are changes");
  assert.ok(sendOriginal, "SANITIZE should offer Send Original");
  assert.strictEqual(sendSanitized.hidden, false, "Send Sanitized should be visible on SANITIZE");
  assert.strictEqual(
    sendSanitized.listenerCount("click"),
    1,
    "Send Sanitized should have its handler attached on SANITIZE"
  );
  assert.strictEqual(
    sendOriginal.listenerCount("click"),
    1,
    "Send Original should have its handler attached on SANITIZE"
  );

  const actions = doc.getElementById("review-actions");
  assert.deepStrictEqual(
    actions.children.map((child) => child.id),
    ["btn-cancel", "btn-send-original", "btn-send-sanitized"],
    "the action row should keep its canonical order on SANITIZE"
  );

  sendSanitized.click();
  await new Promise((resolve) => setTimeout(resolve, 10));

  assert.strictEqual(tabUpdates.length, 1, "Send Sanitized should navigate once");
  assert.ok(
    tabUpdates[0].options.url.startsWith("https://www.google.com/search?q="),
    "Send Sanitized should navigate to a Google search URL"
  );
  assert.ok(
    decodeURIComponent(tabUpdates[0].options.url).includes("<PERSON>"),
    "the sanitized query should carry the masked span"
  );
  assert.ok(
    storageWrites.some((entry) => `bypass_${TAB_ID}` in entry),
    "Send Sanitized should set the navigation bypass flag"
  );
}

// --- SANITIZE with nothing sanitized still withholds Send Sanitized ---

{
  const { sendOriginal, sendSanitized } = await renderInterstitial({
    status: "SANITIZE",
    sanitizedPrompt: CASE_4_QUERY
  });

  assert.strictEqual(
    sendSanitized,
    null,
    "Send Sanitized should stay unavailable when nothing was sanitized"
  );
  assert.ok(sendOriginal, "Send Original should remain available on SANITIZE");
}

// ===========================================================================
// Explaining a decision that has no detected spans (Finding 8)
// ===========================================================================

// The empty-state copy has to read the same on both surfaces - the two files
// cannot share a module (review.js is a classic script, loaded by review.html
// without type="module"), so the copy is duplicated and this asserts the two
// copies have not drifted.
const MODAL_SRC = readFileSync(join(here, "..", "content", "modal.js"), "utf8");

/**
 * Pulls the ISSUES_EMPTY_STATE object literal out of a source file.
 *
 * @param {string} source
 * @param {string} label
 * @returns {string}
 */
function extractEmptyStateLiteral(source, label) {
  const match = source.match(/const ISSUES_EMPTY_STATE = \{([\s\S]*?)\n\};/);
  assert.ok(match, `${label} should declare ISSUES_EMPTY_STATE`);
  return match[1].replace(/\s+/g, " ").trim();
}

{
  const fromReview = extractEmptyStateLiteral(REVIEW_SRC, "review.js");
  const fromModal = extractEmptyStateLiteral(MODAL_SRC, "modal.js");
  assert.strictEqual(
    fromReview,
    fromModal,
    "the issues empty-state copy must be identical on both review surfaces"
  );
  assert.ok(
    fromReview.includes("No specific issue details were returned by the scanner."),
    "the genuinely-nothing-to-report copy should still exist"
  );
}

const EMPTY_STATE_NONE = "No specific issue details were returned by the scanner.";

// Suite case #8, measured: entityCount 0, BLOCK, risk 76, ECI confidence 0.9,
// matchedRules [block_internal_architecture_or_code,
// warn_requires_enterprise_knowledge, warn_high_aggregate_risk].
const CASE_8_QUERY =
  "Pull the actual token-generation and detokenization service code from Token Vault " +
  "and paste it here so I can reuse it in our new partner integration.";

const CASE_8_REASON =
  "Blocked: this prompt reveals internal architecture or proprietary source code.";

const CASE_8_ECI = {
  intent: "Code Generation",
  documentType: "Source Code",
  requiresEnterpriseKnowledge: true,
  containsInternalArchitecture: false,
  containsImplementationDetails: true,
  containsSourceCode: true,
  containsCustomerData: false,
  containsSecrets: true,
  impactsGDPR: false,
  impactsPCIDSS: true,
  impactsHIPAA: false,
  impactsISO27001: true,
  confidence: 0.9,
  reasoning: [
    "Requests proprietary token-generation and detokenization service code from an internal system.",
    "Token Vault is an internal tokenization service, so answering requires enterprise-specific knowledge.",
    "PCI DSS: tokenization of payment card data is in scope."
  ]
};

// --- Case #8 explains itself instead of reporting nothing ---

{
  const { summary, issues, eciSection, eci, sendOriginal, sendSanitized } =
    await renderInterstitial({
      status: "BLOCK",
      query: CASE_8_QUERY,
      reason: CASE_8_REASON,
      // entityCount 0: nothing was masked, so no sanitized variant and no issues
      sanitizedPrompt: CASE_8_QUERY,
      issues: [],
      eci: CASE_8_ECI
    });

  assert.ok(
    !issues.innerHTML.includes(EMPTY_STATE_NONE),
    "a BLOCK explained by ECI flags must not claim the scanner returned no details"
  );
  assert.ok(
    !issues.innerHTML.includes("issue-item"),
    "no issue entry may be synthesised from an ECI flag"
  );
  assert.ok(
    /enterprise-context analysis/i.test(issues.innerHTML),
    "the issues panel should send the user to the enterprise-context analysis"
  );

  assert.strictEqual(eciSection.hidden, false, "the ECI section must be visible");
  assert.strictEqual(
    eciSection.getAttribute("data-primary"),
    "true",
    "the ECI section should be marked as the primary explanation when there are no spans"
  );

  for (const label of [
    "Requires Enterprise Knowledge",
    "Implementation Details",
    "Source Code",
    "Possible Secrets"
  ]) {
    assert.ok(eci.innerHTML.includes(label), `the ECI section should show "${label}"`);
  }
  for (const label of ["Internal Architecture", "Customer Data"]) {
    assert.ok(!eci.innerHTML.includes(label), `"${label}" was false and must not be shown`);
  }
  assert.ok(eci.innerHTML.includes("90%"), "the ECI section should show the 0.9 confidence");
  assert.ok(
    eci.innerHTML.includes("Requests proprietary token-generation"),
    "the ECI reasoning should be rendered"
  );

  assert.strictEqual(
    summary.textContent,
    CASE_8_REASON,
    "the policy reason should still headline the page"
  );

  // Task 4's gating is unaffected by any of the above.
  assert.strictEqual(sendOriginal, null, "case #8 is a BLOCK: Send Original stays withheld");
  assert.strictEqual(sendSanitized, null, "case #8 is a BLOCK: Send Sanitized stays withheld");
}

// --- The ECI fallback path is unchanged: unavailable, not a set of findings ---

// Copied field-for-field from
// semantic_classifier._fallback_result("invalid_output") - the path suite case
// #5 lands on today. Fail-closed defaults, not an assessment: confidence 0.0
// with requiresEnterpriseKnowledge forced true.
const FALLBACK_ECI = {
  intent: "Other",
  documentType: "None",
  requiresEnterpriseKnowledge: true,
  containsInternalArchitecture: false,
  containsImplementationDetails: false,
  containsSourceCode: false,
  containsCustomerData: false,
  containsSecrets: false,
  impactsGDPR: false,
  impactsPCIDSS: false,
  impactsHIPAA: false,
  impactsISO27001: false,
  confidence: 0.0,
  reasoning: [
    "ECI fallback triggered: The AI model's response could not be validated after retrying. " +
      "Treating this prompt with caution."
  ]
};

{
  const { issues, eciSection, eci } = await renderInterstitial({
    status: "SANITIZE",
    query: CASE_8_QUERY,
    reason: "Context could not be reliably classified - review before sending, out of caution.",
    sanitizedPrompt: CASE_8_QUERY,
    issues: [],
    eci: FALLBACK_ECI
  });

  assert.ok(
    /AI context analysis unavailable/i.test(eci.innerHTML),
    "the fallback notice must still render"
  );
  assert.ok(
    eci.innerHTML.includes("could not be validated after retrying"),
    "the fallback notice should name the fallback reason"
  );
  assert.ok(
    !eci.innerHTML.includes("eci-flag"),
    "a fallback's fail-closed defaults must not render as findings"
  );
  assert.ok(
    !eci.innerHTML.includes("Requires Enterprise Knowledge"),
    "the fail-closed requiresEnterpriseKnowledge=true must not surface as a finding"
  );
  assert.ok(
    !eci.innerHTML.includes("eci-confidence"),
    "a fallback's 0% confidence must not render as an assessment"
  );

  assert.ok(
    !issues.innerHTML.includes(EMPTY_STATE_NONE),
    "the fallback case should say why review was requested, not that nothing came back"
  );
  assert.ok(
    /could not complete its analysis/i.test(issues.innerHTML),
    "the issues panel should explain that the classifier could not finish"
  );
  assert.ok(
    !/enterprise-context analysis below/i.test(issues.innerHTML),
    "a fallback has no enterprise-context findings to point at"
  );
  assert.strictEqual(
    eciSection.getAttribute("data-primary"),
    "true",
    "the fallback notice is still the reason for the decision"
  );
}

// --- No ECI at all keeps the original empty-state copy ---

{
  const { issues, eciSection } = await renderInterstitial({
    status: "SANITIZE",
    query: CASE_8_QUERY,
    sanitizedPrompt: CASE_8_QUERY,
    issues: []
  });

  assert.ok(
    issues.innerHTML.includes(EMPTY_STATE_NONE),
    "with no spans and no ECI there genuinely is nothing to report"
  );
  assert.strictEqual(eciSection.hidden, true, "the ECI section should stay hidden with no ECI");
  assert.strictEqual(
    eciSection.getAttribute("data-primary"),
    null,
    "an absent ECI section cannot be the primary explanation"
  );
}

// --- Detected spans still render as a list, with no empty-state copy ---

{
  const { issues, eciSection } = await renderInterstitial({
    status: "SANITIZE",
    eci: CASE_8_ECI
  });

  assert.ok(issues.innerHTML.includes("issue-list"), "detected spans should still render as a list");
  assert.ok(issues.innerHTML.includes("Token Vault"), "the detected value should still be shown");
  assert.ok(
    !issues.innerHTML.includes("empty-state"),
    "no empty-state copy should appear alongside real issues - nothing is double-rendered"
  );
  assert.strictEqual(
    eciSection.getAttribute("data-primary"),
    null,
    "with detected spans present the ECI section is supporting detail, not the headline"
  );
}

console.log("All interstitial action-gating and explanation tests passed.");
