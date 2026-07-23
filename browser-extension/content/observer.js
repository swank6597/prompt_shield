import { resolveScanIssues } from "../utils/scan-utils.js";

const PROMPT_OBSERVER_CONFIG = {
  childList: true,
  subtree: true,
  attributes: true,
  characterData: true,
  attributeFilter: [
    "aria-label",
    "aria-disabled",
    "class",
    "data-disabled",
    "disabled",
    "placeholder",
    "style",
    "type"
  ]
};

/**
 * Creates the Milestone 2-5 controller for the active site.
 *
 * @param {{
 *   Logger: { info: (message: string) => void, warn: (message: string) => void, error: (message: string) => void },
 *   detector: ReturnType<typeof import("./detector.js").createPromptGuardianDetector>,
 *   scanClient: { scanPrompt: (prompt: string) => Promise<{ status: string, reason?: string, sanitizedPrompt?: string, issues?: Array<{ entityType: string, value: string, score?: number }>, eci?: import("./modal.js").EciResult, raw?: unknown }> },
 *   reviewDialog: { show: (payload: import("./modal.js").ReviewDialogPayload) => void, hide: () => void },
 *   documentRef: Document,
 *   windowRef: Window
 * }} params
 * @returns {{ start: () => void, stop: () => void, cancelPendingSend: () => void, sendSanitizedPrompt: () => Promise<boolean>, sendOriginalPrompt: () => Promise<boolean> }}
 */
export function createPromptGuardianObserver({ Logger, detector, scanClient, reviewDialog, documentRef, windowRef }) {
  const state = {
    observer: null,
    refreshScheduled: false,
    promptTextArea: null,
    sendButton: null,
    promptListenerController: null,
    sendButtonListenerController: null,
    documentListenerController: null,
    sendAttemptInFlight: false,
    bypassOnce: false,
    pendingReplay: null,
    pendingOriginalPrompt: null,
    pendingSanitizedPrompt: null,
    sendButtonReadyLogged: false
  };

  /**
   * Removes all listener controllers.
   */
  function clearBoundListeners() {
    state.promptListenerController?.abort();
    state.sendButtonListenerController?.abort();
    state.documentListenerController?.abort();
    state.promptListenerController = null;
    state.sendButtonListenerController = null;
    state.documentListenerController = null;
  }

  /**
   * Returns true when the event target belongs to the active prompt composer.
   *
   * @param {EventTarget | null} target
   * @returns {boolean}
   */
  function isPromptEventTarget(target) {
    if (!state.promptTextArea || !(target instanceof Node)) {
      return false;
    }

    return state.promptTextArea === target || state.promptTextArea.contains(target);
  }

  /**
   * Waits briefly so React/contenteditable state can sync before replaying send.
   *
   * @returns {Promise<void>}
   */
  function waitForComposerSync() {
    return new Promise((resolve) => {
      windowRef.requestAnimationFrame(() => {
        windowRef.setTimeout(resolve, 0);
      });
    });
  }

  /**
   * Replaces the composer text with the sanitized prompt.
   *
   * @param {string} sanitizedPrompt
   * @returns {Promise<boolean>}
   */
  async function applySanitizedPrompt(sanitizedPrompt) {
    const promptTextArea = state.promptTextArea;
    if (!promptTextArea) {
      return false;
    }

    const applied = detector.writePromptText(promptTextArea, sanitizedPrompt);
    if (!applied) {
      Logger.warn("Failed to write sanitized prompt into composer");
      return false;
    }

    await waitForComposerSync();
    Logger.info("Sanitized Prompt Applied");
    Logger.info(`Sanitized Prompt:\n\n${sanitizedPrompt}`);
    return true;
  }

  /**
   * Replays the send action after SAFE or sanitized approval.
   *
   * @returns {() => Promise<void>}
   */
  function createReplayAction() {
    return async () => {
      await waitForComposerSync();

      const sendButton = state.sendButton;
      const promptTextArea = state.promptTextArea;

      if (sendButton && typeof sendButton.click === "function") {
        sendButton.click();
        return;
      }

      const form = promptTextArea?.closest("form");
      if (form && typeof form.requestSubmit === "function") {
        form.requestSubmit();
        return;
      }

      if (form) {
        form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      }
    };
  }

  /**
   * Clears pending send state after review or cancellation.
   */
  function clearPendingSendState() {
    state.pendingReplay = null;
    state.pendingOriginalPrompt = null;
    state.pendingSanitizedPrompt = null;
    state.sendAttemptInFlight = false;
  }

  /**
   * Replays the pending send action once.
   *
   * @returns {Promise<boolean>}
   */
  async function replayPendingSend() {
    const replay = state.pendingReplay;
    if (!replay) {
      Logger.warn("No pending send action to replay");
      clearPendingSendState();
      return false;
    }

    state.bypassOnce = true;
    state.sendAttemptInFlight = false;
    state.pendingReplay = null;
    state.pendingOriginalPrompt = null;
    state.pendingSanitizedPrompt = null;

    await replay();
    return true;
  }

  /**
   * Cancels the pending send after the user closes the review dialog.
   */
  function cancelPendingSend() {
    reviewDialog.hide();
    clearPendingSendState();
    Logger.info("Pending send cancelled");
  }

  /**
   * Sends the sanitized prompt after user approval.
   *
   * @returns {Promise<boolean>}
   */
  async function sendSanitizedPrompt() {
    const sanitizedPrompt = state.pendingSanitizedPrompt;
    if (!sanitizedPrompt) {
      Logger.warn("No sanitized prompt available to send");
      return false;
    }

    const applied = await applySanitizedPrompt(sanitizedPrompt);
    if (!applied) {
      reviewDialog.show({
        status: "BLOCK",
        reason: "Unable to apply the sanitized prompt in the chat composer.",
        originalPrompt: state.pendingOriginalPrompt ?? "",
        sanitizedPrompt,
        issues: []
      });
      return false;
    }

    return replayPendingSend();
  }

  /**
   * Sends the original prompt after explicit user override.
   *
   * @returns {Promise<boolean>}
   */
  async function sendOriginalPrompt() {
    if (state.pendingOriginalPrompt && state.promptTextArea) {
      detector.writePromptText(state.promptTextArea, state.pendingOriginalPrompt);
      await waitForComposerSync();
    }

    return replayPendingSend();
  }

  /**
   * Shows the review dialog and waits for the user's decision.
   *
   * @param {{
   *   status: string,
   *   reason?: string,
   *   originalPrompt: string,
   *   sanitizedPrompt: string,
   *   issues?: Array<{ entityType: string, value: string, score?: number }>,
   *   eci?: import("./modal.js").EciResult
   * }} payload
   */
  function showReviewDialog(payload) {
    state.pendingReplay = createReplayAction();
    state.sendAttemptInFlight = false;
    state.pendingSanitizedPrompt = payload.sanitizedPrompt;

    reviewDialog.show({
      status: payload.status,
      reason: payload.reason,
      originalPrompt: payload.originalPrompt,
      sanitizedPrompt: payload.sanitizedPrompt,
      issues: payload.issues ?? [],
      eci: payload.eci
    });
  }

  /**
   * Allows a safe prompt to continue without review.
   *
   * @param {string} promptText
   * @returns {Promise<void>}
   */
  async function allowSafePromptSend() {
    state.bypassOnce = true;
    state.sendAttemptInFlight = false;
    clearPendingSendState();
    await createReplayAction()();
  }

  /**
   * Reads and logs the current prompt text.
   *
   * @param {HTMLElement} promptTextArea
   */
  function logCurrentPrompt(promptTextArea) {
    const promptText = detector.readPromptText(promptTextArea);
    Logger.info("Prompt Updated");
    Logger.info(`Current Prompt:\n\n${promptText || "(empty)"}`);
  }

  /**
   * Binds prompt input and Enter detection.
   *
   * @param {HTMLElement} promptTextArea
   */
  function bindPromptTextArea(promptTextArea) {
    state.promptListenerController?.abort();
    state.promptListenerController = new AbortController();

    const options = { signal: state.promptListenerController.signal };

    promptTextArea.addEventListener(
      "input",
      () => {
        logCurrentPrompt(promptTextArea);
        scheduleRefresh();
      },
      options
    );

    promptTextArea.addEventListener(
      "keydown",
      (event) => {
        if (!detector.shouldInterceptEnter(event)) {
          return;
        }

        handleSendAttempt(event, "enter");
      },
      { ...options, capture: true }
    );
  }

  /**
   * Binds send-button interception.
   *
   * @param {HTMLElement} sendButton
   */
  function bindSendButton(sendButton) {
    state.sendButtonListenerController?.abort();
    state.sendButtonListenerController = new AbortController();

    const options = { signal: state.sendButtonListenerController.signal, capture: true };
    const handler = (event) => {
      handleSendAttempt(event, "button");
    };

    sendButton.addEventListener("pointerdown", handler, options);
    sendButton.addEventListener("click", handler, options);
  }

  /**
   * Binds document-level interception for Enter and form submit.
   */
  function bindDocumentListeners() {
    state.documentListenerController?.abort();
    state.documentListenerController = new AbortController();

    const options = { signal: state.documentListenerController.signal, capture: true };

    documentRef.addEventListener(
      "keydown",
      (event) => {
        if (!isPromptEventTarget(event.target) || !detector.shouldInterceptEnter(event)) {
          return;
        }

        handleSendAttempt(event, "enter");
      },
      options
    );

    documentRef.addEventListener(
      "submit",
      (event) => {
        if (!state.promptTextArea) {
          return;
        }

        const form = event.target;
        if (!(form instanceof HTMLFormElement) || !form.contains(state.promptTextArea)) {
          return;
        }

        handleSendAttempt(event, "submit");
      },
      options
    );
  }

  /**
   * Marks send button readiness transitions.
   *
   * @param {HTMLElement | null} sendButton
   */
  function updateSendButtonReadyState(sendButton) {
    if (!sendButton) {
      state.sendButtonReadyLogged = false;
      return;
    }

    const isReady = detector.isSendButtonReady(sendButton);

    if (isReady && !state.sendButtonReadyLogged) {
      Logger.info("Send Button Ready");
      state.sendButtonReadyLogged = true;
      return;
    }

    if (!isReady) {
      state.sendButtonReadyLogged = false;
    }
  }

  /**
   * Performs the actual prompt scan and blocks or allows sending.
   *
   * @param {Event} event
   * @param {"button" | "enter" | "submit"} source
   */
  async function handleSendAttempt(event, source) {
    if (state.bypassOnce) {
      state.bypassOnce = false;
      return;
    }

    if (state.sendAttemptInFlight) {
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }

    state.sendAttemptInFlight = true;
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();

    Logger.info(
      source === "enter" ? "Enter Pressed" : source === "submit" ? "Form Submit Intercepted" : "Send Button Clicked"
    );

    const promptText = detector.readPromptText(state.promptTextArea);
    state.pendingOriginalPrompt = promptText;
    Logger.info("Prompt Captured Before Send");
    Logger.info(`Current Prompt:\n\n${promptText || "(empty)"}`);

    if (!promptText.trim()) {
      state.sendAttemptInFlight = false;
      return;
    }

    try {
      const result = await scanClient.scanPrompt(promptText);
      const normalizedStatus = String(result.status ?? "SAFE").toUpperCase();
      const sanitizedPrompt =
        typeof result.sanitizedPrompt === "string" ? result.sanitizedPrompt : promptText;

      if (normalizedStatus === "SAFE") {
        Logger.info("Decision: SAFE");
        await allowSafePromptSend();
        return;
      }

      if (normalizedStatus === "SANITIZE" || normalizedStatus === "BLOCK") {
        Logger.info(`Decision: ${normalizedStatus}`);
        if (result.reason) {
          Logger.info(result.reason);
        }
        showReviewDialog({
          status: normalizedStatus,
          reason: result.reason,
          originalPrompt: promptText,
          sanitizedPrompt,
          issues: resolveScanIssues({
            issues: result.issues,
            reason: result.reason,
            originalPrompt: promptText,
            sanitizedPrompt
          }),
          eci: result.eci
        });
        return;
      }

      Logger.warn(`Unexpected API status: ${normalizedStatus}. Allowing send.`);
      await allowSafePromptSend();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      Logger.warn(`Scan Failed, allowing send: ${message}`);
      await allowSafePromptSend();
    }
  }

  /**
   * Re-scans the DOM for prompt and send controls.
   */
  function refresh() {
    const promptTextArea = detector.findPromptTextArea(documentRef);

    if (promptTextArea && promptTextArea !== state.promptTextArea) {
      state.promptTextArea = promptTextArea;
      Logger.info("Prompt Text Area Found");
      bindPromptTextArea(promptTextArea);
      logCurrentPrompt(promptTextArea);
    }

    const sendButton = detector.findSendButton(documentRef, state.promptTextArea);

    if (sendButton && sendButton !== state.sendButton) {
      state.sendButton = sendButton;
      state.sendButtonReadyLogged = false;
      Logger.info("Send Button Found");
      bindSendButton(sendButton);
    }

    updateSendButtonReadyState(sendButton);
  }

  /**
   * Schedules refresh on the next animation frame.
   */
  function scheduleRefresh() {
    if (state.refreshScheduled) {
      return;
    }

    state.refreshScheduled = true;

    windowRef.requestAnimationFrame(() => {
      state.refreshScheduled = false;
      refresh();
    });
  }

  /**
   * Starts the DOM observer.
   */
  function start() {
    Logger.info("Waiting for Prompt Area...");
    bindDocumentListeners();
    refresh();

    state.observer = new MutationObserver(() => {
      scheduleRefresh();
    });

    state.observer.observe(documentRef.documentElement || documentRef.body, PROMPT_OBSERVER_CONFIG);
  }

  function stop() {
    state.observer?.disconnect();
    clearBoundListeners();
    reviewDialog.hide();
    clearPendingSendState();
  }

  return {
    start,
    stop,
    cancelPendingSend,
    sendSanitizedPrompt,
    sendOriginalPrompt
  };
}

