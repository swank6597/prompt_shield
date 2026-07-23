import { Logger } from "../utils/logger.js";
import { normalizeIssueList } from "../utils/scan-utils.js";

const DEFAULT_SCAN_ENDPOINT = "http://localhost:8081/api/scan";

/**
 * Normalizes a scan response into the shape used by Milestone 5.
 *
 * @param {unknown} response
 * @returns {{ status: string, reason?: string, raw?: unknown }}
 */
function normalizeScanResponse(response) {
  if (response && typeof response === "object") {
    const typedResponse = /** @type {{ status?: unknown, reason?: unknown, sanitizedPrompt?: unknown, issues?: unknown }} */ (
      response
    );
    const status = String(typedResponse.status ?? "SAFE").toUpperCase();
    const reason = typeof typedResponse.reason === "string" ? typedResponse.reason : undefined;
    const sanitizedPrompt =
      typeof typedResponse.sanitizedPrompt === "string" ? typedResponse.sanitizedPrompt : undefined;
    const issues = normalizeIssueList(typedResponse.issues);
    return { status, reason, sanitizedPrompt, issues, raw: response };
  }

  return { status: "SAFE", issues: [], raw: response };
}

/**
 * Handles prompt scanning requests from the content script.
 *
 * @param {string} prompt
 * @param {string} [endpoint]
 * @returns {Promise<{ status: string, reason?: string, sanitizedPrompt?: string, issues?: Array<{ entityType: string, value: string, score?: number }>, raw?: unknown }>}
 */
async function scanPrompt(prompt, endpoint = DEFAULT_SCAN_ENDPOINT) {
  try {
    Logger.info("API Request Sent");

    const response = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ prompt })
    });

    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json")
      ? await response.json()
      : { status: response.ok ? "SAFE" : "BLOCK", reason: await response.text() };

    const normalized = normalizeScanResponse(payload);
    Logger.info("API Response");
    Logger.info(JSON.stringify(normalized.raw ?? payload, null, 2));
    return normalized;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    Logger.warn(`API Request Failed: ${message}`);
    return {
      status: "SAFE",
      reason: "API unavailable, allowing prompt to continue",
      issues: [],
      raw: { error: message }
    };
  }
}

if (chrome?.runtime?.onMessage?.addListener) {
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (!message || message.type !== "PROMPT_GUARDIAN_SCAN_PROMPT") {
      return false;
    }

    void (async () => {
      const result = await scanPrompt(String(message.prompt ?? ""), String(message.endpoint ?? DEFAULT_SCAN_ENDPOINT));
      sendResponse(result);
    })();

    return true;
  });
}

Logger.info("Background Service Worker Loaded");

