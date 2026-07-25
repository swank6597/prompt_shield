/**
 * Best-effort account identity resolution for the audit log's "username"
 * field. Two layers, in order:
 *
 * 1. Auto-detect: read whatever account name/email is already visible in
 *    the page's DOM (aria-label, title, text content) - never simulates
 *    clicks to open an account menu, since that's a much bigger can of
 *    worms than reading what's already rendered.
 * 2. Manual fallback: a value the user enters once in the extension popup,
 *    saved via chrome.storage.local. Used whenever (1) finds nothing - a
 *    site with no identitySelectors configured (see site-definitions.js)
 *    always falls straight through to this.
 *
 * Deliberately asymmetric per site: shipping a guessed, unverified selector
 * risks a WRONG auto-detected value silently landing in a compliance audit
 * log, which is worse than a clean fallback to the manual value. Only
 * sites with an actually-verified selector get real auto-detection.
 */

import { isVisibleElement, collectCandidates } from "./detector.js";

const EMAIL_PATTERN = /[\w.+-]+@[\w-]+\.[\w.-]+/;

const DEFAULT_IDENTITY_HINTS = ["account", "profile", "signed in"];

// Minimum score for a detected candidate to be trusted over falling back
// to the manual value - see scoreIdentityCandidate().
const MIN_IDENTITY_SCORE = 1;

const STORAGE_KEY = "promptGuardianUsername";

/**
 * Scores an identity candidate and extracts its best display value.
 * Email-shaped text is preferred over a bare name/label when both are
 * present in the same element (e.g. Google's account chip typically reads
 * "Google Account: Name (email@domain.com)" - the email is what we want,
 * not the whole label).
 *
 * @param {HTMLElement} element
 * @param {string[]} hints
 * @returns {{ score: number, value: string | null }}
 */
function scoreIdentityCandidate(element, hints) {
  const attributeText = [
    element.getAttribute("aria-label"),
    element.getAttribute("title"),
    element.textContent
  ]
    .filter(Boolean)
    .join(" ")
    .replace(/\s+/g, " ")
    .trim();

  if (!attributeText) {
    return { score: 0, value: null };
  }

  const emailMatch = attributeText.match(EMAIL_PATTERN);
  let score = 0;

  if (emailMatch) {
    score += 5;
  }

  const lowerText = attributeText.toLowerCase();
  for (const hint of hints) {
    if (lowerText.includes(hint.toLowerCase())) {
      score += 2;
    }
  }

  if (isVisibleElement(element)) {
    score += 1;
  }

  return {
    score,
    value: emailMatch ? emailMatch[0] : attributeText
  };
}

/**
 * Best-effort, read-only detection of the signed-in account name/email
 * already visible on the page. Returns null if the site has no verified
 * `identitySelectors`, or nothing found clears the minimum score - both
 * cases mean "fall back to the manually-configured value."
 *
 * @param {Document | Element | ShadowRoot} root
 * @param {{ identitySelectors?: string[], identityHints?: string[] }} site
 * @returns {string | null}
 */
export function detectAccountIdentity(root, site) {
  const selectors = site.identitySelectors;
  if (!selectors || selectors.length === 0) {
    return null;
  }

  const hints = [...DEFAULT_IDENTITY_HINTS, ...(site.identityHints ?? [])];
  const candidates = collectCandidates(root, selectors);

  let best = null;
  for (const candidate of candidates) {
    const scored = scoreIdentityCandidate(candidate, hints);
    if (scored.value && (!best || scored.score > best.score)) {
      best = scored;
    }
  }

  return best && best.score >= MIN_IDENTITY_SCORE ? best.value : null;
}

/**
 * Reads the manually-configured fallback username from chrome.storage.local.
 * Never throws - storage access failures resolve to null, same as "not set".
 *
 * @returns {Promise<string | null>}
 */
export async function getStoredUsername() {
  try {
    const result = await chrome.storage.local.get(STORAGE_KEY);
    const value = result?.[STORAGE_KEY];
    return typeof value === "string" && value.trim() ? value.trim() : null;
  } catch {
    return null;
  }
}

/**
 * Saves the manually-configured fallback username to chrome.storage.local.
 * Used by the popup's settings form.
 *
 * @param {string} username
 * @returns {Promise<void>}
 */
export async function setStoredUsername(username) {
  await chrome.storage.local.set({ [STORAGE_KEY]: username.trim() });
}

/**
 * Resolves the best available identity for the audit log: DOM
 * auto-detection first, manual popup-configured fallback second.
 *
 * @param {Document | Element | ShadowRoot} root
 * @param {{ identitySelectors?: string[], identityHints?: string[] }} site
 * @returns {Promise<string | null>}
 */
export async function resolveIdentity(root, site) {
  const detected = detectAccountIdentity(root, site);
  if (detected) {
    return detected;
  }

  return getStoredUsername();
}
