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
  const { createWarningDialog } = modalModule;
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
  const warningDialog = createWarningDialog({
    onCancel() {
      Logger.info("Warning Dialog Closed");
    },
    onSendAnyway() {
      Logger.info("Send Anyway Clicked");
      observer?.allowBlockedSend();
    }
  });

  observer = createPromptGuardianObserver({
    Logger,
    detector,
    scanClient,
    warningDialog,
    documentRef: document,
    windowRef: window
  });

  observer.start();
})();
