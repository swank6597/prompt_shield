const MODAL_HOST_ID = "prompt-guardian-warning-host";

/**
 * Creates the warning dialog shown when the API blocks a prompt.
 *
 * @param {{
 *   onCancel: () => void,
 *   onSendAnyway: () => void
 * }} handlers
 * @returns {{ show: (reason: string) => void, hide: () => void }}
 */
export function createWarningDialog(handlers) {
  let host = null;
  let shadow = null;

  /**
   * Ensures the dialog host exists.
   */
  function ensureHost() {
    if (host && shadow) {
      return;
    }

    host = document.createElement("div");
    host.id = MODAL_HOST_ID;
    host.style.all = "initial";
    host.style.position = "fixed";
    host.style.inset = "0";
    host.style.zIndex = "2147483647";
    host.style.display = "none";

    shadow = host.attachShadow({ mode: "open" });
    shadow.innerHTML = `
      <style>
        :host { all: initial; }
        .overlay {
          position: fixed;
          inset: 0;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(15, 23, 42, 0.66);
          backdrop-filter: blur(8px);
          font-family: "Segoe UI", Arial, sans-serif;
        }
        .card {
          width: min(520px, calc(100vw - 32px));
          border-radius: 20px;
          background: linear-gradient(180deg, #0f172a 0%, #111827 100%);
          color: #e2e8f0;
          border: 1px solid rgba(148, 163, 184, 0.2);
          box-shadow: 0 24px 60px rgba(0, 0, 0, 0.35);
          padding: 22px;
        }
        .eyebrow {
          margin: 0 0 8px;
          font-size: 12px;
          letter-spacing: 0.18em;
          text-transform: uppercase;
          color: #38bdf8;
        }
        h2 {
          margin: 0;
          font-size: 20px;
          line-height: 1.2;
        }
        .reason {
          margin: 14px 0 0;
          color: #cbd5e1;
          line-height: 1.5;
          white-space: pre-wrap;
        }
        .actions {
          margin-top: 20px;
          display: flex;
          gap: 12px;
          justify-content: flex-end;
        }
        button {
          border: 0;
          border-radius: 12px;
          padding: 10px 16px;
          font: inherit;
          cursor: pointer;
        }
        .secondary {
          background: rgba(148, 163, 184, 0.14);
          color: #e2e8f0;
        }
        .primary {
          background: #38bdf8;
          color: #0f172a;
          font-weight: 700;
        }
      </style>
      <div class="overlay" role="dialog" aria-modal="true" aria-labelledby="pg-warning-title">
        <div class="card">
          <p class="eyebrow">Prompt Guardian</p>
          <h2 id="pg-warning-title">Sensitive Data Detected</h2>
          <p class="reason" id="pg-warning-reason"></p>
          <div class="actions">
            <button type="button" class="secondary" id="pg-warning-cancel">Cancel</button>
            <button type="button" class="primary" id="pg-warning-send-anyway">Send Anyway</button>
          </div>
        </div>
      </div>
    `;

    const cancelButton = shadow.getElementById("pg-warning-cancel");
    const sendAnywayButton = shadow.getElementById("pg-warning-send-anyway");

    cancelButton?.addEventListener("click", () => {
      hide();
      handlers.onCancel();
    });

    sendAnywayButton?.addEventListener("click", () => {
      hide();
      handlers.onSendAnyway();
    });

    (document.body || document.documentElement).appendChild(host);
  }

  /**
   * Displays the warning dialog with the provided reason.
   *
   * @param {string} reason
   */
  function show(reason) {
    ensureHost();
    const reasonNode = shadow?.getElementById("pg-warning-reason");
    if (reasonNode) {
      reasonNode.textContent = `Reason:\n${reason || "Blocked by policy"}`;
    }

    if (host) {
      host.style.display = "block";
    }
  }

  /**
   * Hides the warning dialog.
   */
  function hide() {
    if (host) {
      host.style.display = "none";
    }
  }

  return {
    show,
    hide
  };
}
