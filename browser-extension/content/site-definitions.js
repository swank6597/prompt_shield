const COMMON_PROMPT_SELECTORS = [
  "textarea",
  "[contenteditable='true']",
  "[role='textbox']",
  "input[type='text']",
  "input[type='search']"
];

const COMMON_SEND_SELECTORS = [
  "button[type='submit']",
  "button[aria-label*='send' i]",
  "button[aria-label*='submit' i]",
  "button[aria-label*='ask' i]",
  "button[title*='send' i]",
  "button[data-testid*='send' i]",
  "[role='button'][aria-label*='send' i]",
  "[role='button'][aria-label*='submit' i]",
  "[role='button'][title*='send' i]",
  "[role='button'][data-testid*='send' i]"
];

const COMMON_SCOPE_SELECTORS = [
  "form",
  "main",
  "[role='form']",
  "[data-testid*='composer' i]",
  "[data-testid*='prompt' i]"
];

const DEFAULT_API_ENDPOINT = "http://localhost:8081/api/scan";

/**
 * Returns whether the hostname matches an expected host or subdomain.
 *
 * @param {string} hostname
 * @param {string[]} expectedHosts
 * @returns {boolean}
 */
function matchesHostname(hostname, expectedHosts) {
  return expectedHosts.some((expectedHost) => {
    return hostname === expectedHost || hostname.endsWith(`.${expectedHost}`);
  });
}

/**
 * Creates a site definition entry.
 *
 * @param {{
 *   id: string,
 *   label: string,
 *   hosts: string[],
 *   pathPrefixes?: string[],
 *   promptHints: string[],
 *   sendHints: string[],
 *   apiEndpoint?: string
 * }} site
 * @returns {{
 *   id: string,
 *   label: string,
 *   promptSelectors: string[],
 *   sendSelectors: string[],
 *   promptScopeSelectors: string[],
 *   sendScopeSelectors: string[],
 *   promptHints: string[],
 *   sendHints: string[],
 *   apiEndpoint: string,
 *   matchUrl: (url: string) => boolean
 * }}
 */
function createSiteDefinition(site) {
  return {
    id: site.id,
    label: site.label,
    promptSelectors: site.promptSelectors ?? [...COMMON_PROMPT_SELECTORS],
    sendSelectors: site.sendSelectors ?? [...COMMON_SEND_SELECTORS],
    promptScopeSelectors: site.promptScopeSelectors ?? [...COMMON_SCOPE_SELECTORS],
    sendScopeSelectors: site.sendScopeSelectors ?? [...COMMON_SCOPE_SELECTORS],
    promptHints: [...site.promptHints],
    sendHints: [...site.sendHints],
    apiEndpoint: site.apiEndpoint ?? DEFAULT_API_ENDPOINT,
    matchUrl(url) {
      try {
        const parsedUrl = new URL(url);
        const hostMatches = matchesHostname(parsedUrl.hostname, site.hosts);
        const pathMatches = !site.pathPrefixes?.length
          ? true
          : site.pathPrefixes.some((prefix) => parsedUrl.pathname.startsWith(prefix));
        return hostMatches && pathMatches;
      } catch {
        return false;
      }
    }
  };
}

export const SITE_DEFINITIONS = [
  createSiteDefinition({
    id: "chatgpt",
    label: "ChatGPT",
    hosts: ["chatgpt.com", "chat.openai.com"],
    promptSelectors: [
      "#prompt-textarea",
      "div#prompt-textarea[contenteditable='true']",
      "textarea#prompt-textarea",
      "textarea[data-id='root']",
      "div.ProseMirror[contenteditable='true']",
      ...COMMON_PROMPT_SELECTORS
    ],
    sendSelectors: [
      "[data-testid='send-button']",
      "#composer-submit-button",
      "button[aria-label='Send prompt']",
      "button[aria-label='Send message']",
      ...COMMON_SEND_SELECTORS
    ],
    promptHints: ["message", "prompt", "chatgpt", "ask"],
    sendHints: ["send", "submit"]
  }),
  createSiteDefinition({
    id: "gemini",
    label: "Gemini",
    hosts: ["gemini.google.com"],
    promptSelectors: [
      "div.ql-editor[contenteditable='true']",
      "rich-textarea div[contenteditable='true']",
      ...COMMON_PROMPT_SELECTORS
    ],
    sendSelectors: [
      "button[aria-label*='Send' i]",
      "button.send-button",
      ...COMMON_SEND_SELECTORS
    ],
    promptHints: ["gemini", "ask", "message", "prompt"],
    sendHints: ["send", "submit", "ask"]
  }),
  createSiteDefinition({
    id: "claude",
    label: "Claude",
    hosts: ["claude.ai"],
    promptSelectors: [
      "div[contenteditable='true'][enterkeyhint='send']",
      "fieldset div[contenteditable='true']",
      ...COMMON_PROMPT_SELECTORS
    ],
    sendSelectors: [
      "button[aria-label*='Send' i]",
      "button[data-testid*='send' i]",
      ...COMMON_SEND_SELECTORS
    ],
    promptHints: ["claude", "ask", "message", "prompt"],
    sendHints: ["send", "submit"]
  }),
  createSiteDefinition({
    id: "deepseek",
    label: "DeepSeek",
    hosts: ["chat.deepseek.com", "chat.deepseek.ai"],
    promptHints: ["deepseek", "ask", "message", "prompt"],
    sendHints: ["send", "submit", "ask"]
  }),
  createSiteDefinition({
    id: "copilot",
    label: "Microsoft Copilot",
    hosts: ["copilot.microsoft.com", "copilot.cloud.microsoft", "www.bing.com"],
    pathPrefixes: ["/chat"],
    promptHints: ["copilot", "ask", "message", "prompt"],
    sendHints: ["send", "submit", "ask"]
  })
];

/**
 * Finds the active site definition for the current page.
 *
 * @param {string} url
 * @returns {ReturnType<typeof createSiteDefinition> | null}
 */
export function findSiteDefinition(url) {
  return SITE_DEFINITIONS.find((site) => site.matchUrl(url)) || null;
}
