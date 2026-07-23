# routes.py
# API route definitions. Currently exposes the Presidio-only /analyze
# endpoint (merged from the POC's api.py) plus /health. /api/scan runs the
# full pipeline: Presidio -> ECI (ai/) -> Policy Engine (policy/), which
# turns their combined findings into the final ALLOW/WARN/MASK/BLOCK
# decision. Only Regex (backend/regex/) still needs to be wired in.

import os
import sys
import time

from fastapi import APIRouter

from models import AnalyzeRequest, AnalyzeResponse, ECIResult, EntityResult, ScanRequest, ScanResponse
from presidio.presidio_engine import analyze_text
from utils.logger import get_logger

# backend/ai/'s and backend/policy/'s modules use bare imports (e.g.
# `from keyword_search import search`, `from risk_engine import
# compute_risk_score`) that assume their own directory is on sys.path -
# the same pattern ollama_client.py already uses for backend/ itself.
# Mirrored here rather than refactored so those modules keep working when
# run standalone (`python backend/ai/semantic_classifier.py`,
# `python backend/policy/policy_engine.py`, tests/test_eci_smoke.py).
_AI_DIR = os.path.join(os.path.dirname(__file__), "ai")
_POLICY_DIR = os.path.join(os.path.dirname(__file__), "policy")
for _extra_dir in (_AI_DIR, _POLICY_DIR):
    if _extra_dir not in sys.path:
        sys.path.insert(0, _extra_dir)

from semantic_classifier import classify as classify_context  # noqa: E402
from policy_engine import decide as decide_policy  # noqa: E402

log = get_logger("routes")

router = APIRouter()

# policy_engine.decide() speaks ALLOW/WARN/MASK/BLOCK (its own internal
# severity vocabulary, shared with rules.json). The extension only knows
# SAFE/SANITIZE/BLOCK (see browser-extension/content/observer.js) - WARN
# and MASK both surface as SANITIZE since neither should auto-send, but
# both still let the user review and choose to send the sanitized prompt.
DECISION_TO_STATUS = {
    "ALLOW": "SAFE",
    "WARN": "SANITIZE",
    "MASK": "SANITIZE",
    "BLOCK": "BLOCK",
}


@router.get("/health")
def health():
    return {
        "status": "UP",
        "service": "PromptShield Detection API",
        "version": "1.0.0",
    }


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest):
    result = analyze_text(request.text)

    return AnalyzeResponse(
        success=True,
        entityCount=result["entityCount"],
        maskedText=result["maskedText"],
        entities=[EntityResult(**e) for e in result["entities"]],
    )


@router.post("/api/scan", response_model=ScanResponse)
def scan_prompt(request: ScanRequest):
    log.info("Scan request received (prompt_len=%d)", len(request.prompt))

    presidio_start = time.perf_counter()
    result = analyze_text(request.prompt)
    presidio_ms = (time.perf_counter() - presidio_start) * 1000

    if result["entityCount"] == 0:
        log.info("Presidio: no entities detected (%.0fms)", presidio_ms)
    else:
        entity_types = sorted({e["entity_type"] for e in result["entities"]})
        log.info(
            "Presidio: %d entit(y/ies) detected %s (%.0fms)",
            result["entityCount"], entity_types, presidio_ms,
        )

    # ECI runs on the already-masked text (never the raw prompt), and on
    # every request - not just when Presidio finds entities - since it
    # catches enterprise-context risk (e.g. "explain our OAuth2
    # implementation") that contains no PII at all. classify() never
    # raises; on any failure it returns a fail-closed fallback dict.
    eci_start = time.perf_counter()
    eci_raw = classify_context(result["maskedText"])
    eci_ms = (time.perf_counter() - eci_start) * 1000

    if eci_raw.get("confidence") == 0.0 and any("fallback" in r.lower() for r in eci_raw.get("reasoning", [])):
        log.warning("ECI: fallback triggered (%.0fms) - %s", eci_ms, eci_raw["reasoning"])
    else:
        log.info(
            "ECI: intent=%s requiresEnterpriseKnowledge=%s confidence=%.2f (%.0fms)",
            eci_raw.get("intent"), eci_raw.get("requiresEnterpriseKnowledge"),
            eci_raw.get("confidence", 0.0), eci_ms,
        )

    eci_result = ECIResult(**eci_raw)

    # detection is the merged Regex+Presidio shape policy_engine.py expects.
    # Regex isn't wired in yet, so this is Presidio-only for now - adding
    # regex hits later just means extending entityTypes here.
    detection = {
        "entityCount": result["entityCount"],
        "entityTypes": [entity["entity_type"] for entity in result["entities"]],
    }

    policy_start = time.perf_counter()
    policy_result = decide_policy(detection, eci_raw)
    policy_ms = (time.perf_counter() - policy_start) * 1000

    log.info(
        "Policy: decision=%s riskScore=%d matchedRules=%s (%.0fms)",
        policy_result["decision"], policy_result["riskScore"],
        policy_result["matchedRules"], policy_ms,
    )

    status = DECISION_TO_STATUS.get(policy_result["decision"], "SANITIZE")

    issues = [
        {
            "entityType": entity["entity_type"],
            "value": entity["value"],
            "score": entity["score"],
        }
        for entity in result["entities"]
    ]

    log.info("Scan result: %s (policy=%s)", status, policy_result["decision"])

    return ScanResponse(
        status=status,
        sanitizedPrompt=result["maskedText"],
        reason=policy_result["explanation"],
        issues=issues,
        eci=eci_result,
        riskScore=policy_result["riskScore"],
        matchedRules=policy_result["matchedRules"],
    )
