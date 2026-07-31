const PREFIX = "[PromptShield]";

/**
 * Lightweight logger with a consistent PromptShield prefix.
 */
class PromptShieldLogger {
  /**
   * Writes an informational message.
   *
   * @param {string} message
   */
  info(message) {
    console.log(`${PREFIX}\n\n${message}`);
  }

  /**
   * Writes a warning message.
   *
   * @param {string} message
   */
  warn(message) {
    console.warn(`${PREFIX}\n\n${message}`);
  }

  /**
   * Writes an error message.
   *
   * @param {string | Error} message
   */
  error(message) {
    console.error(`${PREFIX}\n\n${message instanceof Error ? message.message : message}`);
  }
}

export const Logger = new PromptShieldLogger();
export default Logger;
