(async () => {
  const [
    loggerModule,
    siteDefinitionsModule,
    detectorModule,
    apiClientModule,
    modalModule,
    observerModule
  ] = await Promise.all([
    import(chrome.runtime.getURL("utils/logger.js")),
    import(chrome.runtime.getURL("content/site-definitions.js")),
    import(chrome.runtime.getURL("content/detector.js")),
    import(chrome.runtime.getURL("content/api-client.js")),
    import(chrome.runtime.getURL("content/modal.js")),
    import(chrome.runtime.getURL("content/observer.js"))
  ]);

  const { Logger } = loggerModule;
  const { findSiteDefinition } = siteDefinitionsModule;
  const { createPromptGuardianDetector } = detectorModule;
  const { createPromptScanClient } = apiClientModule;
  const { createReviewDialog } = modalModule;
  const { createPromptGuardianObserver } = observerModule;

  Logger.info("Extension Loaded");

  const site = findSiteDefinition(window.location.href);

  if (!site) {
    return;
  }

  Logger.info(`${site.label} Detected`);

  const detector = createPromptGuardianDetector(site);
  const scanClient = createPromptScanClient({
    Logger,
    endpoint: site.apiEndpoint
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
