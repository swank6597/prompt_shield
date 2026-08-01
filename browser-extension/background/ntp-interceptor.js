/**
 * NTP & AI Mode Navigation Interceptor
 *
 * Detects when a search query originating from Chrome's New Tab Page or from
 * the Google homepage AI Mode button navigates to Google Search. Scans the
 * query for sensitive data and redirects to an interstitial review page if
 * the scan result is SANITIZE or BLOCK.
 *
 * Covers two scenarios:
 * 1. NTP/address bar: user types query and presses Enter → navigates to google.com/search
 * 2. AI Mode button: user types on google.com homepage, clicks "AI Mode" → navigates to google.com/search?udm=50&source=hp
 *
 * @module background/ntp-interceptor
 */

/**
 * Checks whether a URL object points to a Google Search page.
 *
 * @param {URL} url - The parsed URL to check.
 * @returns {boolean} True if the URL is a Google Search URL.
 */
export function isGoogleSearchUrl(url) {
  const hostname = url.hostname;
  return (
    (hostname === "www.google.com" ||
      hostname === "google.com" ||
      hostname.endsWith(".google.com")) &&
    url.pathname.startsWith("/search")
  );
}

/**
 * Starts the NTP & AI Mode navigation interceptor in the background service worker.
 *
 * @param {{
 *   Logger: { info: Function, warn: Function },
 *   scanPrompt: (prompt: string, endpoint?: string) => Promise<object>
 * }} params - Dependencies injected from the background service worker.
 */
export function startNtpInterceptor({ Logger, scanPrompt }) {
  // --- Periodic cleanup of stale bypass flags (older than 30 seconds) ---
  const BYPASS_FLAG_TTL_MS = 30_000;
  const CLEANUP_ALARM_NAME = "prompt_guardian_bypass_cleanup";

  async function cleanupStaleBypassFlags() {
    const allData = await chrome.storage.session.get(null);
    const now = Date.now();
    const keysToRemove = [];

    for (const [key, value] of Object.entries(allData)) {
      if (!key.startsWith("bypass_tab_") && !key.startsWith("bypass_") && !key.startsWith("scan_")) continue;
      const timestamp = value?.timestamp;
      if (typeof timestamp === "number" && now - timestamp > BYPASS_FLAG_TTL_MS) {
        keysToRemove.push(key);
      }
    }

    if (keysToRemove.length > 0) {
      await chrome.storage.session.remove(keysToRemove);
      Logger.info(`Cleaned up ${keysToRemove.length} stale bypass flag(s)`);
    }
  }

  // Set up an alarm to run cleanup every 30 seconds
  chrome.alarms.create(CLEANUP_ALARM_NAME, { periodInMinutes: 0.5 });
  chrome.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name === CLEANUP_ALARM_NAME) {
      cleanupStaleBypassFlags();
    }
  });

  // --- Navigation interception ---
  chrome.webNavigation.onCommitted.addListener(
    async (details) => {
      // Only main frame navigations
      if (details.frameId !== 0) return;

      // Parse the destination URL
      let url;
      try {
        url = new URL(details.url);
      } catch {
        return;
      }

      // Must be a Google Search URL
      if (!isGoogleSearchUrl(url)) return;

      // Must have a query
      const query = url.searchParams.get("q");
      if (!query || !query.trim()) return;

      // Log all Google Search navigations for debugging
      Logger.info(`[NTP Interceptor] Navigation detected: transitionType="${details.transitionType}", qualifiers=${JSON.stringify(details.transitionQualifiers || [])}, udm=${url.searchParams.get("udm") || "none"}, source=${url.searchParams.get("source") || "none"}`);

      // Determine if we should intercept this navigation:
      //
      // 1. From NTP/address bar: transitionType is "typed" or "generated",
      //    or qualifiers include "from_address_bar"
      const isFromAddressBar =
        details.transitionType === "typed" ||
        details.transitionType === "generated" ||
        (details.transitionQualifiers || []).includes("from_address_bar");

      // 2. AI Mode from Google homepage: URL contains udm=50 with source=hp
      //    (this is the exact pattern when user clicks "AI Mode" button on google.com)
      const isAiModeFromHomepage =
        url.searchParams.get("udm") === "50" &&
        url.searchParams.get("source") === "hp";

      // If it's neither source, skip — let the content script handle it
      if (!isFromAddressBar && !isAiModeFromHomepage) {
        Logger.info("[NTP Interceptor] Skipping — not from address bar or AI Mode homepage");
        return;
      }

      // Check bypass flag (user already approved this query via interstitial)
      const bypassKey = `bypass_${details.tabId}`;
      const bypassData = await chrome.storage.session.get(bypassKey);
      if (bypassData[bypassKey]) {
        await chrome.storage.session.remove(bypassKey);
        Logger.info("NTP/AI Mode bypass: query pre-approved, allowing through");
        return;
      }

      // Scan the query
      const source = isAiModeFromHomepage ? "AI Mode" : "NTP";
      Logger.info(`${source} Search Intercepted: "${query}"`);
      const result = await scanPrompt(query);

      if (String(result.status).toUpperCase() === "SAFE") {
        Logger.info(`${source} Search: SAFE, allowing navigation`);
        // Set bypass flag so the content script on the Google Search page
        // does not re-intercept this already-scanned query.
        await chrome.storage.session.set({
          [`bypass_tab_${details.tabId}`]: { timestamp: Date.now() },
        });
        return;
      }

      // Store scan results for the interstitial page
      await chrome.storage.session.set({
        [`scan_${details.tabId}`]: {
          originalUrl: details.url,
          query,
          result,
          timestamp: Date.now(),
        },
      });

      // Redirect to interstitial review page
      Logger.info(
        `${source} Search: ${result.status}, redirecting to interstitial`
      );
      chrome.tabs.update(details.tabId, {
        url: chrome.runtime.getURL(
          `interstitial/review.html?tabId=${details.tabId}`
        ),
      });
    },
    {
      url: [{ hostContains: "google", pathPrefix: "/search" }],
    }
  );
}
