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
 *   scanClient: { scanPrompt: (prompt: string) => Promise<{ status: string, reason?: string, raw?: unknown }> },
 *   warningDialog: { show: (reason: string) => void, hide: () => void },
 *   documentRef: Document,
 *   windowRef: Window
 * }} params
 * @returns {{ start: () => void, stop: () => void, allowBlockedSend: () => boolean }}
 */
export function createPromptGuardianObserver({ Logger, detector, scanClient, warningDialog, documentRef, windowRef }) {
  const state = {
    observer: null,
    refreshScheduled: false,
    promptTextArea: null,
    sendButton: null,
    promptListenerController: null,
    sendButtonListenerController: null,
    sendAttemptInFlight: false,
    bypassOnce: false,
    pendingReplay: null,
    sendButtonReadyLogged: false
  };

  /**
   * Removes all listener controllers.
   */
  function clearBoundListeners() {
    state.promptListenerController?.abort();
    state.sendButtonListenerController?.abort();
    state.promptListenerController = null;
    state.sendButtonListenerController = null;
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
   * Creates the replay action used after SAFE or Send Anyway.
   *
   * @returns {() => void}
   */
  function createReplayAction() {
    return () => {
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
      options
    );
  }

  /**
   * Binds send-button click interception.
   *
   * @param {HTMLElement} sendButton
   */
  function bindSendButton(sendButton) {
    state.sendButtonListenerController?.abort();
    state.sendButtonListenerController = new AbortController();

    sendButton.addEventListener(
      "click",
      (event) => {
        handleSendAttempt(event, "button");
      },
      { signal: state.sendButtonListenerController.signal, capture: true }
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
   * @param {"button" | "enter"} source
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

    Logger.info(source === "enter" ? "Enter Pressed" : "Send Button Clicked");

    const promptText = detector.readPromptText(state.promptTextArea);
    Logger.info("Prompt Captured Before Send");
    Logger.info(`Current Prompt:\n\n${promptText || "(empty)"}`);

    try {
      const result = await scanClient.scanPrompt(promptText);
      const normalizedStatus = String(result.status ?? "SAFE").toUpperCase();

      if (normalizedStatus === "SAFE") {
        Logger.info("Milestone 5 Decision: SAFE");
        state.pendingReplay = createReplayAction();
        state.bypassOnce = true;
        state.sendAttemptInFlight = false;
        state.pendingReplay?.();
        state.pendingReplay = null;
        return;
      }

      if (normalizedStatus === "BLOCK") {
        Logger.warn("Milestone 5 Decision: BLOCK");
        state.pendingReplay = createReplayAction();
        warningDialog.show(result.reason || "Sensitive Data Detected");
        state.sendAttemptInFlight = false;
        return;
      }

      Logger.warn(`Unexpected API status: ${normalizedStatus}. Allowing send.`);
      state.pendingReplay = createReplayAction();
      state.bypassOnce = true;
      state.sendAttemptInFlight = false;
      state.pendingReplay?.();
      state.pendingReplay = null;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      Logger.warn(`Scan Failed, allowing send: ${message}`);
      state.pendingReplay = createReplayAction();
      state.bypassOnce = true;
      state.sendAttemptInFlight = false;
      state.pendingReplay?.();
      state.pendingReplay = null;
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
   * Allows the blocked prompt to continue once.
   *
   * @returns {boolean}
   */
  function allowBlockedSend() {
    if (!state.pendingReplay) {
      return false;
    }

    warningDialog.hide();
    state.bypassOnce = true;
    state.sendAttemptInFlight = false;

    const replay = state.pendingReplay;
    state.pendingReplay = null;
    replay();
    return true;
  }

  /**
   * Starts the DOM observer.
   */
  function start() {
    Logger.info("Waiting for Prompt Area...");
    refresh();

    state.observer = new MutationObserver(() => {
      scheduleRefresh();
    });

    state.observer.observe(documentRef.documentElement || documentRef.body, PROMPT_OBSERVER_CONFIG);
  }

  /**
   * Stops the DOM observer and disconnects listeners.
   */
  function stop() {
    state.observer?.disconnect();
    clearBoundListeners();
    warningDialog.hide();
  }

  return {
    start,
    stop,
    allowBlockedSend
  };
}

