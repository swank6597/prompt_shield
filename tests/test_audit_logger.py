# test_audit_logger.py
# Verifies backend/audit/audit_logger.py's core safety guarantees:
#   (a) only masked_prompt/entity_types ever reach the DB - no raw values
#   (b) log_scan() never raises, even when the underlying write fails
#   (c) table creation is idempotent - re-running _init_db() never wipes rows
#
# Run from repo root: python tests/test_audit_logger.py
#
# Uses a throwaway DB file (never the real audit_log.db), pointed to via
# PROMPTSHIELD_AUDIT_DB_PATH set BEFORE importing audit_logger, since
# _init_db() runs as a module-level side effect at import time.

import json
import os
import sqlite3
import sys
import tempfile
from unittest import mock

_TEST_DB_PATH = os.path.join(tempfile.gettempdir(), "promptshield_test_audit_log.db")
for _suffix in ("", "-journal", "-wal", "-shm"):
    _candidate = _TEST_DB_PATH + _suffix
    if os.path.exists(_candidate):
        os.remove(_candidate)

os.environ["PROMPTSHIELD_AUDIT_DB_PATH"] = _TEST_DB_PATH

sys.path.insert(0, "backend")
sys.path.insert(0, "backend/audit")
import audit_logger  # noqa: E402

RAW_SECRET_VALUE = "ghp_thisIsARawSecretThatMustNeverBeLogged123456"
MASKED_PROMPT = "My GitHub token is <GITHUB_TOKEN>. My email is <EMAIL_ADDRESS>."

FAKE_ECI = {
    "intent": "Other",
    "documentType": "None",
    "requiresEnterpriseKnowledge": False,
    "containsInternalArchitecture": False,
    "containsImplementationDetails": False,
    "containsSourceCode": False,
    "containsCustomerData": False,
    "containsSecrets": True,
    "impactsGDPR": True,
    "impactsPCIDSS": False,
    "impactsHIPAA": False,
    "impactsISO27001": False,
    "confidence": 0.9,
    "reasoning": ["Contains a masked secret token and email address."],
}


def _fetch_latest_row():
    conn = sqlite3.connect(_TEST_DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM scan_audit_log ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return dict(row) if row else None


def test_no_raw_value_reaches_the_db():
    print("--- test_no_raw_value_reaches_the_db ---")
    audit_logger.log_scan(
        username="test@example.com",
        platform="ChatGPT",
        masked_prompt=MASKED_PROMPT,
        entity_count=2,
        entity_types=["EMAIL_ADDRESS", "GITHUB_TOKEN"],  # pre-sorted, matching routes.py's caller contract
        eci=FAKE_ECI,
        risk_score=68,
        matched_rules=["block_secret_credentials"],
        decision="BLOCK",
        status="BLOCK",
        presidio_ms=5.0,
        eci_ms=0.0,
        policy_ms=0.2,
        total_ms=5.5,
    )

    row = _fetch_latest_row()
    assert row is not None, "expected a row to have been inserted"
    assert row["masked_prompt"] == MASKED_PROMPT
    assert RAW_SECRET_VALUE not in row["masked_prompt"]
    # Scan every column, not just masked_prompt - the raw value must never
    # leak into any field (e.g. via eci_reasoning).
    assert RAW_SECRET_VALUE not in json.dumps(row)

    entity_types = json.loads(row["entity_types"])
    assert entity_types == ["EMAIL_ADDRESS", "GITHUB_TOKEN"]
    assert all(isinstance(t, str) and "@" not in t and not t.startswith("ghp_") for t in entity_types)

    assert row["eci_impacts_gdpr"] == 1
    assert row["eci_contains_secrets"] == 1
    assert json.loads(row["matched_rules"]) == ["block_secret_credentials"]
    assert json.loads(row["eci_reasoning"]) == FAKE_ECI["reasoning"]
    assert row["decision"] == "BLOCK"
    assert row["status"] == "BLOCK"
    assert row["username"] == "test@example.com"
    assert row["platform"] == "ChatGPT"
    print("PASS\n")


def test_defaults_to_unknown_when_identity_missing():
    print("--- test_defaults_to_unknown_when_identity_missing ---")
    audit_logger.log_scan(
        username=None,
        platform=None,
        masked_prompt="Hi, how are you?",
        entity_count=0,
        entity_types=[],
        eci={**FAKE_ECI, "containsSecrets": False, "impactsGDPR": False},
        risk_score=0,
        matched_rules=[],
        decision="ALLOW",
        status="SAFE",
        presidio_ms=1.0,
        eci_ms=0.0,
        policy_ms=0.1,
        total_ms=1.2,
    )
    row = _fetch_latest_row()
    assert row["username"] == "unknown"
    assert row["platform"] == "unknown"
    print("PASS\n")


def test_log_scan_never_raises_on_db_failure():
    print("--- test_log_scan_never_raises_on_db_failure ---")
    with mock.patch.object(audit_logger.sqlite3, "connect", side_effect=sqlite3.OperationalError("simulated failure")):
        try:
            audit_logger.log_scan(
                username="x", platform="y", masked_prompt="z", entity_count=0,
                entity_types=[], eci=FAKE_ECI, risk_score=0, matched_rules=[],
                decision="ALLOW", status="SAFE", presidio_ms=0.0, eci_ms=0.0,
                policy_ms=0.0, total_ms=0.0,
            )
        except Exception as e:  # this is exactly what must never happen
            raise AssertionError(f"log_scan() raised {e!r} - it must never raise") from e
    print("PASS - log_scan() swallowed the simulated DB failure\n")


def test_init_db_is_idempotent():
    print("--- test_init_db_is_idempotent ---")
    before = _fetch_latest_row()
    audit_logger._init_db()
    audit_logger._init_db()
    after = _fetch_latest_row()
    assert before == after, "re-running _init_db() must never wipe existing rows"
    print("PASS\n")


if __name__ == "__main__":
    test_no_raw_value_reaches_the_db()
    test_defaults_to_unknown_when_identity_missing()
    test_log_scan_never_raises_on_db_failure()
    test_init_db_is_idempotent()
    print("=" * 60)
    print("All audit_logger tests passed.")
    print(f"(test DB at {_TEST_DB_PATH} - safe to delete)")
    print("=" * 60)
