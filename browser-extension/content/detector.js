/**
 * Shared DOM detection helpers for prompt composers and send buttons.
 */

const IGNORED_TEXT = /\u200B/g;

/**
 * Returns true when the value is a browser HTMLElement.
 *
 * @param {unknown} value
 * @returns {value is HTMLElement}
 */
function isHTMLElement(value) {
  return typeof HTMLElement !== "undefined" && value instanceof HTMLElement;
}

/**
 * Returns true when the element is visible enough to interact with.
 *
 * @param {Element} element
 * @returns {boolean}
 */
function isVisibleElement(element) {
  if (!isHTMLElement(element)) {
    return false;
  }

  const rect = element.getBoundingClientRect();
  const style = window.getComputedStyle(element);

  return (
    rect.width > 0 &&
    rect.height > 0 &&
    style.visibility !== "hidden" &&
    style.display !== "none" &&
    style.opacity !== "0"
  );
}

/**
 * Queries elements deeply across open shadow roots.
 *
 * @param {Document | Element | ShadowRoot} root
 * @param {string} selector
 * @returns {Element[]}
 */
function querySelectorAllDeep(root, selector) {
  const results = [];
  const queue = [root];
  const visited = new Set();

  while (queue.length > 0) {
    const currentRoot = queue.shift();
    if (!currentRoot || visited.has(currentRoot) || typeof currentRoot.querySelectorAll !== "function") {
      continue;
    }

    visited.add(currentRoot);
    results.push(...Array.from(currentRoot.querySelectorAll(selector)));

    for (const element of Array.from(currentRoot.querySelectorAll("*"))) {
      if (element.shadowRoot && !visited.has(element.shadowRoot)) {
        queue.push(element.shadowRoot);
      }
    }
  }

  return results;
}

/**
 * Collects element candidates from the given selectors.
 *
 * @param {Document | Element | ShadowRoot} root
 * @param {string[]} selectors
 * @returns {HTMLElement[]}
 */
function collectCandidates(root, selectors) {
  const collected = new Set();

  for (const selector of selectors) {
    const directMatches = Array.from(root.querySelectorAll(selector));
    for (const element of directMatches) {
      if (isHTMLElement(element)) {
        collected.add(element);
      }
    }
  }

  if (collected.size > 0) {
    return Array.from(collected);
  }

  for (const selector of selectors) {
    const deepMatches = querySelectorAllDeep(root, selector);
    for (const element of deepMatches) {
      if (isHTMLElement(element)) {
        collected.add(element);
      }
    }
  }

  return Array.from(collected);
}

/**
 * Scores a prompt candidate.
 *
 * @param {HTMLElement} element
 * @param {string[]} hints
 * @returns {number}
 */
function scorePromptCandidate(element, hints) {
  const attributeText = [
    element.getAttribute("aria-label"),
    element.getAttribute("placeholder"),
    element.getAttribute("name"),
    element.getAttribute("id"),
    element.getAttribute("data-placeholder"),
    element.textContent
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();

  let score = 0;

  if (element.matches("textarea")) {
    score += 5;
  }

  if (element.matches("[contenteditable='true']")) {
    score += 4;
  }

  if (element.matches("[role='textbox']")) {
    score += 3;
  }

  if (element.matches("input[type='text'], input[type='search']")) {
    score += 2;
  }

  if (element.closest("form")) {
    score += 2;
  }

  if (isVisibleElement(element)) {
    score += 2;
  }

  for (const hint of hints) {
    if (attributeText.includes(hint.toLowerCase())) {
      score += 2;
    }
  }

  return score;
}

/**
 * Scores a send-button candidate.
 *
 * @param {HTMLElement} element
 * @param {string[]} hints
 * @returns {number}
 */
function scoreSendCandidate(element, hints) {
  const attributeText = [
    element.getAttribute("aria-label"),
    element.getAttribute("title"),
    element.textContent,
    element.getAttribute("data-testid")
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();

  let score = 0;

  if (element.matches("button[type='submit']")) {
    score += 5;
  }

  if (element.matches("[role='button']")) {
    score += 2;
  }

  if (element.closest("form")) {
    score += 2;
  }

  if (isVisibleElement(element)) {
    score += 2;
  }

  for (const hint of hints) {
    if (attributeText.includes(hint.toLowerCase())) {
      score += 3;
    }
  }

  return score;
}

/**
 * Creates a detector for the active AI chat site.
 *
 * @param {{
 *   label: string,
 *   promptSelectors: string[],
 *   sendSelectors: string[],
 *   promptScopeSelectors: string[],
 *   sendScopeSelectors: string[],
 *   promptHints: string[],
 *   sendHints: string[]
 * }} site
 * @returns {{
 *   findPromptTextArea: (root: Document | Element | ShadowRoot) => HTMLElement | null,
 *   findSendButton: (root: Document | Element | ShadowRoot, promptTextArea?: HTMLElement | null) => HTMLElement | null,
 *   isSendButtonReady: (element: HTMLElement | null) => boolean,
 *   readPromptText: (element: HTMLElement | null) => string,
 *   shouldInterceptEnter: (event: KeyboardEvent) => boolean,
 *   isVisibleElement: (element: Element) => boolean,
 *   getSiteLabel: () => string
 * }}
 */
export function createPromptGuardianDetector(site) {
  /**
   * Finds the most likely prompt element.
   *
   * @param {Document | Element | ShadowRoot} root
   * @returns {HTMLElement | null}
   */
  function findPromptTextArea(root) {
    const candidates = collectCandidates(root, site.promptSelectors).filter(isVisibleElement);

    if (candidates.length === 0) {
      return null;
    }

    candidates.sort((left, right) => scorePromptCandidate(right, site.promptHints) - scorePromptCandidate(left, site.promptHints));
    return candidates[0] || null;
  }

  /**
   * Resolves the best search root for the send button.
   *
   * @param {HTMLElement | null} promptTextArea
   * @param {Document | Element | ShadowRoot} root
   * @returns {Document | Element | ShadowRoot}
   */
  function resolveSendSearchRoot(promptTextArea, root) {
    if (isHTMLElement(promptTextArea)) {
      const scopeSelector = site.sendScopeSelectors.join(",");
      const matchedScope = scopeSelector ? promptTextArea.closest(scopeSelector) : null;
      if (matchedScope) {
        return matchedScope;
      }

      const form = promptTextArea.closest("form");
      if (form) {
        return form;
      }
    }

    return root;
  }

  /**
   * Finds the send button for the current composer.
   *
   * @param {Document | Element | ShadowRoot} root
   * @param {HTMLElement | null} promptTextArea
   * @returns {HTMLElement | null}
   */
  function findSendButton(root, promptTextArea = null) {
    const searchRoot = resolveSendSearchRoot(promptTextArea, root);
    const candidates = collectCandidates(searchRoot, site.sendSelectors).filter(isVisibleElement);

    if (candidates.length === 0 && searchRoot !== root) {
      return findSendButton(root, null);
    }

    if (candidates.length === 0) {
      return null;
    }

    candidates.sort((left, right) => scoreSendCandidate(right, site.sendHints) - scoreSendCandidate(left, site.sendHints));
    return candidates[0] || null;
  }

  /**
   * Determines whether a send button is ready to activate.
   *
   * @param {HTMLElement | null} element
   * @returns {boolean}
   */
  function isSendButtonReady(element) {
    if (!isHTMLElement(element)) {
      return false;
    }

    const ariaDisabled = element.getAttribute("aria-disabled");
    const dataDisabled = element.getAttribute("data-disabled");

    return !element.hasAttribute("disabled") && ariaDisabled !== "true" && dataDisabled !== "true";
  }

  /**
   * Reads the prompt text from either a textarea or a contenteditable element.
   *
   * @param {HTMLElement | null} element
   * @returns {string}
   */
  function readPromptText(element) {
    if (!isHTMLElement(element)) {
      return "";
    }

    if ("value" in element) {
      return String(element.value ?? "");
    }

    return String(element.innerText ?? element.textContent ?? "")
      .replace(IGNORED_TEXT, "")
      .trim();
  }

  /**
   * Detects whether the key event should be treated as a send attempt.
   *
   * @param {KeyboardEvent} event
   * @returns {boolean}
   */
  function shouldInterceptEnter(event) {
    return event.key === "Enter" && !event.shiftKey && !event.altKey && !event.ctrlKey && !event.metaKey && !event.isComposing;
  }

  return {
    findPromptTextArea,
    findSendButton,
    isSendButtonReady,
    readPromptText,
    shouldInterceptEnter,
    isVisibleElement,
    getSiteLabel: () => site.label
  };
}
