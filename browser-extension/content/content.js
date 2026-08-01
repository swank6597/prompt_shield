(async () => {
  const [
    loggerModule,
    siteDefinitionsModule,
    detectorModule,
    apiClientModule,
    modalModule,
    observerModule,
    identityModule
  ] = await Promise.all([
    import(chrome.runtime.getURL("utils/logger.js")),
    import(chrome.runtime.getURL("content/site-definitions.js")),
    import(chrome.runtime.getURL("content/detector.js")),
    import(chrome.runtime.getURL("content/api-client.js")),
    import(chrome.runtime.getURL("content/modal.js")),
    import(chrome.runtime.getURL("content/observer.js")),
    import(chrome.runtime.getURL("content/identity.js"))
  ]);

  const { Logger } = loggerModule;
  const { findSiteDefinition } = siteDefinitionsModule;
  const { createPromptShieldDetector } = detectorModule;
  const { createPromptScanClient } = apiClientModule;
  const { createReviewDialog } = modalModule;
  const { createPromptShieldObserver } = observerModule;
  const { resolveIdentity } = identityModule;

  Logger.info("Extension Loaded");

  const site = findSiteDefinition(window.location.href);

  if (!site) {
    return;
  }

  Logger.info(`${site.label} Detected`);

  const detector = createPromptShieldDetector(site);
  const scanClient = createPromptScanClient({
    Logger,
    endpoint: site.apiEndpoint,
    username: null,
    platform: site.label
  });

  // Resolved in the background rather than awaited here: DOM
  // auto-detection retries a few times (see content/identity.js) since
  // some sites - ChatGPT included - render their profile UI client-side,
  // after this script has already run. Awaiting that up front would delay
  // send-interception setup below by up to ~2s for no benefit; instead
  // scanClient starts with no username and picks up the resolved value
  // (auto-detected, or the popup's manual fallback) as soon as it's ready.
  // A prompt sent before it resolves is still scanned/blocked correctly -
  // it just logs as "unknown" until then.
  void resolveIdentity(document, site).then((resolvedUsername) => {
    if (resolvedUsername) {
      Logger.info(`Audit identity resolved: ${resolvedUsername}`);
      scanClient.setUsername(resolvedUsername);
    } else {
      Logger.info("Audit identity not resolved (no DOM match, no manual fallback saved) - will log as \"unknown\"");
    }
  });

  // Tracks which interceptor owns the currently-visible review dialog so
  // that button callbacks route to the correct handler.
  // "observer" = the standard send-interception observer
  // "chip"     = the suggestion chip interceptor
  let activeInterceptor = "observer";

  // Chip interceptor callbacks stored per-show(). When the chip interceptor
  // triggers the dialog, it passes its own onCancel/onSendOriginal/onSendSanitized
  // in the payload. We stash them here so the fixed dialog handlers can delegate.
  const chipCallbacks = {
    onCancel: null,
    onSendOriginal: null,
    onSendSanitized: null
  };

  let observer = null;
  const reviewDialog = createReviewDialog({
    onCancel() {
      if (activeInterceptor === "chip" && chipCallbacks.onCancel) {
        chipCallbacks.onCancel();
        return;
      }
      Logger.info("Review Dialog Cancelled");
      observer?.cancelPendingSend();
    },
    onSendSanitized() {
      if (activeInterceptor === "chip" && chipCallbacks.onSendSanitized) {
        chipCallbacks.onSendSanitized();
        return;
      }
      Logger.info("Send Sanitized Clicked");
      void observer?.sendSanitizedPrompt();
    },
    onSendOriginal() {
      if (activeInterceptor === "chip" && chipCallbacks.onSendOriginal) {
        chipCallbacks.onSendOriginal();
        return;
      }
      Logger.info("Send Original Clicked");
      void observer?.sendOriginalPrompt();
    }
  });

  observer = createPromptShieldObserver({
    Logger,
    detector,
    scanClient,
    reviewDialog,
    documentRef: document,
    windowRef: window
  });

  // Anti-double-interception: check if the NTP interceptor already scanned this
  // query and set a bypass flag. If so, skip the first send interception cycle.
  let initialBypass = false;
  if (site.id === "google-search-ai") {
    try {
      const tabIdResponse = await chrome.runtime.sendMessage({ type: "PROMPT_GUARDIAN_GET_TAB_ID" });
      const tabId = tabIdResponse?.tabId;
      if (tabId) {
        const bypassKey = `bypass_tab_${tabId}`;
        const data = await chrome.storage.session.get(bypassKey);
        if (data[bypassKey]) {
          await chrome.storage.session.remove(bypassKey);
          initialBypass = true;
          Logger.info("Bypass flag set: skipping first interception");
        }
      }
    } catch (err) {
      // Non-critical — proceed normally if bypass check fails
      Logger.warn("Bypass check failed, proceeding normally");
    }
  }

  observer.start();

  if (initialBypass) {
    observer.setBypassOnce();
  }

  // Conditionally start the chip interceptor on Google Search AI surfaces.
  // Both the observer (for typed queries) and the chip interceptor (for
  // suggestion chip clicks) run side-by-side to provide full coverage.
  if (site.id === "google-search-ai") {
    const { createChipInterceptor, GOOGLE_CHIP_SELECTORS } = await import(
      chrome.runtime.getURL("content/chip-interceptor.js")
    );

    // Proxy review dialog that sets activeInterceptor = "chip" and stashes
    // the chip interceptor's per-show callbacks before forwarding to the
    // real dialog. When the user clicks a button, the fixed handlers above
    // detect activeInterceptor === "chip" and delegate to chipCallbacks.
    const chipReviewDialog = {
      show(payload) {
        activeInterceptor = "chip";
        chipCallbacks.onCancel = payload.onCancel ?? null;
        chipCallbacks.onSendOriginal = payload.onSendOriginal ?? null;
        chipCallbacks.onSendSanitized = payload.onSendSanitized ?? null;
        reviewDialog.show(payload);
      },
      hide() {
        activeInterceptor = "observer";
        chipCallbacks.onCancel = null;
        chipCallbacks.onSendOriginal = null;
        chipCallbacks.onSendSanitized = null;
        reviewDialog.hide();
      }
    };

    const chipInterceptor = createChipInterceptor({
      Logger,
      scanClient,
      reviewDialog: chipReviewDialog,
      chipSelectors: GOOGLE_CHIP_SELECTORS,
      documentRef: document,
      windowRef: window
    });

    chipInterceptor.start();
    Logger.info("Chip interceptor wired alongside observer for Google Search AI");
  }
})();
