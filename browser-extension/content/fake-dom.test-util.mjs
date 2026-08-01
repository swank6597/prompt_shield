/**
 * Minimal DOM stand-in for the node-based tests of the two review surfaces.
 *
 * Follows the same hand-rolled-mock approach as chip-interceptor.test.mjs, but
 * is shared because both review surfaces (content/modal.js shadow DOM and
 * interstitial/review.js document) need the same three things:
 *
 *  - real element identity, so a test can hold a node reference across renders
 *  - real tree membership, so getElementById stops finding a detached node
 *  - real listener dispatch, so click() runs whatever the code registered
 *
 * It is deliberately not a general HTML parser. It handles the markup these two
 * surfaces actually use: no void-element quirks beyond the list below, no
 * unquoted attribute values, no `<` inside style or comment text.
 *
 * Not shipped: web_accessible_resources globs `content/*.js`, which does not
 * match `.mjs`.
 */

const VOID_TAGS = new Set([
  "area",
  "base",
  "br",
  "col",
  "embed",
  "hr",
  "img",
  "input",
  "link",
  "meta",
  "param",
  "source",
  "track",
  "wbr"
]);

const TAG_PATTERN = /<(\/)?([a-zA-Z][\w-]*)((?:"[^"]*"|'[^']*'|[^>"'])*?)(\/)?>/g;
const ATTR_PATTERN = /([a-zA-Z_:][-\w:.]*)(?:\s*=\s*"([^"]*)")?/g;

/**
 * Parses an attribute string into a plain object.
 *
 * @param {string} raw
 * @returns {Record<string, string>}
 */
function parseAttributes(raw) {
  const attributes = {};
  if (!raw || !raw.trim()) {
    return attributes;
  }

  ATTR_PATTERN.lastIndex = 0;
  let match;
  while ((match = ATTR_PATTERN.exec(raw)) !== null) {
    attributes[match[1]] = match[2] ?? "";
  }

  return attributes;
}

export class MockElement {
  /**
   * @param {string} tagName
   * @param {Record<string, string>} [attributes]
   */
  constructor(tagName, attributes = {}) {
    this.tagName = String(tagName).toUpperCase();
    this.attributes = { ...attributes };
    this.children = [];
    this.parentNode = null;
    this.style = {};
    this.textContent = "";
    this.hidden = "hidden" in this.attributes;
    this.disabled = false;
    this.listeners = {};
    this.isRoot = false;
    this._innerHTML = "";
  }

  get id() {
    return this.attributes.id ?? "";
  }

  set id(value) {
    this.attributes.id = String(value);
  }

  get innerHTML() {
    return this._innerHTML;
  }

  /**
   * Assigning innerHTML replaces the subtree, as it does in a real DOM.
   *
   * @param {string} html
   */
  set innerHTML(html) {
    for (const child of this.children) {
      child.parentNode = null;
    }
    this.children = [];
    this._innerHTML = String(html);
    parseHtmlInto(this, this._innerHTML);
  }

  getAttribute(name) {
    return this.attributes[name] ?? null;
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }

  removeAttribute(name) {
    delete this.attributes[name];
  }

  appendChild(child) {
    child.parentNode?.removeChild(child);
    child.parentNode = this;
    this.children.push(child);
    return child;
  }

  removeChild(child) {
    const index = this.children.indexOf(child);
    if (index !== -1) {
      this.children.splice(index, 1);
    }
    child.parentNode = null;
    return child;
  }

  remove() {
    this.parentNode?.removeChild(this);
  }

  /**
   * True when the node is still reachable from a root (document / shadow root).
   *
   * @returns {boolean}
   */
  get isConnected() {
    let node = this;
    while (node.parentNode) {
      node = node.parentNode;
    }
    return node.isRoot === true;
  }

  attachShadow() {
    this.shadowRoot = new MockElement("#shadow-root");
    this.shadowRoot.isRoot = true;
    this.shadowRoot.host = this;
    return this.shadowRoot;
  }

  addEventListener(type, handler) {
    if (!this.listeners[type]) {
      this.listeners[type] = [];
    }
    this.listeners[type].push(handler);
  }

  removeEventListener(type, handler) {
    const list = this.listeners[type];
    if (!list) {
      return;
    }
    const index = list.indexOf(handler);
    if (index !== -1) {
      list.splice(index, 1);
    }
  }

  /**
   * How many handlers are registered for a type. Used to assert that a
   * disallowed action has no reachable listener at all.
   *
   * @param {string} type
   * @returns {number}
   */
  listenerCount(type) {
    return (this.listeners[type] ?? []).length;
  }

  /**
   * Fires the registered click handlers, exactly as a real click would - this
   * is what a page script calling node.click() on an open shadow root's button
   * would trigger.
   */
  click() {
    for (const handler of [...(this.listeners.click ?? [])]) {
      handler({ type: "click", target: this });
    }
  }

  getElementById(id) {
    for (const child of this.children) {
      if (child.id === id) {
        return child;
      }
      const found = child.getElementById(id);
      if (found) {
        return found;
      }
    }
    return null;
  }

  querySelector() {
    return null;
  }

  closest() {
    return null;
  }

  dispatchEvent() {
    return true;
  }

  focus() {}
}

export class MockDocument extends MockElement {
  /**
   * @param {{ readyState?: string }} [options]
   */
  constructor({ readyState = "complete" } = {}) {
    super("#document");
    this.isRoot = true;
    this.readyState = readyState;
    this.body = new MockElement("body");
    this.appendChild(this.body);
    this.documentElement = this.body;
  }

  createElement(tagName) {
    return new MockElement(tagName);
  }
}

/**
 * Parses a markup string and appends the resulting tree to `root`.
 *
 * @param {MockElement} root
 * @param {string} html
 * @returns {MockElement}
 */
export function parseHtmlInto(root, html) {
  const stack = [root];

  TAG_PATTERN.lastIndex = 0;
  let match;
  while ((match = TAG_PATTERN.exec(html)) !== null) {
    const isClosing = Boolean(match[1]);
    const tagName = match[2].toLowerCase();
    const selfClosing = Boolean(match[4]);

    if (isClosing) {
      for (let i = stack.length - 1; i > 0; i -= 1) {
        if (stack[i].tagName === tagName.toUpperCase()) {
          stack.length = i;
          break;
        }
      }
      continue;
    }

    const element = new MockElement(tagName, parseAttributes(match[3]));
    stack[stack.length - 1].appendChild(element);

    if (!selfClosing && !VOID_TAGS.has(tagName)) {
      stack.push(element);
    }
  }

  return root;
}

/**
 * Builds a document from a markup string (used to load the real review.html).
 *
 * @param {string} html
 * @param {{ readyState?: string }} [options]
 * @returns {MockDocument}
 */
export function documentFromHtml(html, options = {}) {
  const doc = new MockDocument(options);
  parseHtmlInto(doc.body, html);
  return doc;
}
