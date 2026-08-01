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
 *   pathExclusions?: string[],
 *   promptHints: string[],
 *   sendHints: string[],
 *   apiEndpoint?: string,
 *   identitySelectors?: string[],
 *   identityHints?: string[]
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
 *   identitySelectors: string[],
 *   identityHints: string[],
 *   matchUrl: (url: string) => boolean
 * }}
 */
export function createSiteDefinition(site) {
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
    // No verified selector for a site (e.g. DeepSeek, Copilot) means an
    // empty array here, which content/identity.js treats as "always fall
    // back to the manually-configured popup value" - see its docstring.
    identitySelectors: site.identitySelectors ?? [],
    identityHints: site.identityHints ?? [],
    matchUrl(url) {
      try {
        const parsedUrl = new URL(url);
        const hostMatches = matchesHostname(parsedUrl.hostname, site.hosts);
        const pathExcluded = site.pathExclusions?.some(
          (prefix) => parsedUrl.pathname.startsWith(prefix)
        );
        if (pathExcluded) return false;
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
    sendHints: ["send", "submit"],
    // No identitySelectors: tried this (see git history) and
    // "nav [aria-label*='account' i]" matched a broad sidebar container
    // rather than a small profile chip, so textContent picked up
    // unrelated nested text (a conversation title, a pin/unpin menu
    // action) - a generic hint word happened to appear inside that text
    // and it scored as a confident match, landing a wrong value in the
    // audit log. That's worse than falling back to the manual popup
    // value, so this is manual-only now, same as DeepSeek/Copilot below.
    // Only reintroduce with a selector confirmed (via live DOM
    // inspection) to target the profile button specifically, not a
    // container that also holds conversation history.
    identityHints: ["chatgpt account"]
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
    sendHints: ["send", "submit", "ask"],
    // Google's account chip aria-label is fairly consistent across Google
    // products: "Google Account: Name (email@domain.com)" - identity.js
    // extracts just the email from whichever of these matches.
    identitySelectors: [
      "a[aria-label*='Google Account' i]",
      "[aria-label*='Google Account' i]"
    ],
    identityHints: ["google account"]
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
    sendHints: ["send", "submit"],
    // Best-effort only, same caveat as ChatGPT above - Claude's sidebar
    // account area typically shows a display name without opening a menu.
    identitySelectors: [
      "button[aria-label*='account' i]",
      "[data-testid*='profile' i]"
    ],
    identityHints: ["claude account"]
  }),
  createSiteDefinition({
    id: "deepseek",
    label: "DeepSeek",
    hosts: ["chat.deepseek.com", "chat.deepseek.ai"],
    // No verified identitySelectors yet - falls back to the manually
    // configured popup value (see identity.js). Add real selectors here
    // once someone has inspected DeepSeek's live account-menu DOM.
    promptHints: ["deepseek", "ask", "message", "prompt"],
    sendHints: ["send", "submit", "ask"]
  }),
  createSiteDefinition({
    id: "copilot",
    label: "Microsoft Copilot",
    hosts: ["copilot.microsoft.com", "copilot.cloud.microsoft", "www.bing.com"],
    pathPrefixes: ["/chat"],
    // No verified identitySelectors yet - same as DeepSeek above, falls
    // back to the manually configured popup value.
    promptHints: ["copilot", "ask", "message", "prompt"],
    sendHints: ["send", "submit", "ask"]
  }),
  createSiteDefinition({
    id: "google-search-ai",
    label: "Google Search AI",
    hosts: ["www.google.com", "google.com"],
    pathPrefixes: ["/search"],
    promptSelectors: [
      // Google's primary search textarea class (stable across redesigns)
      "textarea.gLFyf",
      // AI Mode conversational input — multiple variants
      "textarea[aria-label*='Search' i]",
      "textarea[aria-label*='Ask' i]",
      "textarea[aria-label*='follow' i]",
      "textarea[jsname]",
      "div[contenteditable='true'][aria-label*='Search' i]",
      "div[contenteditable='true'][aria-label*='Ask' i]",
      "div[contenteditable='true'][role='textbox']",
      "div[contenteditable='true'][data-placeholder]",
      // Scoped search container patterns
      "[role='search'] textarea",
      "[role='search'] input[type='text']",
      // AI Overviews follow-up input
      "input[aria-label*='Ask a follow up' i]",
      "input[aria-label*='follow up' i]",
      "input[aria-label*='Ask' i]",
      // Standard search refinement
      "textarea[name='q']",
      "input[name='q']",
      // Google AI Mode uses combobox role for the input
      "[role='combobox'] textarea",
      "[role='combobox'] input",
      // Catch-all for any textarea on the page
      "textarea",
      // Generic fallbacks
      ...COMMON_PROMPT_SELECTORS
    ],
    sendSelectors: [
      "button[aria-label*='Search' i]",
      "button[aria-label*='Google Search' i]",
      "button[aria-label*='Send' i]",
      "button[aria-label*='Ask' i]",
      "button[aria-label*='Submit' i]",
      // Google uses jsname attributes on interactive elements
      "[role='search'] button[jsname]",
      "[role='search'] button",
      "form[action='/search'] button[type='submit']",
      "button[type='submit']",
      // SVG send icon buttons (Google often uses these)
      "button:has(svg)",
      ...COMMON_SEND_SELECTORS
    ],
    promptScopeSelectors: [
      "form[action='/search']",
      "[role='search']",
      "[role='combobox']",
      ...COMMON_SCOPE_SELECTORS
    ],
    sendScopeSelectors: [
      "form[action='/search']",
      "[role='search']",
      "[role='combobox']",
      ...COMMON_SCOPE_SELECTORS
    ],
    promptHints: ["search", "ask", "follow up", "query", "ai mode", "gLFyf", "search-input", "搜索"],
    sendHints: ["search", "send", "submit", "ask", "google search"]
  }),
  createSiteDefinition({
    id: "google-homepage",
    label: "Google Homepage",
    hosts: ["www.google.com", "google.com"],
    pathExclusions: ["/search", "/maps", "/mail", "/drive", "/calendar", "/docs"],
    promptSelectors: [
      "textarea.gLFyf",
      "textarea[name='q']",
      "input[name='q']",
      "textarea[aria-label*='Search' i]",
      "[role='search'] textarea",
      "[role='combobox'] textarea",
      ...COMMON_PROMPT_SELECTORS
    ],
    sendSelectors: [
      "input[name='btnK']",
      "input[name='btnI']",
      "button[aria-label*='Google Search' i]",
      // AI Mode button on Google homepage — this triggers navigation to /search?udm=50
      "button[aria-label*='AI' i]",
      "a[aria-label*='AI Mode' i]",
      "a[href*='udm=50']",
      "[data-ved] button[jsname]",
      "[role='search'] button[jsname]",
      "button[type='submit']",
      ...COMMON_SEND_SELECTORS
    ],
    promptScopeSelectors: [
      "form[action='/search']",
      "[role='search']",
      "[role='combobox']",
      ...COMMON_SCOPE_SELECTORS
    ],
    sendScopeSelectors: [
      "form[action='/search']",
      "[role='search']",
      ...COMMON_SCOPE_SELECTORS
    ],
    promptHints: ["search", "google", "query", "gLFyf", "search-input"],
    sendHints: ["search", "submit", "feeling lucky", "google search"]
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
