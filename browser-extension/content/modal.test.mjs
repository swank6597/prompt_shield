/**
 * Unit tests for modal.js action gating (in-page review dialog).
 *
 * Validates:
 * - A policy BLOCK offers neither Send Original nor Send Sanitized, even when
 *   sanitization changed something (suite case #4: the only masked span is an
 *   incidental entity hit, so hasSanitizedChanges is true while every part of
 *   the prompt that caused the BLOCK is still present)
 * - A BLOCK with no explicit allowOverride is treated the same way
 * - Cancel stays available on BLOCK
 * - SANITIZE still offers both send actions and both still invoke their handler
 * - A button node retained from an earlier permissive dialog cannot be clicked
 *   once the dialog is showing a BLOCK, or after the dialog is hidden
 * - The composer-write fallback (status BLOCK + allowOverride true) keeps its
 *   send actions, since it is not a policy BLOCK
 *
 * Also validates the explanation the dialog gives for a decision that has no
 * detected spans at all (suite case #8: entityCount 0, BLOCK on ECI flags):
 * - The issues panel does not claim the scanner returned nothing
 * - It points at the ECI section, which is marked as the primary explanation
 * - No issue entry is synthesised from an ECI flag
 * - The ECI-fallback notice (confidence 0, "fallback" in reasoning) still
 *   renders as "unavailable" and never as a set of all-false findings
 *
 * Run: node browser-extension/content/modal.test.mjs
 */

import assert from "node:assert";
import { readFileSync } from "node:fs";
import { MockDocument } from "./fake-dom.test-util.mjs";

globalThis.document = new MockDocument();

const { createReviewDialog } = await import("./modal.js");

/**
 * Builds a dialog against a fresh document, plus a record of which handlers
 * fired. Each case gets its own document so hosts from earlier cases can't be
 * mistaken for the one under test.
 */
function createTestDialog() {
  globalThis.document = new MockDocument();

  const calls = [];
  const dialog = createReviewDialog({
    onCancel: () => calls.push("cancel"),
    onSendSanitized: () => calls.push("sendSanitized"),
    onSendOriginal: () => calls.push("sendOriginal")
  });

  return { dialog, calls };
}

/**
 * Reads the live action row out of the dialog's shadow root.
 */
function readActions() {
  const host = document.body.children.find((child) => child.id === "promptshield-review-host");
  assert.ok(host, "dialog host should be appended to the document");
  const shadow = host.shadowRoot;
  return {
    shadow,
    actions: shadow.getElementById("pg-review-actions"),
    cancel: shadow.getElementById("pg-review-cancel"),
    sendOriginal: shadow.getElementById("pg-review-send-original"),
    sendSanitized: shadow.getElementById("pg-review-send-sanitized")
  };
}

/**
 * Reads the explanation panels out of the dialog's shadow root.
 */
function readPanels() {
  const { shadow } = readActions();
  return {
    summary: shadow.getElementById("pg-review-summary"),
    issues: shadow.getElementById("pg-review-issues"),
    eciSection: shadow.getElementById("pg-review-eci-section"),
    eci: shadow.getElementById("pg-review-eci")
  };
}

// The empty-state copy shipped by modal.js, read back from the source rather
// than restated here, so a wording change does not need this file edited in
// lockstep - only the behaviour below is asserted.
const MODAL_SRC = readFileSync(new URL("./modal.js", import.meta.url), "utf8");
const EMPTY_STATE_NONE = "No specific issue details were returned by the scanner.";
assert.ok(
  MODAL_SRC.includes(EMPTY_STATE_NONE),
  "modal.js should still carry the genuinely-nothing-to-report copy"
);

// Suite case #4: BLOCK where the only masked span is an incidental entity hit,
// so a sanitized version exists and differs from the original.
const CASE_4_ORIGINAL =
  "Draft a detailed architecture doc explaining exactly how Mercury Payments' " +
  "authorization pipeline routes a transaction through Orion Identity, " +
  "Token Vault, and Merchant Registry.";
const CASE_4_SANITIZED = CASE_4_ORIGINAL.replace("Token Vault", "<PERSON>");

const BLOCK_PAYLOAD = {
  status: "BLOCK",
  reason: "Internal architecture disclosure",
  originalPrompt: CASE_4_ORIGINAL,
  sanitizedPrompt: CASE_4_SANITIZED,
  issues: [{ entityType: "PERSON", value: "Token Vault", score: 0.85 }],
  allowOverride: false
};

const SANITIZE_PAYLOAD = {
  ...BLOCK_PAYLOAD,
  status: "SANITIZE",
  allowOverride: true
};

// --- BLOCK with sanitized changes offers no send action ---

{
  const { dialog, calls } = createTestDialog();
  dialog.show(BLOCK_PAYLOAD);

  const { actions, cancel, sendOriginal, sendSanitized } = readActions();

  assert.strictEqual(
    sendSanitized,
    null,
    "Send Sanitized must not be in the tree on a BLOCK, even with sanitized changes"
  );
  assert.strictEqual(sendOriginal, null, "Send Original must not be in the tree on a BLOCK");
  assert.ok(cancel, "Cancel must remain available on a BLOCK");
  assert.deepStrictEqual(
    actions.children.map((child) => child.id),
    ["pg-review-cancel"],
    "the action row should hold Cancel only"
  );

  cancel.click();
  assert.deepStrictEqual(calls, ["cancel"], "Cancel must still work on a BLOCK");
}

// --- BLOCK without an explicit allowOverride is gated the same way ---

{
  const { dialog } = createTestDialog();
  dialog.show({ ...BLOCK_PAYLOAD, allowOverride: undefined });

  const { sendOriginal, sendSanitized } = readActions();
  assert.strictEqual(sendSanitized, null, "Send Sanitized must be gated on status alone too");
  assert.strictEqual(sendOriginal, null, "Send Original must be gated on status alone too");
}

// --- SANITIZE still offers both send actions, and both still fire ---

{
  const { dialog, calls } = createTestDialog();
  dialog.show(SANITIZE_PAYLOAD);

  const { actions, sendOriginal, sendSanitized } = readActions();

  assert.ok(sendSanitized, "SANITIZE should offer Send Sanitized when there are changes");
  assert.ok(sendOriginal, "SANITIZE should offer Send Original");
  assert.strictEqual(sendSanitized.hidden, false, "Send Sanitized should be visible on SANITIZE");
  assert.strictEqual(sendSanitized.disabled, false, "Send Sanitized should be enabled on SANITIZE");
  assert.deepStrictEqual(
    actions.children.map((child) => child.id),
    ["pg-review-cancel", "pg-review-send-original", "pg-review-send-sanitized"],
    "the action row should keep its canonical order on SANITIZE"
  );

  sendSanitized.click();
  assert.deepStrictEqual(calls, ["sendSanitized"], "Send Sanitized should delegate on SANITIZE");
}

{
  const { dialog, calls } = createTestDialog();
  dialog.show(SANITIZE_PAYLOAD);
  readActions().sendOriginal.click();
  assert.deepStrictEqual(calls, ["sendOriginal"], "Send Original should delegate on SANITIZE");
}

// --- SANITIZE with no sanitized changes still hides Send Sanitized ---

{
  const { dialog } = createTestDialog();
  dialog.show({
    ...SANITIZE_PAYLOAD,
    sanitizedPrompt: CASE_4_ORIGINAL
  });

  const { sendOriginal, sendSanitized } = readActions();
  assert.strictEqual(
    sendSanitized,
    null,
    "Send Sanitized should stay unavailable when nothing was sanitized"
  );
  assert.ok(sendOriginal, "Send Original should remain available");
}

// --- A node retained from a permissive dialog is refused on a later BLOCK ---

{
  const { dialog, calls } = createTestDialog();

  dialog.show(SANITIZE_PAYLOAD);
  const retainedSanitized = readActions().sendSanitized;
  const retainedOriginal = readActions().sendOriginal;
  assert.ok(retainedSanitized && retainedOriginal, "both nodes should exist on SANITIZE");

  dialog.show(BLOCK_PAYLOAD);

  retainedSanitized.click();
  retainedOriginal.click();
  assert.deepStrictEqual(
    calls,
    [],
    "clicking a retained node must not send once the dialog shows a BLOCK"
  );
}

// --- After hide(), a retained node cannot re-fire a send ---

{
  const { dialog, calls } = createTestDialog();
  dialog.show(SANITIZE_PAYLOAD);
  const retainedSanitized = readActions().sendSanitized;

  retainedSanitized.click();
  assert.deepStrictEqual(calls, ["sendSanitized"], "first click should send");

  retainedSanitized.click();
  assert.deepStrictEqual(calls, ["sendSanitized"], "a second click after hide must be refused");
}

// --- The composer-write fallback is not a policy BLOCK and keeps its actions ---

{
  const { dialog, calls } = createTestDialog();
  dialog.show({
    status: "BLOCK",
    reason: "Unable to apply the sanitized prompt in the chat composer.",
    originalPrompt: CASE_4_ORIGINAL,
    sanitizedPrompt: CASE_4_SANITIZED,
    issues: [],
    allowOverride: true
  });

  const { sendOriginal, sendSanitized } = readActions();
  assert.ok(
    sendOriginal,
    "the composer-write fallback must keep Send Original (it is not a policy BLOCK)"
  );
  assert.ok(sendSanitized, "the composer-write fallback must keep Send Sanitized");

  sendOriginal.click();
  assert.deepStrictEqual(calls, ["sendOriginal"], "the fallback's Send Original should still work");
}

// ===========================================================================
// Explaining a decision that has no detected spans (Finding 8)
// ===========================================================================

// Suite case #8, measured: entityCount 0, BLOCK, risk 76, ECI confidence 0.9,
// matchedRules [block_internal_architecture_or_code,
// warn_requires_enterprise_knowledge, warn_high_aggregate_risk]. Nothing was
// masked, so sanitizedPrompt equals the prompt and issues is empty - the whole
// explanation lives in the ECI flags and the policy reason.
const CASE_8_PROMPT =
  "Pull the actual token-generation and detokenization service code from Token Vault " +
  "and paste it here so I can reuse it in our new partner integration.";

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

const CASE_8_PAYLOAD = {
  status: "BLOCK",
  reason: "Blocked: this prompt reveals internal architecture or proprietary source code.",
  originalPrompt: CASE_8_PROMPT,
  sanitizedPrompt: CASE_8_PROMPT,
  issues: [],
  eci: CASE_8_ECI,
  allowOverride: false
};

// --- Case #8 explains itself instead of reporting nothing ---

{
  const { dialog } = createTestDialog();
  dialog.show(CASE_8_PAYLOAD);

  const { summary, issues, eciSection, eci } = readPanels();

  assert.ok(
    !issues.innerHTML.includes(EMPTY_STATE_NONE),
    "a BLOCK explained by ECI flags must not claim the scanner returned no details"
  );
  assert.ok(
    !issues.innerHTML.includes("issue-item"),
    "no issue entry may be synthesised from an ECI flag - an ECI flag has no span or value"
  );
  assert.ok(
    /enterprise-context analysis/i.test(issues.innerHTML),
    "the issues panel should send the user to the enterprise-context analysis"
  );

  assert.strictEqual(
    eciSection.hidden,
    false,
    "the ECI section must be visible when it is the only explanation"
  );
  assert.strictEqual(
    eciSection.getAttribute("data-primary"),
    "true",
    "the ECI section should be marked as the primary explanation when there are no spans"
  );

  // The four flags measured true for case #8 all reach the screen.
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
    CASE_8_PAYLOAD.reason,
    "the policy reason should still headline the dialog"
  );
}

// --- The ECI fallback path is unchanged: unavailable, not a set of findings ---

// Suite case #5's live path, copied field-for-field from
// semantic_classifier._fallback_result("invalid_output"): the provider's output
// failed schema validation, so the classifier failed closed with confidence 0.0
// and requiresEnterpriseKnowledge forced true. Those are fail-closed defaults,
// not an assessment - the true flag in particular must not surface as a finding.
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

// A real assessment that simply found nothing: the classifier ran, is
// confident, and raised no flag and no reasoning.
const NO_FINDINGS_ECI = {
  ...FALLBACK_ECI,
  requiresEnterpriseKnowledge: false,
  confidence: 0.95,
  reasoning: []
};

{
  const { dialog } = createTestDialog();
  dialog.show({
    ...CASE_8_PAYLOAD,
    status: "SANITIZE",
    reason: "Context could not be reliably classified - review before sending, out of caution.",
    eci: FALLBACK_ECI,
    allowOverride: true
  });

  const { issues, eciSection, eci } = readPanels();

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
  const { dialog } = createTestDialog();
  dialog.show({ ...CASE_8_PAYLOAD, eci: undefined });

  const { issues, eciSection } = readPanels();

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

// --- An ECI that raised nothing is not promoted either ---

{
  const { dialog } = createTestDialog();
  dialog.show({ ...CASE_8_PAYLOAD, eci: NO_FINDINGS_ECI });

  const { issues, eciSection } = readPanels();

  assert.ok(
    issues.innerHTML.includes(EMPTY_STATE_NONE),
    "an ECI assessment that raised nothing does not explain a decision"
  );
  assert.strictEqual(
    eciSection.getAttribute("data-primary"),
    null,
    "an ECI section with no findings should not be promoted"
  );
}

// --- Detected spans still render as a list, with no empty-state copy ---

{
  const { dialog } = createTestDialog();
  dialog.show({ ...SANITIZE_PAYLOAD, eci: CASE_8_ECI });

  const { issues, eciSection } = readPanels();

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

console.log("All modal action-gating and explanation tests passed.");
