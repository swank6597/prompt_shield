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

  let observer = null;
  const reviewDialog = createReviewDialog({
    onCancel() {
      Logger.info("Review Dialog Cancelled");
      observer?.cancelPendingSend();
    },
    onSendSanitized() {
      Logger.info("Send Sanitized Clicked");
      void observer?.sendSanitizedPrompt();
    },
    onSendOriginal() {
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

  observer.start();
})();
