import { resolveScanIssues } from "../utils/scan-utils.js";

/**
 * Default selectors for Google suggestion chips across AI Mode and AI Overviews.
 */
export const GOOGLE_CHIP_SELECTORS = [
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
export function createChipInterceptor({ Logger, scanClient, reviewDialog, chipSelectors, documentRef, windowRef }) {
  const state = {
    listenerController: null,
    bypassClick: false,
    scanInFlight: false,
    pendingElement: null,
    pendingChipText: null,
    pendingSanitizedText: null,
    // True when the pending decision was a policy BLOCK. Both send handlers
    // refuse while this is set, so the decision holds even if the dialog's
    // buttons are reached directly (the dialog host uses an open shadow root).
    pendingSendBlocked: false
  };

  /**
   * Builds the combined selector string for chip matching.
   *
   * @returns {string}
   */
  function buildCombinedSelector() {
    return chipSelectors.join(", ");
  }

  /**
   * Finds the chip element from the click target by checking the target itself
   * and then walking up to find a matching ancestor.
   *
   * @param {EventTarget | null} target
   * @returns {HTMLElement | null}
   */
  function findChipElement(target) {
    if (!(target instanceof HTMLElement)) {
      return null;
    }

    const combinedSelector = buildCombinedSelector();

    if (target.matches(combinedSelector)) {
      return target;
    }

    const ancestor = target.closest(combinedSelector);
    if (ancestor instanceof HTMLElement) {
      return ancestor;
    }

    return null;
  }

  /**
   * Extracts the query text from a chip element by checking data attributes
   * and falling back to innerText.
   *
   * @param {HTMLElement} element
   * @returns {string}
   */
  function extractChipText(element) {
    // Try structured data attributes first
    const followupText = element.getAttribute("data-followup-text");
    if (followupText && followupText.trim()) {
      return followupText.trim();
    }

    const dataQ = element.getAttribute("data-q");
    if (dataQ && dataQ.trim()) {
      return dataQ.trim();
    }

    const chipAction = element.getAttribute("data-chip-action");
    if (chipAction && chipAction.trim()) {
      return chipAction.trim();
    }

    // Fall back to visible text content
    const innerText = (element.innerText || element.textContent || "").trim();
    return innerText;
  }

  /**
   * Replays the original chip click by setting the bypass flag and triggering click.
   *
   * @param {HTMLElement} element
   */
  function replayChipClick(element) {
    state.bypassClick = true;
    element.click();
  }

  /**
   * Attempts to find the prompt input on the page and write sanitized text into it,
   * then submits. Returns true if successful.
   *
   * @param {string} sanitizedText
   * @returns {boolean}
   */
  function writeSanitizedToInput(sanitizedText) {
    // Try common prompt input selectors for Google Search AI surfaces
    const inputSelectors = [
      "textarea[aria-label*='Search' i]",
      "div[contenteditable='true'][aria-label*='Search' i]",
      "div[contenteditable='true'][role='textbox']",
      "input[aria-label*='Ask a follow up' i]",
      "textarea[aria-label*='follow' i]",
      "textarea[name='q']",
      "input[name='q']"
    ];

    let inputElement = null;
    for (const selector of inputSelectors) {
      const candidate = documentRef.querySelector(selector);
      if (candidate instanceof HTMLElement) {
        inputElement = candidate;
        break;
      }
    }

    if (!inputElement) {
      return false;
    }

    // Write text into the input
    if ("value" in inputElement && typeof inputElement.value === "string") {
      inputElement.value = sanitizedText;
      inputElement.dispatchEvent(new Event("input", { bubbles: true }));
      inputElement.dispatchEvent(new Event("change", { bubbles: true }));
    } else {
      inputElement.focus();
      const selection = windowRef.getSelection();
      const range = documentRef.createRange();
      range.selectNodeContents(inputElement);
      selection?.removeAllRanges();
      selection?.addRange(range);

      if (typeof documentRef.execCommand === "function") {
        documentRef.execCommand("insertText", false, sanitizedText);
      } else {
        inputElement.textContent = sanitizedText;
      }

      inputElement.dispatchEvent(
        new InputEvent("input", {
          bubbles: true,
          cancelable: true,
          inputType: "insertText",
          data: sanitizedText
        })
      );
    }

    // Try to submit
    const form = inputElement.closest("form");
    if (form && typeof form.requestSubmit === "function") {
      form.requestSubmit();
      return true;
    }

    if (form) {
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      return true;
    }

    // Try clicking a send button near the input
    const sendButton = documentRef.querySelector(
      "button[aria-label*='Search' i], button[aria-label*='Send' i], button[type='submit']"
    );
    if (sendButton instanceof HTMLElement) {
      sendButton.click();
      return true;
    }

    return false;
  }

  /**
   * Shows the review dialog for a chip interception.
   *
   * @param {{
   *   status: string,
   *   reason?: string,
   *   chipText: string,
   *   sanitizedPrompt: string,
   *   issues?: Array<{ entityType: string, value: string, score?: number }>,
   *   eci?: unknown,
   *   element: HTMLElement
   * }} payload
   */
  function showChipReviewDialog(payload) {
    state.pendingElement = payload.element;
    state.pendingChipText = payload.chipText;
    state.pendingSanitizedText = payload.sanitizedPrompt;
    // Enforced again in the send handlers, not just in the dialog's markup.
    state.pendingSendBlocked = String(payload.status ?? "").toUpperCase() === "BLOCK";

    reviewDialog.show({
      status: payload.status,
      reason: payload.reason,
      originalPrompt: payload.chipText,
      sanitizedPrompt: payload.sanitizedPrompt,
      issues: payload.issues ?? [],
      eci: payload.eci,
      allowOverride: payload.status !== "BLOCK",
      onCancel: handleCancel,
      onSendOriginal: handleSendOriginal,
      onSendSanitized: handleSendSanitized
    });
  }

  /**
   * Handles "Cancel" action — drops the chip click.
   */
  function handleCancel() {
    Logger.info("Chip review: cancelled");
    reviewDialog.hide();
    clearPendingState();
  }

  /**
   * Handles "Send Original" — replays the original chip click.
   */
  function handleSendOriginal() {
    if (state.pendingSendBlocked) {
      Logger.warn("Chip review: send refused, the scan decision was BLOCK");
      return;
    }

    Logger.info("Chip review: sending original");
    reviewDialog.hide();
    const element = state.pendingElement;
    clearPendingState();

    if (element) {
      replayChipClick(element);
    }
  }

  /**
   * Handles "Send Sanitized" — writes sanitized text to prompt input and submits.
   * Falls back to "Send Original" if no input is available.
   */
  function handleSendSanitized() {
    if (state.pendingSendBlocked) {
      Logger.warn("Chip review: send refused, the scan decision was BLOCK");
      return;
    }

    Logger.info("Chip review: sending sanitized");
    reviewDialog.hide();
    const sanitizedText = state.pendingSanitizedText;
    const element = state.pendingElement;
    clearPendingState();

    if (sanitizedText && writeSanitizedToInput(sanitizedText)) {
      Logger.info("Sanitized chip text written to input and submitted");
      return;
    }

    // Fallback: replay original click if can't write sanitized text
    Logger.warn("Could not write sanitized text to input, replaying original chip click");
    if (element) {
      replayChipClick(element);
    }
  }

  /**
   * Clears all pending state after a review action.
   */
  function clearPendingState() {
    state.pendingElement = null;
    state.pendingChipText = null;
    state.pendingSanitizedText = null;
    state.pendingSendBlocked = false;
    state.scanInFlight = false;
  }

  /**
   * Main click handler attached in the capture phase.
   *
   * @param {MouseEvent} event
   */
  async function handleClick(event) {
    // Allow replayed clicks to pass through
    if (state.bypassClick) {
      state.bypassClick = false;
      return;
    }

    const chipElement = findChipElement(event.target);
    if (!chipElement) {
      return;
    }

    // Prevent the click from reaching Google's handlers
    event.preventDefault();
    event.stopImmediatePropagation();

    // Ignore if already processing a chip
    if (state.scanInFlight) {
      Logger.info("Chip click ignored: scan already in flight");
      return;
    }

    const chipText = extractChipText(chipElement);
    if (!chipText) {
      Logger.warn("Chip intercepted but no text extracted, allowing click");
      replayChipClick(chipElement);
      return;
    }

    Logger.info(`Chip intercepted: "${chipText}"`);
    state.scanInFlight = true;

    try {
      const result = await scanClient.scanPrompt(chipText);
      const normalizedStatus = String(result.status ?? "SAFE").toUpperCase();
      const sanitizedPrompt =
        typeof result.sanitizedPrompt === "string" ? result.sanitizedPrompt : chipText;

      if (normalizedStatus === "SAFE") {
        Logger.info("Chip scan decision: SAFE");
        state.scanInFlight = false;
        replayChipClick(chipElement);
        return;
      }

      if (normalizedStatus === "SANITIZE" || normalizedStatus === "WARN" || normalizedStatus === "BLOCK") {
        Logger.info(`Chip scan decision: ${normalizedStatus}`);
        if (result.reason) {
          Logger.info(result.reason);
        }

        showChipReviewDialog({
          status: normalizedStatus,
          reason: result.reason,
          chipText,
          sanitizedPrompt,
          issues: resolveScanIssues({
            issues: result.issues,
            reason: result.reason,
            originalPrompt: chipText,
            sanitizedPrompt
          }),
          eci: result.eci,
          element: chipElement
        });
        return;
      }

      // Unknown status — allow through
      Logger.warn(`Chip scan: unexpected status "${normalizedStatus}", allowing click`);
      state.scanInFlight = false;
      replayChipClick(chipElement);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      Logger.warn(`Chip scan failed, allowing click: ${message}`);
      state.scanInFlight = false;
      replayChipClick(chipElement);
    }
  }

  /**
   * Starts the chip interceptor by attaching the capture-phase click listener.
   */
  function start() {
    if (state.listenerController) {
      return;
    }

    state.listenerController = new AbortController();
    documentRef.addEventListener("click", handleClick, {
      capture: true,
      signal: state.listenerController.signal
    });

    Logger.info("Chip interceptor started");
  }

  /**
   * Stops the chip interceptor by removing the click listener and clearing state.
   */
  function stop() {
    state.listenerController?.abort();
    state.listenerController = null;
    clearPendingState();
    Logger.info("Chip interceptor stopped");
  }

  return { start, stop };
}
