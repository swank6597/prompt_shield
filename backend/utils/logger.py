# logger.py
# Shared logging configuration used across backend modules. Every module
# calls get_logger(__name__) instead of configuring its own handler, so
# console output stays consistently formatted and level is controlled in
# one place via an environment variable - no code change needed to get
# more/less detail out of a running backend.
#
# Usage: PROMPTSHIELD_LOG_LEVEL=DEBUG uvicorn app:app --reload --port 8081
# DEBUG shows per-call detail (Ollama payload sizes, retrieved knowledge
# doc scores, retry attempts); default INFO shows request-level milestones.

import logging
import os
import sys

_LOG_LEVEL = os.environ.get("PROMPTSHIELD_LOG_LEVEL", "INFO").upper()
_ROOT_NAME = "promptshield"
_configured = False


def _configure_root() -> None:
    global _configured
    if _configured:
        return

    root = logging.getLogger(_ROOT_NAME)
    root.setLevel(_LOG_LEVEL)
    root.propagate = False

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root.addHandler(handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """
    Returns a logger under the shared "promptshield" namespace, e.g.
    get_logger("routes") -> logger named "promptshield.routes". First call
    (from any module) configures the shared console handler; every
    subsequent call reuses it.
    """
    _configure_root()
    return logging.getLogger(f"{_ROOT_NAME}.{name}")
