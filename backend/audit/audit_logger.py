# audit_logger.py
# Audit Logger - persists a privacy-safe record of every /api/scan decision
# to SQLite: the already-masked prompt (never the raw prompt), entity TYPES
# only (never the raw matched values used in the live response's issues
# list), the ECI classification, and the Policy Engine's decision. Backs the
# future dashboard (counts by decision/day/platform).
#
# Known limitation - see README.md: this guarantee is bounded by Presidio's
# recall. A detection below presidio_engine.py's MIN_SCORE is filtered out
# BEFORE anonymization, so its raw text is still sitting in maskedText
# verbatim; an entity type no recognizer knows how to match is invisible
# entirely. Not something this module can fix.

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from config import AUDIT_DB_PATH  # noqa: E402
from utils.logger import get_logger  # noqa: E402

log = get_logger("audit")

# ECI boolean flags stored as individual INTEGER (0/1) columns rather than a
# JSON blob - these are exactly what a dashboard filters/groups by
# (WHERE eci_contains_secrets = 1, GROUP BY eci_intent), so they need to be
# queryable columns. entity_types/matched_rules/eci_reasoning stay JSON TEXT
# columns - variable-length, display-only, not first-class filter targets.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS scan_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    username TEXT NOT NULL DEFAULT 'unknown',
    platform TEXT NOT NULL DEFAULT 'unknown',
    masked_prompt TEXT NOT NULL,
    entity_count INTEGER NOT NULL DEFAULT 0,
    entity_types TEXT NOT NULL DEFAULT '[]',
    eci_intent TEXT,
    eci_document_type TEXT,
    eci_confidence REAL,
    eci_requires_enterprise_knowledge INTEGER,
    eci_contains_internal_architecture INTEGER,
    eci_contains_implementation_details INTEGER,
    eci_contains_source_code INTEGER,
    eci_contains_customer_data INTEGER,
    eci_contains_secrets INTEGER,
    eci_impacts_gdpr INTEGER,
    eci_impacts_pcidss INTEGER,
    eci_impacts_hipaa INTEGER,
    eci_impacts_iso27001 INTEGER,
    eci_reasoning TEXT,
    risk_score INTEGER,
    matched_rules TEXT,
    decision TEXT NOT NULL,
    status TEXT NOT NULL,
    presidio_ms REAL,
    eci_ms REAL,
    policy_ms REAL,
    total_ms REAL
);
"""

# Indexed on the three dimensions the eventual dashboard aggregates by
# (counts by day/decision/platform). No username index yet - no concrete
# query needs it today; cheap to add later if a per-user drill-down appears.
_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_scan_audit_timestamp ON scan_audit_log(timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_scan_audit_decision ON scan_audit_log(decision);",
    "CREATE INDEX IF NOT EXISTS idx_scan_audit_platform ON scan_audit_log(platform);",
)


def _init_db() -> None:
    """Idempotent - CREATE TABLE/INDEX IF NOT EXISTS never wipes prior rows."""
    os.makedirs(os.path.dirname(AUDIT_DB_PATH), exist_ok=True)
    with sqlite3.connect(AUDIT_DB_PATH) as conn:
        conn.execute(_SCHEMA)
        for statement in _INDEXES:
            conn.execute(statement)
        conn.commit()


_init_db()  # module-level side effect, matches presidio_engine.py's pattern


def log_scan(
    *,
    username: str | None,
    platform: str | None,
    masked_prompt: str,
    entity_count: int,
    entity_types: list,
    eci: dict,
    risk_score: int,
    matched_rules: list,
    decision: str,
    status: str,
    presidio_ms: float,
    eci_ms: float,
    policy_ms: float,
    total_ms: float,
) -> None:
    """
    Persists one scan's privacy-safe audit record. Never raises - any
    failure (disk full, locked DB, permissions) is logged as a warning and
    swallowed, matching ai/semantic_classifier.py's classify() contract:
    audit logging must never break the actual /api/scan response.

    masked_prompt must already be Presidio's anonymized output - never pass
    the raw prompt here. entity_types must be type strings only - never
    pass entities[].value (the raw matched value used in the live
    response's issues list).
    """
    try:
        with sqlite3.connect(AUDIT_DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO scan_audit_log (
                    timestamp, username, platform, masked_prompt,
                    entity_count, entity_types,
                    eci_intent, eci_document_type, eci_confidence,
                    eci_requires_enterprise_knowledge,
                    eci_contains_internal_architecture,
                    eci_contains_implementation_details,
                    eci_contains_source_code, eci_contains_customer_data,
                    eci_contains_secrets, eci_impacts_gdpr,
                    eci_impacts_pcidss, eci_impacts_hipaa,
                    eci_impacts_iso27001, eci_reasoning,
                    risk_score, matched_rules, decision, status,
                    presidio_ms, eci_ms, policy_ms, total_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    username or "unknown",
                    platform or "unknown",
                    masked_prompt,
                    entity_count,
                    json.dumps(entity_types),
                    eci.get("intent"),
                    eci.get("documentType"),
                    eci.get("confidence"),
                    int(bool(eci.get("requiresEnterpriseKnowledge"))),
                    int(bool(eci.get("containsInternalArchitecture"))),
                    int(bool(eci.get("containsImplementationDetails"))),
                    int(bool(eci.get("containsSourceCode"))),
                    int(bool(eci.get("containsCustomerData"))),
                    int(bool(eci.get("containsSecrets"))),
                    int(bool(eci.get("impactsGDPR"))),
                    int(bool(eci.get("impactsPCIDSS"))),
                    int(bool(eci.get("impactsHIPAA"))),
                    int(bool(eci.get("impactsISO27001"))),
                    json.dumps(eci.get("reasoning", [])),
                    risk_score,
                    json.dumps(matched_rules),
                    decision,
                    status,
                    presidio_ms,
                    eci_ms,
                    policy_ms,
                    total_ms,
                ),
            )
            conn.commit()
    except Exception as e:  # noqa: BLE001 - fail-safe by design, never raises
        log.warning("Audit log write failed: %s", e)


if __name__ == "__main__":
    # Quick manual check: python audit_logger.py
    log_scan(
        username="test@example.com",
        platform="ChatGPT",
        masked_prompt="My email is <EMAIL_ADDRESS>",
        entity_count=1,
        entity_types=["EMAIL_ADDRESS"],
        eci={
            "intent": "Other",
            "documentType": "None",
            "requiresEnterpriseKnowledge": False,
            "containsInternalArchitecture": False,
            "containsImplementationDetails": False,
            "containsSourceCode": False,
            "containsCustomerData": False,
            "containsSecrets": False,
            "impactsGDPR": True,
            "impactsPCIDSS": False,
            "impactsHIPAA": False,
            "impactsISO27001": False,
            "confidence": 0.9,
            "reasoning": ["Contains a personal email address."],
        },
        risk_score=5,
        matched_rules=["mask_personal_identifiers"],
        decision="MASK",
        status="SANITIZE",
        presidio_ms=12.3,
        eci_ms=0.0,
        policy_ms=0.5,
        total_ms=13.1,
    )
    print(f"Logged one test row to {AUDIT_DB_PATH}")
