/**
 * Gemini Nano / Chrome Built-in AI Monitor
 *
 * Best-effort monitoring of outbound requests to Google's generative AI endpoints
 * (Gemini Nano, Help me write, summarize, etc.). Extracts text from request bodies
 * where possible, scans for PII/sensitive data, and warns the user via Chrome
 * notifications if issues are detected.
 *
 * This monitor does NOT block requests — it observes and warns only.
 * Opaque/binary/encrypted payloads are skipped gracefully.
 *
 * @module background/gemini-monitor
 */

/**
 * Extracts text content from a webRequest requestBody object.
 *
 * Attempts to decode raw bytes as UTF-8, parse as JSON, and extract text from
 * known Gemini API payload structures:
 * - `contents[].parts[].text` (standard Gemini API format)
 * - `prompt` (alternative format)
 * - `text` (alternative format)
 * - `input` (alternative format)
 *
 * Returns null for opaque, binary, or unrecognized payloads (graceful skip).
 *
 * @param {chrome.webRequest.WebRequestBody | undefined} requestBody - The request body from webRequest event.
 * @returns {string | null} Extracted text content, or null if not extractable.
 */
export function extractTextFromRequestBody(requestBody) {
  if (!requestBody?.raw?.length) return null;

  try {
    const decoder = new TextDecoder();
    const rawData = requestBody.raw
      .map((part) => decoder.decode(part.bytes))
      .join("");

    const parsed = JSON.parse(rawData);

    // Gemini API format: contents[].parts[].text
    if (parsed.contents && Array.isArray(parsed.contents)) {
      const text = parsed.contents
        .flatMap((c) => c.parts || [])
        .filter((p) => p.text)
        .map((p) => p.text)
        .join("\n");
      return text || null;
    }

    // Alternative payload formats
    if (typeof parsed.prompt === "string") return parsed.prompt;
    if (typeof parsed.text === "string") return parsed.text;
    if (typeof parsed.input === "string") return parsed.input;

    return null;
  } catch {
    // Opaque/binary/encrypted payload — skip gracefully
    return null;
  }
}

/**
 * Starts the Gemini Nano / Chrome Built-in AI monitor in the background service worker.
 *
 * Listens for outbound requests to known Google generative AI endpoints, extracts
 * text from request bodies, scans for sensitive data, and creates Chrome notifications
 * if issues are detected. Does NOT block any requests.
 *
 * @param {{
 *   Logger: { info: Function, warn: Function },
 *   scanPrompt: (prompt: string, endpoint?: string) => Promise<{ status: string, reason?: string }>
 * }} params - Dependencies injected from the background service worker.
 */
export function startGeminiMonitor({ Logger, scanPrompt }) {
  chrome.webRequest.onBeforeRequest.addListener(
    (details) => {
      // Fire-and-forget async processing — we never block the request
      void (async () => {
        Logger.info(`[Gemini Monitor] Request intercepted: ${details.url}`);

        if (!details.requestBody?.raw) {
          Logger.info("[Gemini Monitor] No raw body available, skipping");
          return;
        }

        const bodyText = extractTextFromRequestBody(details.requestBody);
        if (!bodyText) {
          Logger.info("[Gemini Monitor] Could not extract text from body, skipping");
          return;
        }

        Logger.info(`[Gemini Monitor] Extracted text (${bodyText.length} chars), scanning...`);

        const result = await scanPrompt(bodyText);

        Logger.info(`[Gemini Monitor] Scan result: ${result.status}`);

        if (result.status !== "SAFE") {
          chrome.notifications.create(`gemini-warn-${Date.now()}`, {
            type: "basic",
            iconUrl: chrome.runtime.getURL("icons/icon128.png"),
            title: "PromptShield \u2014 Sensitive Data Detected",
            message:
              result.reason ||
              "PII or enterprise data found in a Chrome AI request.",
            priority: 2,
          });

          Logger.warn(
            `[Gemini Monitor] WARNING: Sensitive data detected in Chrome AI request (${result.status}): ${result.reason || "no reason provided"}`
          );
        }
      })();
    },
    {
      urls: [
        "*://generativelanguage.googleapis.com/*",
        "*://alkali-pa.googleapis.com/*",
        "*://content-push.googleapis.com/upload/*",
      ],
    },
    ["requestBody"]
  );

  Logger.info("[Gemini Monitor] Started — monitoring Chrome AI endpoints");
}
