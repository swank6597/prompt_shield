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
  const { createPromptGuardianDetector } = detectorModule;
  const { createPromptScanClient } = apiClientModule;
  const { createReviewDialog } = modalModule;
  const { createPromptGuardianObserver } = observerModule;
  const { resolveIdentity } = identityModule;

  Logger.info("Extension Loaded");

  const site = findSiteDefinition(window.location.href);

  if (!site) {
    return;
  }

  Logger.info(`${site.label} Detected`);

  // Resolved once at load: DOM auto-detection first, manual popup-
  // configured fallback second - see content/identity.js.
  const username = await resolveIdentity(document, site);

  const detector = createPromptGuardianDetector(site);
  const scanClient = createPromptScanClient({
    Logger,
    endpoint: site.apiEndpoint,
    username,
    platform: site.label
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

  observer = createPromptGuardianObserver({
    Logger,
    detector,
    scanClient,
    reviewDialog,
    documentRef: document,
    windowRef: window
  });

  observer.start();
})();
