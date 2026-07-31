# queries.py
# Read-only queries over backend/audit/'s scan_audit_log table. No writes
# happen here - audit_logger.log_scan() is the only writer, this module
# only ever SELECTs. Kept separate from audit_logger.py so the write-path's
# fail-safe contract (never raise) isn't mixed with read-path code that's
# allowed to raise (a dashboard query failing should surface as a 500, not
# be silently swallowed the way a scan's audit write is).

import json
import os
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from config import AUDIT_DB_PATH  # noqa: E402
from audit.audit_logger import _init_db as _init_audit_db  # noqa: E402

# Ensures the schema (including the enrichment columns) exists even if this
# module is imported before any scan has ever run - audit_logger.py's own
# _init_db() already runs at its import time, but that only happens once
# something imports audit_logger; the dashboard shouldn't 500 on a fresh
# install just because no /api/scan call has happened yet.
_init_audit_db()

# Maps the pre-classifier's fine-grained decision_path onto the coarser
# "which layer actually made the call" bucket the dashboard displays -
# mirrors specs/audit-dashboard-consolidation/'s "layer_responsible"
# concept from the original dashboard proposal. Any decision_path not
# listed here (including NULL, for rows written before this column
# existed) falls into "Unknown".
_LAYER_BY_DECISION_PATH = {
    "hard_block": "Presidio",
    "trivial": "Pre-Classifier (Lexical)",
    "pii_only": "Pre-Classifier (Lexical)",
    "general_knowledge": "Pre-Classifier (Lexical)",
    "enterprise_detected": "Pre-Classifier (Lexical)",
    "engine_degraded": "Pre-Classifier (Lexical)",
    "semantic_confirmed_public": "Pre-Classifier (Semantic)",
    "semantic_confirmed_enterprise": "Pre-Classifier (Semantic)",
    "true_ambiguity": "ECI (LLM)",
    "enterprise_ambiguous": "ECI (LLM)",
}

DECISION_ORDER = ["ALLOW", "WARN", "MASK", "BLOCK"]


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(AUDIT_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def layer_for(decision_path: str | None) -> str:
    return _LAYER_BY_DECISION_PATH.get(decision_path, "Unknown")


def get_stats(days: int = 7) -> dict:
    """
    Summary-card + chart data for the last `days` days (default 7).
    Returns counts only - no prompt text, no per-row detail - this is the
    aggregate view; get_events() below is the drill-down.
    """
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT decision, decision_path, llm_provider, risk_score, platform "
            "FROM scan_audit_log WHERE timestamp >= ?",
            (since,),
        ).fetchall()

        total = len(rows)
        by_decision = Counter(r["decision"] for r in rows)
        by_layer = Counter(layer_for(r["decision_path"]) for r in rows)
        by_provider = Counter((r["llm_provider"] or "none") for r in rows)
        by_platform = Counter((r["platform"] or "unknown") for r in rows)

        risk_scores = [r["risk_score"] for r in rows if r["risk_score"] is not None]
        avg_risk = round(sum(risk_scores) / len(risk_scores), 1) if risk_scores else 0.0

        resolved_without_llm = sum(1 for r in rows if not r["llm_provider"])
        pct_without_llm = round(100 * resolved_without_llm / total, 1) if total else 0.0

        # Daily decision counts for the trend chart, oldest first.
        daily_rows = conn.execute(
            "SELECT substr(timestamp, 1, 10) AS day, decision, COUNT(*) AS n "
            "FROM scan_audit_log WHERE timestamp >= ? GROUP BY day, decision ORDER BY day",
            (since,),
        ).fetchall()
        by_day: dict[str, dict[str, int]] = {}
        for r in daily_rows:
            by_day.setdefault(r["day"], {}).setdefault(r["decision"], 0)
            by_day[r["day"]][r["decision"]] += r["n"]

        return {
            "windowDays": days,
            "totalScanned": total,
            "byDecision": {d: by_decision.get(d, 0) for d in DECISION_ORDER},
            "byLayer": dict(by_layer),
            "byLlmProvider": dict(by_provider),
            "byPlatform": dict(by_platform),
            "avgRiskScore": avg_risk,
            "pctResolvedWithoutLlm": pct_without_llm,
            "dailyDecisions": [
                {"day": day, **{d: counts.get(d, 0) for d in DECISION_ORDER}}
                for day, counts in sorted(by_day.items())
            ],
        }
    finally:
        conn.close()


def get_events(
    limit: int = 50,
    offset: int = 0,
    decision: str | None = None,
    platform: str | None = None,
    search: str | None = None,
) -> tuple[list[dict], int]:
    """
    Paginated, filterable event list for the dashboard's table view.
    `search` matches against masked_prompt/raw_prompt/username/reason
    (substring, case-insensitive) - useful for a compliance investigation
    ("find every scan that mentioned X").

    Every event includes `rawPrompt` - access control for this entire
    table happens one layer up, in routes.py (admin role required for the
    whole dashboard), not by selectively withholding fields here. See
    backend/audit/README.md for why this product retains raw prompts.
    """
    conn = _connect()
    try:
        clauses = []
        params: list = []
        if decision:
            clauses.append("decision = ?")
            params.append(decision)
        if platform:
            clauses.append("platform = ?")
            params.append(platform)
        if search:
            clauses.append("(masked_prompt LIKE ? OR raw_prompt LIKE ? OR username LIKE ? OR reason LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like, like, like])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        total = conn.execute(f"SELECT COUNT(*) AS c FROM scan_audit_log {where}", params).fetchone()["c"]
        rows = conn.execute(
            f"SELECT * FROM scan_audit_log {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()

        events = []
        for r in rows:
            event = {
                "id": r["id"],
                "timestamp": r["timestamp"],
                "username": r["username"],
                "platform": r["platform"],
                "maskedPrompt": r["masked_prompt"],
                "rawPrompt": r["raw_prompt"],
                "deviceId": r["device_id"],
                "ownerUserId": r["owner_user_id"],
                "decision": r["decision"],
                "status": r["status"],
                "riskScore": r["risk_score"],
                "reason": r["reason"],
                "matchedRules": json.loads(r["matched_rules"] or "[]"),
                "entityTypes": json.loads(r["entity_types"] or "[]"),
                "decisionPath": r["decision_path"],
                "layer": layer_for(r["decision_path"]),
                "llmProvider": r["llm_provider"],
                "llmModel": r["llm_model"],
                "totalMs": r["total_ms"],
            }
            events.append(event)
        return events, total
    finally:
        conn.close()
