/**
 * @typedef {{
 *   entityType: string,
 *   value: string,
 *   score?: number
 * }} ScanIssue
 */

/**
 * Finds the original text replaced by a sanitized placeholder.
 *
 * @param {string} originalPrompt
 * @param {string} sanitizedPrompt
 * @param {string} placeholder
 * @returns {string}
 */
function findReplacedValue(originalPrompt, sanitizedPrompt, placeholder) {
  const placeholderIndex = sanitizedPrompt.indexOf(placeholder);
  if (placeholderIndex === -1) {
    return "";
  }

  let start = 0;
  while (
    start < originalPrompt.length &&
    start < sanitizedPrompt.length &&
    originalPrompt[start] === sanitizedPrompt[start]
  ) {
    start += 1;
  }

  let endOriginal = originalPrompt.length;
  let endSanitized = sanitizedPrompt.length;
  while (
    endOriginal > start &&
    endSanitized > start &&
    originalPrompt[endOriginal - 1] === sanitizedPrompt[endSanitized - 1]
  ) {
    endOriginal -= 1;
    endSanitized -= 1;
  }

  if (sanitizedPrompt.slice(start, endSanitized) === placeholder) {
    return originalPrompt.slice(start, endOriginal).trim();
  }

  return "";
}

/**
 * Parses issue types from the API reason string.
 *
 * @param {string | undefined} reason
 * @returns {string[]}
 */
function parseIssueTypesFromReason(reason) {
  if (!reason) {
    return [];
  }

  const match = reason.match(/Detected \d+ sensitive item\(s\):\s*(.+)$/i);
  if (!match) {
    return [];
  }

  return match[1]
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

/**
 * Normalizes raw scan issue objects from the API or background worker.
 *
 * @param {unknown} issues
 * @returns {ScanIssue[]}
 */
export function normalizeIssueList(issues) {
  if (!Array.isArray(issues)) {
    return [];
  }

  return issues
    .map((issue) => {
      if (!issue || typeof issue !== "object") {
        return null;
      }

      const typedIssue = /** @type {{ entityType?: unknown, entity_type?: unknown, value?: unknown, score?: unknown }} */ (
        issue
      );

      const entityType = String(typedIssue.entityType ?? typedIssue.entity_type ?? "UNKNOWN").trim();
      const value = String(typedIssue.value ?? "").trim();

      if (!entityType || entityType === "UNKNOWN") {
        return null;
      }

      return {
        entityType,
        value: value || "(detected in prompt)",
        score: typeof typedIssue.score === "number" ? typedIssue.score : undefined
      };
    })
    .filter(Boolean);
}

/**
 * Builds a user-facing issue list even when the API omits structured issues.
 *
 * @param {{
 *   issues?: unknown,
 *   reason?: string,
 *   originalPrompt?: string,
 *   sanitizedPrompt?: string
 * }} params
 * @returns {ScanIssue[]}
 */
export function resolveScanIssues({ issues, reason, originalPrompt = "", sanitizedPrompt = "" }) {
  const normalizedIssues = normalizeIssueList(issues);
  if (normalizedIssues.length > 0) {
    return normalizedIssues;
  }

  const inferredIssues = [];
  for (const entityType of parseIssueTypesFromReason(reason)) {
    const placeholder = `<${entityType}>`;
    const value =
      findReplacedValue(originalPrompt, sanitizedPrompt, placeholder) || "(detected in prompt)";

    inferredIssues.push({ entityType, value });
  }

  return inferredIssues;
}
