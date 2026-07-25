const DEFAULT_SCAN_ENDPOINT = "http://localhost:8081/api/scan";

import { normalizeIssueList } from "../utils/scan-utils.js";

/**
 * Creates a bridge for sending prompt scans to the background service worker.
 *
 * @param {{
 *   Logger: { info: (message: string) => void, warn: (message: string) => void, error: (message: string) => void },
 *   endpoint?: string,
 *   username?: string | null,
 *   platform?: string | null
 * }} params
 * @returns {{ scanPrompt: (prompt: string) => Promise<{ status: string, reason?: string, sanitizedPrompt?: string, issues?: Array<{ entityType: string, value: string, score?: number }>, eci?: import("./modal.js").EciResult, raw?: unknown }> }}
 */
export function createPromptScanClient({ Logger, endpoint = DEFAULT_SCAN_ENDPOINT, username = null, platform = null }) {
  /**
   * Sends the prompt to the background worker for scanning.
   *
   * @param {string} prompt
   * @returns {Promise<{ status: string, reason?: string, sanitizedPrompt?: string, issues?: Array<{ entityType: string, value: string, score?: number }>, eci?: import("./modal.js").EciResult, raw?: unknown }>}
   */
  async function scanPrompt(prompt) {
    const response = await chrome.runtime.sendMessage({
      type: "PROMPT_GUARDIAN_SCAN_PROMPT",
      prompt,
      endpoint,
      username,
      platform
    });

    if (!response) {
      Logger.warn("API Response Missing, defaulting to SAFE");
      return {
        status: "SAFE",
        reason: "No API response returned",
        issues: [],
        raw: null
      };
    }

    Logger.info("API Response");
    Logger.info(JSON.stringify(response, null, 2));

    const originalIssues = response.issues ?? response.raw?.issues;
    const issues = normalizeIssueList(originalIssues);
    const eci = response.eci ?? response.raw?.eci;

    return {
      status: String(response.status ?? "SAFE").toUpperCase(),
      reason: typeof response.reason === "string" ? response.reason : undefined,
      sanitizedPrompt:
        typeof response.sanitizedPrompt === "string" ? response.sanitizedPrompt : undefined,
      issues,
      eci: eci && typeof eci === "object" ? eci : undefined,
      raw: response.raw ?? response
    };
  }

  return {
    scanPrompt
  };
}
