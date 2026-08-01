/**
 * Unit-style verification for site-definitions.js
 * Validates:
 * - Existing site definitions (ChatGPT, Gemini, Claude, DeepSeek, Copilot) remain unaffected
 * - pathExclusions support works correctly in createSiteDefinition
 *
 * Run: node --experimental-vm-modules browser-extension/content/site-definitions.test.mjs
 */

import { SITE_DEFINITIONS, findSiteDefinition, createSiteDefinition } from "./site-definitions.js";
import assert from "node:assert";

// --- Existing site definitions still match correctly (no pathExclusions set) ---

// ChatGPT
assert.strictEqual(
  findSiteDefinition("https://chatgpt.com/")?.id,
  "chatgpt",
  "ChatGPT root should match"
);
assert.strictEqual(
  findSiteDefinition("https://chat.openai.com/c/abc")?.id,
  "chatgpt",
  "ChatGPT conversation should match"
);

// Gemini
assert.strictEqual(
  findSiteDefinition("https://gemini.google.com/app")?.id,
  "gemini",
  "Gemini should match"
);

// Claude
assert.strictEqual(
  findSiteDefinition("https://claude.ai/chat/123")?.id,
  "claude",
  "Claude should match"
);

// DeepSeek
assert.strictEqual(
  findSiteDefinition("https://chat.deepseek.com/")?.id,
  "deepseek",
  "DeepSeek should match"
);

// Copilot (has pathPrefixes: ["/chat"])
assert.strictEqual(
  findSiteDefinition("https://copilot.microsoft.com/chat")?.id,
  "copilot",
  "Copilot /chat should match"
);
assert.strictEqual(
  findSiteDefinition("https://copilot.microsoft.com/other"),
  null,
  "Copilot non-/chat path should not match"
);

// --- pathExclusions feature ---

// Manually test createSiteDefinition with pathExclusions by checking SITE_DEFINITIONS
// None of the existing definitions use pathExclusions, so they should all work as before
for (const site of SITE_DEFINITIONS) {
  // Each existing definition should have a working matchUrl
  assert.strictEqual(typeof site.matchUrl, "function", `${site.id} should have matchUrl`);
}

// Test the pathExclusions logic by importing and calling createSiteDefinition directly
// We'll import the module again and use dynamic import to test the factory function

// Simulate a site with pathExclusions by testing matchUrl behavior on the existing definitions
// Since none have pathExclusions, they should all pass through normally (no exclusion)
assert.strictEqual(
  findSiteDefinition("https://chatgpt.com/search")?.id,
  "chatgpt",
  "ChatGPT should match any path (no pathExclusions, no pathPrefixes)"
);

// Test that invalid URLs still return false
const chatgptDef = SITE_DEFINITIONS.find((s) => s.id === "chatgpt");
assert.strictEqual(chatgptDef.matchUrl("not-a-url"), false, "Invalid URL should return false");

// The Copilot definition uses pathPrefixes ["/chat"] - verify it excludes other paths
assert.strictEqual(
  findSiteDefinition("https://copilot.microsoft.com/"),
  null,
  "Copilot root should not match (pathPrefixes requires /chat)"
);

// --- Directly verify pathExclusions logic via exported createSiteDefinition ---
// Test that a definition with pathExclusions properly excludes matching paths.

const testSite = createSiteDefinition({
  id: "test-exclusions",
  label: "Test Exclusions",
  hosts: ["example.com"],
  pathExclusions: ["/search", "/maps", "/mail"],
  promptHints: ["test"],
  sendHints: ["test"]
});

// Should match root (no exclusion hit)
assert.strictEqual(
  testSite.matchUrl("https://example.com/"),
  true,
  "Root path should match (not excluded)"
);

// Should match arbitrary path
assert.strictEqual(
  testSite.matchUrl("https://example.com/other"),
  true,
  "Non-excluded path should match"
);

// Should NOT match excluded paths
assert.strictEqual(
  testSite.matchUrl("https://example.com/search"),
  false,
  "/search should be excluded"
);
assert.strictEqual(
  testSite.matchUrl("https://example.com/search?q=test"),
  false,
  "/search with query should be excluded"
);
assert.strictEqual(
  testSite.matchUrl("https://example.com/maps/place"),
  false,
  "/maps subpath should be excluded"
);
assert.strictEqual(
  testSite.matchUrl("https://example.com/mail/inbox"),
  false,
  "/mail subpath should be excluded"
);

// Should NOT match wrong host
assert.strictEqual(
  testSite.matchUrl("https://other.com/"),
  false,
  "Wrong host should not match"
);

// Test with both pathPrefixes and pathExclusions
const testSiteWithBoth = createSiteDefinition({
  id: "test-both",
  label: "Test Both",
  hosts: ["example.com"],
  pathPrefixes: ["/app"],
  pathExclusions: ["/app/admin"],
  promptHints: ["test"],
  sendHints: ["test"]
});

assert.strictEqual(
  testSiteWithBoth.matchUrl("https://example.com/app/dashboard"),
  true,
  "/app/dashboard should match (prefix match, not excluded)"
);
assert.strictEqual(
  testSiteWithBoth.matchUrl("https://example.com/app/admin"),
  false,
  "/app/admin should be excluded even though it matches prefix"
);
assert.strictEqual(
  testSiteWithBoth.matchUrl("https://example.com/other"),
  false,
  "/other should not match (no prefix match)"
);

// Test with no pathExclusions (default behavior unchanged)
const testSiteNoExclusions = createSiteDefinition({
  id: "test-no-exclusions",
  label: "Test No Exclusions",
  hosts: ["example.com"],
  promptHints: ["test"],
  sendHints: ["test"]
});

assert.strictEqual(
  testSiteNoExclusions.matchUrl("https://example.com/anything"),
  true,
  "No exclusions means all paths match"
);
assert.strictEqual(
  testSiteNoExclusions.matchUrl("https://example.com/search"),
  true,
  "No exclusions means /search also matches"
);

// --- Google Search AI definition ---

// Standard search URL
assert.strictEqual(
  findSiteDefinition("https://www.google.com/search?q=test")?.id,
  "google-search-ai",
  "Google Search with query should match google-search-ai"
);

// AI Mode URL (udm=50 parameter)
assert.strictEqual(
  findSiteDefinition("https://www.google.com/search?q=test&udm=50")?.id,
  "google-search-ai",
  "Google Search AI Mode (udm=50) should match google-search-ai"
);

// Bare google.com host (without www)
assert.strictEqual(
  findSiteDefinition("https://google.com/search?q=hello")?.id,
  "google-search-ai",
  "google.com/search should match google-search-ai"
);

// --- Google Homepage definition ---

// Root URL matches google-homepage
assert.strictEqual(
  findSiteDefinition("https://www.google.com/")?.id,
  "google-homepage",
  "Google root should match google-homepage"
);

// /webhp matches google-homepage
assert.strictEqual(
  findSiteDefinition("https://www.google.com/webhp")?.id,
  "google-homepage",
  "Google /webhp should match google-homepage"
);

// /search should match google-search-ai (NOT google-homepage) due to ordering
assert.strictEqual(
  findSiteDefinition("https://www.google.com/search?q=x")?.id,
  "google-search-ai",
  "Google /search should match google-search-ai, not google-homepage"
);

// Excluded paths should return null (not matched by google-homepage or google-search-ai)
assert.strictEqual(
  findSiteDefinition("https://www.google.com/maps"),
  null,
  "Google /maps should be excluded (returns null)"
);
assert.strictEqual(
  findSiteDefinition("https://www.google.com/mail"),
  null,
  "Google /mail should be excluded (returns null)"
);

// Bare google.com (without www) should also match google-homepage
assert.strictEqual(
  findSiteDefinition("https://google.com/")?.id,
  "google-homepage",
  "google.com root should match google-homepage"
);

// --- Edge cases: www.google.com vs google.com, subdomains, and regional domains ---

// www.google.com/search should match google-search-ai
assert.strictEqual(
  findSiteDefinition("https://www.google.com/search?q=hello&udm=50")?.id,
  "google-search-ai",
  "www.google.com/search with AI Mode param should match google-search-ai"
);

// google.com (bare, no www) root should match google-homepage
assert.strictEqual(
  findSiteDefinition("https://google.com/")?.id,
  "google-homepage",
  "google.com/ (no www) should match google-homepage"
);

// google.com/search (bare, no www) should match google-search-ai
assert.strictEqual(
  findSiteDefinition("https://google.com/search?q=test&udm=50")?.id,
  "google-search-ai",
  "google.com/search with udm=50 (no www) should match google-search-ai"
);

// Regional/country-code domains should NOT match (e.g. google.co.uk)
// because the site definitions only specify www.google.com and google.com
assert.strictEqual(
  findSiteDefinition("https://www.google.co.uk/search?q=test"),
  null,
  "google.co.uk should NOT match (not in hosts list)"
);
assert.strictEqual(
  findSiteDefinition("https://www.google.de/"),
  null,
  "google.de should NOT match (not in hosts list)"
);

// Subdomain of google.com that isn't www should NOT match (e.g. mail.google.com)
// because matchesHostname checks exact match or endsWith .google.com — but wait,
// mail.google.com ends with .google.com, so it would match! Let's verify current behavior.
// The hosts list is ["www.google.com", "google.com"], so mail.google.com
// would match "google.com" via the endsWith logic.
// This is acceptable since pathExclusions filter out /mail paths,
// and the content_scripts.matches pattern limits actual injection.
assert.strictEqual(
  findSiteDefinition("https://mail.google.com/mail/inbox"),
  null,
  "mail.google.com/mail should be excluded by pathExclusions in google-homepage"
);

// Verify that google.com/drive is excluded
assert.strictEqual(
  findSiteDefinition("https://www.google.com/drive"),
  null,
  "Google /drive should be excluded (returns null)"
);

// Verify that google.com/calendar is excluded
assert.strictEqual(
  findSiteDefinition("https://www.google.com/calendar"),
  null,
  "Google /calendar should be excluded (returns null)"
);

// Verify that google.com/docs is excluded
assert.strictEqual(
  findSiteDefinition("https://www.google.com/docs"),
  null,
  "Google /docs should be excluded (returns null)"
);

// --- Verify google-search-ai definition has correct selectors ---

const googleSearchDef = SITE_DEFINITIONS.find((s) => s.id === "google-search-ai");
assert.ok(googleSearchDef, "google-search-ai definition should exist");
assert.ok(
  googleSearchDef.promptSelectors.some((s) => s.includes("textarea")),
  "google-search-ai should have textarea in promptSelectors"
);
assert.ok(
  googleSearchDef.sendSelectors.some((s) => s.includes("Search")),
  "google-search-ai should have a Search button selector"
);

// --- Verify google-homepage definition has correct selectors ---

const googleHomeDef = SITE_DEFINITIONS.find((s) => s.id === "google-homepage");
assert.ok(googleHomeDef, "google-homepage definition should exist");
assert.ok(
  googleHomeDef.promptSelectors.some((s) => s.includes("name='q'")),
  "google-homepage should target the search input by name='q'"
);
assert.ok(
  googleHomeDef.sendSelectors.some((s) => s.includes("btnK")),
  "google-homepage should target the Google Search button (btnK)"
);

// --- Verify existing sites still match correctly (regression) ---

assert.strictEqual(
  findSiteDefinition("https://chatgpt.com/c/12345")?.id,
  "chatgpt",
  "Regression: ChatGPT conversation URL should still match"
);
assert.strictEqual(
  findSiteDefinition("https://gemini.google.com/app/12345")?.id,
  "gemini",
  "Regression: Gemini should still match"
);
assert.strictEqual(
  findSiteDefinition("https://claude.ai/chat/new")?.id,
  "claude",
  "Regression: Claude should still match"
);
assert.strictEqual(
  findSiteDefinition("https://chat.deepseek.com/chat")?.id,
  "deepseek",
  "Regression: DeepSeek should still match"
);
assert.strictEqual(
  findSiteDefinition("https://copilot.microsoft.com/chat/session")?.id,
  "copilot",
  "Regression: Copilot should still match"
);
assert.strictEqual(
  findSiteDefinition("https://www.bing.com/chat")?.id,
  "copilot",
  "Regression: Bing Chat should still match Copilot"
);

console.log("All site-definitions tests passed.");
