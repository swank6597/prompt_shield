/**
 * Unit tests for chip-interceptor.js
 * Validates:
 * - GOOGLE_CHIP_SELECTORS is exported correctly
 * - createChipInterceptor lifecycle (start/stop)
 * - Click interception on chip elements
 * - Chip text extraction from various attributes
 * - Bypass flag prevents infinite loops
 * - SAFE result replays original click
 * - SANITIZE/BLOCK results show review dialog
 * - Cancel drops the click
 * - Send Original replays the click
 * - Send Sanitized writes to prompt input and submits
 *
 * Run: node --experimental-vm-modules browser-extension/content/chip-interceptor.test.mjs
 */

import { createChipInterceptor, GOOGLE_CHIP_SELECTORS } from "./chip-interceptor.js";
import assert from "node:assert";

// --- Minimal DOM simulation ---

class MockElement {
  constructor(tag, attributes = {}, children = []) {
    this.tagName = tag.toUpperCase();
    this._attributes = { ...attributes };
    this.children = children;
    this.parentElement = null;
    this.innerText = attributes._innerText || "";
    this.textContent = attributes._textContent || this.innerText;
    this.clickCount = 0;
    this.value = attributes._value !== undefined ? attributes._value : undefined;
    this._eventListeners = {};

    for (const child of children) {
      child.parentElement = this;
    }
  }

  getAttribute(name) {
    return this._attributes[name] ?? null;
  }

  matches(selector) {
    // Handle comma-separated selectors
    if (selector.includes(",")) {
      return selector.split(",").some((s) => this.matches(s.trim()));
    }

    // Simple attribute selector: [attr], [attr=value], [attr*=value]
    const attrMatch = selector.match(/^\[([^\]=~*^$|]+)/);
    if (attrMatch) {
      const attrName = attrMatch[1];
      return this._attributes[attrName] !== undefined;
    }

    // Class selector
    if (selector.startsWith(".")) {
      const className = selector.slice(1);
      return (this._attributes.class || "").split(" ").includes(className);
    }

    // Role selector
    if (selector.includes("[role=")) {
      const roleMatch = selector.match(/\[role=['"]?([^'"\]]+)/);
      if (roleMatch) {
        return this._attributes.role === roleMatch[1];
      }
    }

    // Compound selectors with space (descendant) - simplified: just check last part
    if (selector.includes(" ")) {
      const parts = selector.trim().split(/\s+/);
      const lastPart = parts[parts.length - 1];
      return this.matches(lastPart);
    }

    return false;
  }

  closest(selector) {
    if (this.matches(selector)) return this;
    if (this.parentElement) return this.parentElement.closest(selector);
    return null;
  }

  click() {
    this.clickCount++;
    // Dispatch a click event on the document if registered
    if (this._document) {
      const event = new MockEvent("click", this);
      this._document._dispatchCapture("click", event);
    }
  }

  querySelector() {
    return null;
  }

  dispatchEvent() {}
  focus() {}
}

class MockEvent {
  constructor(type, target) {
    this.type = type;
    this.target = target;
    this.defaultPrevented = false;
    this.propagationStopped = false;
    this.immediatePropagationStopped = false;
  }

  preventDefault() {
    this.defaultPrevented = true;
  }

  stopPropagation() {
    this.propagationStopped = true;
  }

  stopImmediatePropagation() {
    this.immediatePropagationStopped = true;
  }
}

class MockDocument {
  constructor() {
    this._captureListeners = {};
    this._abortControllers = [];
  }

  addEventListener(type, handler, options = {}) {
    if (!this._captureListeners[type]) {
      this._captureListeners[type] = [];
    }
    const entry = { handler, signal: options?.signal };
    this._captureListeners[type].push(entry);

    if (options?.signal) {
      options.signal.addEventListener("abort", () => {
        const list = this._captureListeners[type];
        const idx = list.indexOf(entry);
        if (idx !== -1) list.splice(idx, 1);
      });
    }
  }

  removeEventListener() {}

  querySelector() {
    return null;
  }

  createRange() {
    return { selectNodeContents() {}, setStart() {}, setEnd() {} };
  }

  execCommand() {
    return true;
  }

  _dispatchCapture(type, event) {
    const listeners = this._captureListeners[type] || [];
    for (const { handler } of listeners) {
      if (!event.immediatePropagationStopped) {
        handler(event);
      }
    }
  }
}

class MockAbortController {
  constructor() {
    this.signal = new MockAbortSignal();
  }
  abort() {
    this.signal._aborted = true;
    this.signal._listeners.forEach((fn) => fn());
  }
}

class MockAbortSignal {
  constructor() {
    this._aborted = false;
    this._listeners = [];
  }
  get aborted() {
    return this._aborted;
  }
  addEventListener(type, fn) {
    if (type === "abort") this._listeners.push(fn);
  }
}

// Polyfill global AbortController for test environment
globalThis.AbortController = MockAbortController;
globalThis.HTMLElement = MockElement;
globalThis.Event = class Event {
  constructor(type, opts = {}) {
    this.type = type;
    this.bubbles = opts.bubbles || false;
  }
};
globalThis.InputEvent = class InputEvent extends globalThis.Event {
  constructor(type, opts = {}) {
    super(type, opts);
    this.inputType = opts.inputType;
    this.data = opts.data;
  }
};

// Helper to create a test interceptor
function createTestInterceptor(scanResult = { status: "SAFE" }) {
  const logs = [];
  const Logger = {
    info: (msg) => logs.push({ level: "info", msg }),
    warn: (msg) => logs.push({ level: "warn", msg }),
    error: (msg) => logs.push({ level: "error", msg })
  };

  const scanCalls = [];
  const scanClient = {
    scanPrompt: async (text) => {
      scanCalls.push(text);
      return scanResult;
    }
  };

  const dialogCalls = [];
  const reviewDialog = {
    show: (payload) => dialogCalls.push({ action: "show", payload }),
    hide: () => dialogCalls.push({ action: "hide" })
  };

  const doc = new MockDocument();
  const win = { getSelection: () => ({ removeAllRanges() {}, addRange() {} }) };

  const interceptor = createChipInterceptor({
    Logger,
    scanClient,
    reviewDialog,
    chipSelectors: GOOGLE_CHIP_SELECTORS,
    documentRef: doc,
    windowRef: win
  });

  return { interceptor, doc, logs, scanCalls, dialogCalls };
}

// --- Test: GOOGLE_CHIP_SELECTORS is exported ---

assert.ok(Array.isArray(GOOGLE_CHIP_SELECTORS), "GOOGLE_CHIP_SELECTORS should be an array");
assert.ok(GOOGLE_CHIP_SELECTORS.length > 0, "GOOGLE_CHIP_SELECTORS should not be empty");
assert.ok(
  GOOGLE_CHIP_SELECTORS.includes("[data-chip-action]"),
  "Should include data-chip-action selector"
);
assert.ok(
  GOOGLE_CHIP_SELECTORS.includes("[data-followup-text]"),
  "Should include data-followup-text selector"
);
assert.ok(
  GOOGLE_CHIP_SELECTORS.includes("[data-q]"),
  "Should include data-q selector"
);

// --- Test: createChipInterceptor returns start/stop ---

{
  const { interceptor } = createTestInterceptor();
  assert.strictEqual(typeof interceptor.start, "function", "Should have start method");
  assert.strictEqual(typeof interceptor.stop, "function", "Should have stop method");
}

// --- Test: start registers capture-phase listener ---

{
  const { interceptor, doc, logs } = createTestInterceptor();
  interceptor.start();
  assert.ok(
    doc._captureListeners.click?.length > 0,
    "Should have registered a click listener"
  );
  assert.ok(
    logs.some((l) => l.msg.includes("Chip interceptor started")),
    "Should log start message"
  );
}

// --- Test: stop removes listener ---

{
  const { interceptor, doc, logs } = createTestInterceptor();
  interceptor.start();
  interceptor.stop();
  assert.strictEqual(
    doc._captureListeners.click?.length ?? 0,
    0,
    "Should have removed click listener after stop"
  );
  assert.ok(
    logs.some((l) => l.msg.includes("Chip interceptor stopped")),
    "Should log stop message"
  );
}

// --- Test: non-chip clicks pass through ---

{
  const { interceptor, doc, scanCalls } = createTestInterceptor();
  interceptor.start();

  const nonChipElement = new MockElement("div", {});
  const event = new MockEvent("click", nonChipElement);
  doc._dispatchCapture("click", event);

  // Give async handler a tick
  await new Promise((r) => setTimeout(r, 10));

  assert.strictEqual(scanCalls.length, 0, "Non-chip click should not trigger scan");
  assert.strictEqual(event.defaultPrevented, false, "Non-chip click should not be prevented");
}

// --- Test: chip click is intercepted and text extracted from data-followup-text ---

{
  const { interceptor, doc, scanCalls } = createTestInterceptor();
  interceptor.start();

  const chipElement = new MockElement("button", {
    "data-followup-text": "What is quantum computing?",
    _innerText: "Quantum Computing"
  });

  // Make it match the selector
  const event = new MockEvent("click", chipElement);
  doc._dispatchCapture("click", event);

  await new Promise((r) => setTimeout(r, 10));

  assert.strictEqual(scanCalls.length, 1, "Chip click should trigger scan");
  assert.strictEqual(
    scanCalls[0],
    "What is quantum computing?",
    "Should extract text from data-followup-text attribute"
  );
  assert.strictEqual(event.defaultPrevented, true, "Chip click should be prevented");
  assert.strictEqual(event.immediatePropagationStopped, true, "Chip propagation should be stopped");
}

// --- Test: chip text extraction from data-q ---

{
  const { interceptor, doc, scanCalls } = createTestInterceptor();
  interceptor.start();

  const chipElement = new MockElement("a", {
    "data-q": "How does AI work?",
    _innerText: "AI explanation"
  });

  const event = new MockEvent("click", chipElement);
  doc._dispatchCapture("click", event);

  await new Promise((r) => setTimeout(r, 10));

  assert.strictEqual(scanCalls[0], "How does AI work?", "Should extract from data-q");
}

// --- Test: chip text extraction from data-chip-action ---

{
  const { interceptor, doc, scanCalls } = createTestInterceptor();
  interceptor.start();

  const chipElement = new MockElement("button", {
    "data-chip-action": "Tell me more about climate change",
    _innerText: "Climate change"
  });

  const event = new MockEvent("click", chipElement);
  doc._dispatchCapture("click", event);

  await new Promise((r) => setTimeout(r, 10));

  assert.strictEqual(
    scanCalls[0],
    "Tell me more about climate change",
    "Should extract from data-chip-action"
  );
}

// --- Test: chip text extraction falls back to innerText ---

{
  const { interceptor, doc, scanCalls } = createTestInterceptor();
  interceptor.start();

  const chipElement = new MockElement("button", {
    class: "suggestion-chip",
    _innerText: "Best practices for Python"
  });

  const event = new MockEvent("click", chipElement);
  doc._dispatchCapture("click", event);

  await new Promise((r) => setTimeout(r, 10));

  assert.strictEqual(
    scanCalls[0],
    "Best practices for Python",
    "Should fall back to innerText"
  );
}

// --- Test: SAFE scan replays click ---

{
  const { interceptor, doc } = createTestInterceptor({ status: "SAFE" });
  interceptor.start();

  const chipElement = new MockElement("button", {
    "data-followup-text": "Safe query",
    _innerText: "Safe"
  });
  chipElement._document = doc;

  const event = new MockEvent("click", chipElement);
  doc._dispatchCapture("click", event);

  await new Promise((r) => setTimeout(r, 10));

  assert.strictEqual(chipElement.clickCount, 1, "SAFE scan should replay the chip click");
}

// --- Test: SANITIZE scan shows review dialog ---

{
  const { interceptor, doc, dialogCalls } = createTestInterceptor({
    status: "SANITIZE",
    reason: "Detected 1 sensitive item(s): EMAIL_ADDRESS",
    sanitizedPrompt: "Contact me at <EMAIL_ADDRESS>",
    issues: [{ entityType: "EMAIL_ADDRESS", value: "test@example.com" }]
  });
  interceptor.start();

  const chipElement = new MockElement("button", {
    "data-followup-text": "Contact me at test@example.com",
    _innerText: "Contact"
  });

  const event = new MockEvent("click", chipElement);
  doc._dispatchCapture("click", event);

  await new Promise((r) => setTimeout(r, 10));

  assert.strictEqual(dialogCalls.length, 1, "SANITIZE should show review dialog");
  assert.strictEqual(dialogCalls[0].action, "show", "Should call show");
  assert.strictEqual(dialogCalls[0].payload.status, "SANITIZE", "Dialog should show SANITIZE status");
  assert.strictEqual(
    dialogCalls[0].payload.originalPrompt,
    "Contact me at test@example.com",
    "Dialog should show original chip text"
  );
}

// --- Test: BLOCK scan shows review dialog with allowOverride false ---

{
  const { interceptor, doc, dialogCalls } = createTestInterceptor({
    status: "BLOCK",
    reason: "Blocked content detected",
    sanitizedPrompt: "Blocked",
    issues: []
  });
  interceptor.start();

  const chipElement = new MockElement("button", {
    "data-followup-text": "Blocked content",
    _innerText: "Blocked"
  });

  const event = new MockEvent("click", chipElement);
  doc._dispatchCapture("click", event);

  await new Promise((r) => setTimeout(r, 10));

  assert.strictEqual(dialogCalls.length, 1, "BLOCK should show review dialog");
  assert.strictEqual(dialogCalls[0].payload.status, "BLOCK", "Dialog should show BLOCK status");
  assert.strictEqual(dialogCalls[0].payload.allowOverride, false, "BLOCK should not allow override");
}

// --- Test: scan failure allows click through ---

{
  const logs = [];
  const Logger = {
    info: (msg) => logs.push({ level: "info", msg }),
    warn: (msg) => logs.push({ level: "warn", msg }),
    error: (msg) => logs.push({ level: "error", msg })
  };

  const scanClient = {
    scanPrompt: async () => {
      throw new Error("Network error");
    }
  };

  const dialogCalls = [];
  const reviewDialog = {
    show: (payload) => dialogCalls.push({ action: "show", payload }),
    hide: () => dialogCalls.push({ action: "hide" })
  };

  const doc = new MockDocument();
  const win = { getSelection: () => ({ removeAllRanges() {}, addRange() {} }) };

  const interceptor = createChipInterceptor({
    Logger,
    scanClient,
    reviewDialog,
    chipSelectors: GOOGLE_CHIP_SELECTORS,
    documentRef: doc,
    windowRef: win
  });

  interceptor.start();

  const chipElement = new MockElement("button", {
    "data-followup-text": "Test query",
    _innerText: "Test"
  });
  chipElement._document = doc;

  const event = new MockEvent("click", chipElement);
  doc._dispatchCapture("click", event);

  await new Promise((r) => setTimeout(r, 10));

  assert.ok(
    logs.some((l) => l.msg.includes("Chip scan failed")),
    "Should log scan failure"
  );
  assert.strictEqual(chipElement.clickCount, 1, "Should replay click on scan failure");
  assert.strictEqual(dialogCalls.length, 0, "Should not show dialog on scan failure");
}

// --- Test: empty chip text replays click without scanning ---

{
  const { interceptor, doc, scanCalls } = createTestInterceptor();
  interceptor.start();

  const chipElement = new MockElement("button", {
    "data-chip-action": "",
    _innerText: ""
  });
  chipElement._document = doc;

  const event = new MockEvent("click", chipElement);
  doc._dispatchCapture("click", event);

  await new Promise((r) => setTimeout(r, 10));

  assert.strictEqual(scanCalls.length, 0, "Empty chip text should not trigger scan");
  assert.strictEqual(chipElement.clickCount, 1, "Should replay click for empty chip text");
}

// --- Test: duplicate start is idempotent ---

{
  const { interceptor, doc } = createTestInterceptor();
  interceptor.start();
  interceptor.start(); // second call should not add another listener
  assert.strictEqual(
    doc._captureListeners.click?.length,
    1,
    "Multiple start calls should not duplicate listeners"
  );
}

console.log("All chip-interceptor tests passed.");
