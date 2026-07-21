const DEFAULT_SCAN_ENDPOINT = "http://localhost:8080/api/scan";

/**
 * Creates a bridge for sending prompt scans to the background service worker.
 *
 * @param {{
 *   Logger: { info: (message: string) => void, warn: (message: string) => void, error: (message: string) => void },
 *   endpoint?: string
 * }} params
 * @returns {{ scanPrompt: (prompt: string) => Promise<{ status: string, reason?: string, raw?: unknown }> }}
 */
export function createPromptScanClient({ Logger, endpoint = DEFAULT_SCAN_ENDPOINT }) {
  /**
   * Sends the prompt to the background worker for scanning.
   *
   * @param {string} prompt
   * @returns {Promise<{ status: string, reason?: string, raw?: unknown }>}
   */
  async function scanPrompt(prompt) {
    const response = await chrome.runtime.sendMessage({
      type: "PROMPT_GUARDIAN_SCAN_PROMPT",
      prompt,
      endpoint
    });

    if (!response) {
      Logger.warn("API Response Missing, defaulting to SAFE");
      return {
        status: "SAFE",
        reason: "No API response returned",
        raw: null
      };
    }

    Logger.info("API Response");
    Logger.info(JSON.stringify(response.raw ?? response, null, 2));

    return {
      status: String(response.status ?? "SAFE").toUpperCase(),
      reason: typeof response.reason === "string" ? response.reason : undefined,
      raw: response.raw ?? response
    };
  }

  return {
    scanPrompt
  };
}
