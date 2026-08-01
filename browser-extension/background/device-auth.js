import { Logger } from "../utils/logger.js";

// Same backend host /api/scan itself defaults to (background.js's
// DEFAULT_SCAN_ENDPOINT) - not a separate config, since there is no
// dynamic backend-URL setting today.
const DEFAULT_ENROLL_ENDPOINT = "http://localhost:8081/devices/enroll";
const STORAGE_KEY = "promptShieldApiKey";
const DEVICE_LABEL = "PromptShield Extension";

// De-dupes concurrent enrollment attempts (e.g. two scans firing before
// the first enrollment finishes) so a fresh install doesn't create
// multiple device rows for one browser profile.
let _enrollPromise = null;

/**
 * @returns {Promise<string | null>}
 */
async function readStoredApiKey() {
  try {
    const result = await chrome.storage.local.get(STORAGE_KEY);
    const value = result?.[STORAGE_KEY];
    return typeof value === "string" && value.trim() ? value.trim() : null;
  } catch {
    return null;
  }
}

async function storeApiKey(apiKey) {
  await chrome.storage.local.set({ [STORAGE_KEY]: apiKey });
}

/**
 * Clears the stored API key so the next call to getOrCreateApiKey()
 * enrolls a fresh device. Used when the backend reports the current key
 * as invalid/revoked (see background.js's 401 handling) - self-heals
 * without needing the user to do anything.
 */
export async function clearStoredApiKey() {
  try {
    await chrome.storage.local.remove(STORAGE_KEY);
  } catch {
    // Nothing to do - worst case, the next scan tries the same bad key
    // once more and clears it again.
  }
}

async function enrollDevice(endpoint) {
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label: DEVICE_LABEL }),
  });
  if (!response.ok) {
    throw new Error(`Device enrollment failed: ${response.status}`);
  }
  const data = await response.json();
  if (typeof data.apiKey !== "string" || !data.apiKey) {
    throw new Error("Device enrollment response missing apiKey");
  }
  return data.apiKey;
}

/**
 * Returns a usable API key for /api/scan's X-API-Key header, enrolling a
 * new device (POST /devices/enroll) once and caching the result in
 * chrome.storage.local if none is stored yet. Concurrent callers share
 * one in-flight enrollment instead of each enrolling their own device.
 *
 * Throws if enrollment fails (backend unreachable, etc.) - background.js's
 * scanPrompt() already wraps its whole body in a try/catch that fails
 * open to SAFE, matching this extension's existing "never block typing
 * over a backend outage" behavior, so no separate handling is needed here.
 *
 * @param {string} [endpoint]
 * @returns {Promise<string>}
 */
export async function getOrCreateApiKey(endpoint = DEFAULT_ENROLL_ENDPOINT) {
  const stored = await readStoredApiKey();
  if (stored) {
    return stored;
  }

  if (!_enrollPromise) {
    _enrollPromise = (async () => {
      Logger.info("No device API key stored - enrolling a new device");
      const apiKey = await enrollDevice(endpoint);
      await storeApiKey(apiKey);
      Logger.info("Device enrolled and API key stored");
      return apiKey;
    })().finally(() => {
      _enrollPromise = null;
    });
  }
  return _enrollPromise;
}
