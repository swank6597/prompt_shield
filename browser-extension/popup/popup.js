import { Logger } from "../utils/logger.js";
import { getStoredUsername, setStoredUsername } from "../content/identity.js";

/**
 * Popup entry point.
 */
Logger.info("Popup Loaded");

const input = document.getElementById("pg-username-input");
const saveButton = document.getElementById("pg-username-save");
const status = document.getElementById("pg-username-status");

/**
 * Shows a brief status message under the identity form.
 *
 * @param {string} message
 */
function showStatus(message) {
  if (!status) {
    return;
  }
  status.textContent = message;
  status.hidden = false;
}

if (input) {
  getStoredUsername()
    .then((stored) => {
      if (stored) {
        input.value = stored;
      }
    })
    .catch(() => {
      // No stored value yet - leave the input empty.
    });
}

if (saveButton && input) {
  saveButton.addEventListener("click", () => {
    const value = input.value.trim();

    if (!value) {
      showStatus("Enter a name or email first.");
      return;
    }

    void setStoredUsername(value)
      .then(() => {
        Logger.info("Audit identity saved");
        showStatus("Saved.");
      })
      .catch((error) => {
        const message = error instanceof Error ? error.message : String(error);
        Logger.warn(`Failed to save audit identity: ${message}`);
        showStatus("Couldn't save - try again.");
      });
  });
}
