// app.js
// Vanilla JS, no build step or framework - same approach as
// browser-extension/, so this stays consistent with the rest of the repo.
// The dashboard is served from the same origin as /auth/* and
// /dashboard/api/*, so these are same-origin fetches - no CORS involved
// here regardless of PROMPTSHIELD_AUTH_ALLOWED_ORIGINS (that setting only
// matters for a *different* origin, e.g. a separately-hosted frontend).

const TOKEN_KEY = "promptshield_dashboard_token";
const USER_KEY = "promptshield_dashboard_user";

const STATUS_FILL = {
  ALLOW: "var(--status-good-fill)",
  WARN: "var(--status-warning-fill)",
  MASK: "var(--status-serious-fill)",
  BLOCK: "var(--status-critical-fill)",
};
const DECISION_ORDER = ["ALLOW", "WARN", "MASK", "BLOCK"];

// Every table cell below is built via innerHTML template strings for
// simplicity (no framework) - masked_prompt, username, and reason are all
// data that ultimately traces back to what someone typed into a chat box,
// so they must never be interpolated raw: a prompt containing "<img
// onerror=...>" would otherwise execute in the dashboard for whoever views
// that row. Every dynamic string below goes through this first.
function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value ?? "";
  return div.innerHTML;
}

let state = {
  page: 0,
  limit: 25,
  decision: "",
  search: "",
  days: 7,
};
let searchDebounce = null;

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function setSession(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

async function apiFetch(path, options = {}) {
  const token = getToken();
  const res = await fetch(path, {
    ...options,
    headers: {
      ...(options.headers || {}),
      Authorization: `Bearer ${token}`,
    },
  });
  if (res.status === 401) {
    clearSession();
    showLogin("Session expired - please sign in again.");
    throw new Error("unauthorized");
  }
  if (res.status === 403) {
    clearSession();
    throw new Error("This account doesn't have dashboard access (admin role required).");
  }
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status}`);
  }
  return res.json();
}

function showLogin(errorMessage) {
  document.getElementById("app").hidden = true;
  document.getElementById("login-screen").hidden = false;
  const errorEl = document.getElementById("login-error");
  if (errorMessage) {
    errorEl.textContent = errorMessage;
    errorEl.hidden = false;
  } else {
    errorEl.hidden = true;
  }
}

function showApp(user) {
  document.getElementById("login-screen").hidden = true;
  document.getElementById("app").hidden = false;
  document.getElementById("whoami").textContent = `${user.username} (${user.role})`;
}

async function handleLogin(event) {
  event.preventDefault();
  const username = document.getElementById("login-username").value.trim();
  const password = document.getElementById("login-password").value;

  try {
    const res = await fetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || "Invalid username or password");
    }
    const { accessToken } = await res.json();

    const meRes = await fetch("/auth/me", {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    const user = await meRes.json();

    setSession(accessToken, user);
    // Render BEFORE swapping the screen - if anything below throws, we
    // stay on the (visible) login screen and the catch block's error
    // message is seen, instead of silently landing on a half-rendered
    // dashboard with the error written into a now-hidden element.
    await loadAll();
    showApp(user);
  } catch (err) {
    console.error("Dashboard login/load failed:", err);
    document.getElementById("login-error").textContent = err.message;
    document.getElementById("login-error").hidden = false;
  }
}

function handleLogout() {
  apiFetch("/auth/logout", { method: "POST" }).catch(() => {});
  clearSession();
  showLogin();
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

function fmtNumber(n) {
  return new Intl.NumberFormat("en-US").format(n);
}

function fmtTimestamp(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function renderStats(stats) {
  document.getElementById("stat-total").textContent = fmtNumber(stats.totalScanned);
  document.getElementById("stat-blocked").textContent = fmtNumber(stats.byDecision.BLOCK || 0);
  const sanitized = (stats.byDecision.WARN || 0) + (stats.byDecision.MASK || 0);
  document.getElementById("stat-sanitized").textContent = fmtNumber(sanitized);
  document.getElementById("stat-risk").textContent = stats.avgRiskScore;
  document.getElementById("stat-no-llm").textContent = `${stats.pctResolvedWithoutLlm}%`;
}

function renderDecisionsChart(dailyDecisions) {
  const container = document.getElementById("chart-decisions");
  container.innerHTML = "";

  if (!dailyDecisions.length) {
    container.innerHTML = '<p class="chart-empty">No scans in this window yet.</p>';
    document.getElementById("legend-decisions").innerHTML = "";
    return;
  }

  const maxTotal = Math.max(
    ...dailyDecisions.map((d) => DECISION_ORDER.reduce((sum, k) => sum + (d[k] || 0), 0)),
    1,
  );

  dailyDecisions.forEach((day) => {
    const col = document.createElement("div");
    col.className = "chart-day";
    const dayTotal = DECISION_ORDER.reduce((sum, k) => sum + (day[k] || 0), 0);
    const label = new Date(day.day).toLocaleDateString(undefined, { month: "short", day: "numeric" });
    col.title = `${label}: ${dayTotal} scan(s)`;

    DECISION_ORDER.forEach((decision) => {
      const count = day[decision] || 0;
      if (count === 0) return;
      const seg = document.createElement("div");
      seg.className = "chart-segment";
      seg.style.background = STATUS_FILL[decision];
      seg.style.height = `${Math.max((count / maxTotal) * 100, 2)}%`;
      col.appendChild(seg);
    });
    container.appendChild(col);
  });

  const legend = document.getElementById("legend-decisions");
  legend.innerHTML = DECISION_ORDER.map(
    (d) => `<li><span class="legend-swatch" style="background:${STATUS_FILL[d]}"></span>${d}</li>`,
  ).join("");
}

function renderBarList(containerId, counts, labelMap = {}) {
  const container = document.getElementById(containerId);
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((sum, [, n]) => sum + n, 0);

  if (!entries.length || total === 0) {
    container.innerHTML = '<p class="chart-empty">No data in this window yet.</p>';
    return;
  }

  const max = Math.max(...entries.map(([, n]) => n));
  container.innerHTML = entries
    .map(([key, n]) => {
      const label = labelMap[key] || key;
      const pct = Math.round((n / max) * 100);
      return `
        <div class="bar-row">
          <span class="bar-row-label" title="${label}">${label}</span>
          <span class="bar-track"><span class="bar-fill" style="width:${pct}%"></span></span>
          <span class="bar-row-value">${fmtNumber(n)}</span>
        </div>`;
    })
    .join("");
}

function statusBadge(decision) {
  return `<span class="status-badge status-${decision}">${decision}</span>`;
}

function truncate(text, maxLen = 60) {
  if (!text) return "";
  return text.length > maxLen ? `${text.slice(0, maxLen)}…` : text;
}

function renderEventsTable(events) {
  const body = document.getElementById("events-body");
  if (!events.length) {
    body.innerHTML = '<tr><td colspan="9" class="muted" style="padding:20px;">No events match these filters.</td></tr>';
    return;
  }

  body.innerHTML = events
    .map((e) => {
      // rawPrompt can still be null for a row logged before this column
      // existed - everything from here on is admin-only (the whole
      // dashboard requires the admin role - see dashboard/routes.py), so
      // no per-field visibility check is needed, just a null fallback.
      const rawPromptBlock = `
        <div class="row-detail-wide row-detail-danger">
          <dt>Raw prompt</dt>
          <dd>${e.rawPrompt ? escapeHtml(e.rawPrompt) : "— (not recorded for this scan)"}</dd>
        </div>`;

      return `
      <tr class="event-row" data-id="${e.id}">
        <td><button class="row-expand-btn" data-toggle="${e.id}">▸</button></td>
        <td>${fmtTimestamp(e.timestamp)}</td>
        <td>${escapeHtml(e.username || "unknown")}</td>
        <td>${escapeHtml(e.platform || "unknown")}</td>
        <td class="prompt-cell" title="${escapeHtml(e.maskedPrompt || "")}">${escapeHtml(truncate(e.maskedPrompt))}</td>
        <td>${statusBadge(e.decision)}</td>
        <td>${e.riskScore ?? "–"}</td>
        <td>${escapeHtml(e.layer)}</td>
        <td>${e.llmProvider ? `${escapeHtml(e.llmProvider)}${e.llmModel ? ` / ${escapeHtml(e.llmModel)}` : ""}` : "—"}</td>
      </tr>
      <tr class="row-detail" id="detail-${e.id}" hidden>
        <td></td>
        <td colspan="8">
          <dl class="row-detail-grid">
            <div class="row-detail-wide"><dt>Masked prompt</dt><dd>${escapeHtml(e.maskedPrompt || "—")}</dd></div>
            ${rawPromptBlock}
            <div><dt>Reason</dt><dd>${escapeHtml(e.reason || "—")}</dd></div>
            <div><dt>Matched rules</dt><dd>${escapeHtml(e.matchedRules.join(", ")) || "—"}</dd></div>
            <div><dt>Entity types</dt><dd>${escapeHtml(e.entityTypes.join(", ")) || "—"}</dd></div>
            <div><dt>Decision path</dt><dd>${escapeHtml(e.decisionPath || "—")}</dd></div>
            <div><dt>Device id / owner user id</dt><dd>${e.deviceId ?? "—"} / ${e.ownerUserId ?? "—"}</dd></div>
            <div><dt>Total latency</dt><dd>${e.totalMs ? `${Math.round(e.totalMs)}ms` : "—"}</dd></div>
          </dl>
        </td>
      </tr>`;
    })
    .join("");

  body.querySelectorAll("[data-toggle]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-toggle");
      const row = document.getElementById(`detail-${id}`);
      row.hidden = !row.hidden;
      btn.textContent = row.hidden ? "▸" : "▾";
    });
  });
}

function renderPagination(total) {
  const info = document.getElementById("page-info");
  const start = state.page * state.limit + (total === 0 ? 0 : 1);
  const end = Math.min((state.page + 1) * state.limit, total);
  info.textContent = total === 0 ? "0 results" : `${start}–${end} of ${fmtNumber(total)}`;

  document.getElementById("prev-page").disabled = state.page === 0;
  document.getElementById("next-page").disabled = end >= total;
}

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------

async function loadStats() {
  const stats = await apiFetch(`/dashboard/api/stats?days=${state.days}`);
  renderStats(stats);
  renderDecisionsChart(stats.dailyDecisions);
  renderBarList("chart-layers", stats.byLayer);
  renderBarList("chart-providers", stats.byLlmProvider, { none: "None (pre-classifier resolved it)" });
}

async function loadEvents() {
  const params = new URLSearchParams({
    limit: state.limit,
    offset: state.page * state.limit,
  });
  if (state.decision) params.set("decision", state.decision);
  if (state.search) params.set("search", state.search);

  const data = await apiFetch(`/dashboard/api/events?${params}`);
  renderEventsTable(data.events);
  renderPagination(data.total);
}

async function loadAll() {
  await Promise.all([loadStats(), loadEvents()]);
}

// ---------------------------------------------------------------------------
// Wiring
// ---------------------------------------------------------------------------

document.getElementById("login-form").addEventListener("submit", handleLogin);
document.getElementById("logout-btn").addEventListener("click", handleLogout);

document.getElementById("range-select").addEventListener("change", (e) => {
  state.days = Number(e.target.value);
  loadStats();
});

document.getElementById("filter-decision").addEventListener("change", (e) => {
  state.decision = e.target.value;
  state.page = 0;
  loadEvents();
});

document.getElementById("filter-search").addEventListener("input", (e) => {
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => {
    state.search = e.target.value.trim();
    state.page = 0;
    loadEvents();
  }, 300);
});

document.getElementById("prev-page").addEventListener("click", () => {
  if (state.page > 0) {
    state.page -= 1;
    loadEvents();
  }
});

document.getElementById("next-page").addEventListener("click", () => {
  state.page += 1;
  loadEvents();
});

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

(async function init() {
  const token = getToken();
  const rawUser = localStorage.getItem(USER_KEY);
  if (!token || !rawUser) {
    showLogin();
    return;
  }
  showApp(JSON.parse(rawUser));
  try {
    await loadAll();
  } catch (err) {
    console.error("Dashboard initial load failed:", err);
    // apiFetch already handles 401 by showing the login screen. A 403
    // (e.g. a viewer's stored session, or a role downgrade) clears the
    // session too but doesn't redirect on its own - do that here instead
    // of leaving a broken, half-rendered app view up.
    if (!getToken()) {
      showLogin(err.message);
    }
  }
})();
