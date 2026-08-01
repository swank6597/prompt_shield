# routes.py
# API route definitions. Currently exposes the Presidio-only /analyze
# endpoint (merged from the POC's api.py) plus /health. /api/scan runs the
# full pipeline: Presidio -> Pre-Classifier -> (optional) ECI LLM -> Policy
# Engine, which turns combined findings into the final ALLOW/WARN/MASK/BLOCK.
#
# Cost-saving architecture:
#   1. Presidio always runs (cheap, local, ~20ms)
#   2. Pre-classifier checks if the LLM is even needed:
#      - Trivial prompts -> skip LLM
#      - Secrets found -> skip LLM (policy will BLOCK from Presidio alone)
#      - PII only, no enterprise terms -> skip LLM (policy will MASK)
#      - General knowledge, no enterprise overlap -> skip LLM
#      - Enterprise context ambiguous -> CALL LLM (only case that needs AI)
#   3. Policy engine makes final decision from all signals
#   4. Audit trail: every decision is persisted (backend/audit/) - see the
#      log_scan() call at the end of scan_prompt().

import os
import sys
import time

from fastapi import APIRouter, Depends

from audit.audit_logger import log_scan
from models import AnalyzeRequest, AnalyzeResponse, ECIResult, EntityResult, ScanRequest, ScanResponse
from presidio.presidio_engine import analyze_text
from utils.logger import get_logger
from auth import service as auth_service
from auth.dependencies import require_api_key

# backend/ai/'s and backend/policy/'s modules use bare imports (e.g.
# `from keyword_search import search`, `from risk_engine import
# compute_risk_score`) that assume their own directory is on sys.path.
_AI_DIR = os.path.join(os.path.dirname(__file__), "ai")
_POLICY_DIR = os.path.join(os.path.dirname(__file__), "policy")
for _extra_dir in (_AI_DIR, _POLICY_DIR):
    if _extra_dir not in sys.path:
        sys.path.insert(0, _extra_dir)

from semantic_classifier import classify as classify_context  # noqa: E402
from pre_classifier import pre_classify  # noqa: E402
from policy_engine import decide as decide_policy  # noqa: E402

log = get_logger("routes")

router = APIRouter()

# policy_engine.decide() speaks ALLOW/WARN/MASK/BLOCK. The extension only
# knows SAFE/SANITIZE/BLOCK - WARN and MASK both surface as SANITIZE.
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
def scan_prompt(request: ScanRequest, device: auth_service.Device = Depends(require_api_key)):
    request_start = time.perf_counter()
    log.info(
        "Scan request received (prompt_len=%d, device_id=%d, owner_user_id=%s)",
        len(request.prompt), device.id, device.owner_user_id,
    )

    # =========================================================================
    # Stage 1: Presidio (always runs - cheap, local, ~20ms)
    # =========================================================================
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

    # =========================================================================
    # Stage 2: Pre-Classifier (deterministic, ~1ms)
    # Decides whether the LLM call is worth making at all.
    # =========================================================================
    pre_start = time.perf_counter()
    pre_result = pre_classify(request.prompt, result["maskedText"], result)
    pre_ms = (time.perf_counter() - pre_start) * 1000

    log.info(
        "Pre-classifier: path=%s, needs_llm=%s (%.0fms) - %s",
        pre_result["decision_path"], pre_result["needs_llm"], pre_ms,
        pre_result["reason"],
    )

    # =========================================================================
    # Stage 3: ECI/LLM (only when pre-classifier says it's needed)
    # =========================================================================
    if not pre_result["needs_llm"]:
        # Use the pre-classifier's deterministic ECI result
        eci_raw = pre_result["pre_eci"]
        eci_ms = 0.0
        log.info("ECI: skipped by pre-classifier (0ms, 0 tokens used)")
    else:
        # Gray zone - enterprise context ambiguous, LLM needed
        # Extract semantic chunks from pre_classifier's semantic_result when available
        semantic_chunks = None
        semantic_result = pre_result.get("semantic_result")
        if semantic_result and isinstance(semantic_result, dict):
            semantic_chunks = semantic_result.get("top_chunks") or None

        eci_start = time.perf_counter()
        eci_raw = classify_context(
            result["maskedText"],
            entity_count=result["entityCount"],
            semantic_chunks=semantic_chunks,
        )
        eci_ms = (time.perf_counter() - eci_start) * 1000

        if eci_raw.get("confidence") == 0.0 and any("fallback" in r.lower() for r in eci_raw.get("reasoning", [])):
            log.warning("ECI: fallback triggered (%.0fms) - %s", eci_ms, eci_raw["reasoning"])
        else:
            log.info(
                "ECI: intent=%s requiresEnterpriseKnowledge=%s confidence=%.2f (%.0fms)",
                eci_raw.get("intent"), eci_raw.get("requiresEnterpriseKnowledge"),
                eci_raw.get("confidence", 0.0), eci_ms,
            )

    # semantic_classifier.classify() stashes these on a real LLM call (never
    # part of ai/schema.json's public contract) so the audit trail can
    # report which provider/model served the request - pop them before
    # building ECIResult so they never leak into the client-facing response
    # or trip Pydantic on an unexpected field. Absent (None) when the
    # pre-classifier skipped the LLM entirely.
    llm_provider = eci_raw.pop("_llm_provider", None)
    llm_model = eci_raw.pop("_llm_model", None)

    eci_result = ECIResult(**eci_raw)

    # =========================================================================
    # Stage 4: Policy Engine (deterministic, <1ms)
    # =========================================================================
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

    total_ms = presidio_ms + pre_ms + eci_ms + policy_ms
    hybrid_score = pre_result.get("hybrid_score")
    log.info(
        "Scan result: %s (policy=%s, path=%s, hybrid=%s) "
        "[total=%.0fms, presidio=%.0fms, pre=%.0fms, eci=%.0fms, policy=%.0fms]",
        status, policy_result["decision"], pre_result["decision_path"],
        f"{hybrid_score:.4f}" if hybrid_score is not None else "N/A",
        total_ms, presidio_ms, pre_ms, eci_ms, policy_ms,
    )

    # Audit trail: both masked_prompt and the raw prompt are persisted -
    # this is an enterprise audit/compliance product, retaining the raw
    # prompt is a deliberate requirement, not an oversight (see
    # backend/audit/README.md). entity_types only (never entities[].value,
    # the raw matched value used in the `issues` list above). log_scan()
    # never raises - a DB failure logs a warning and is swallowed, never
    # affecting this response. Carries both the authenticated device
    # identity (device_id/owner_user_id, from require_api_key above) and
    # the best-effort display identity (username/platform, from the
    # extension) - see specs/audit-dashboard-consolidation/design.md's
    # "Dual identity". Access to all of this, raw prompt included, is
    # controlled at the dashboard layer (admin role required) rather than
    # by withholding it here.
    log_scan(
        device_id=device.id,
        owner_user_id=device.owner_user_id,
        username=request.username,
        platform=request.platform,
        masked_prompt=result["maskedText"],
        raw_prompt=request.prompt,
        entity_count=result["entityCount"],
        entity_types=sorted(set(detection["entityTypes"])),
        eci=eci_raw,
        reason=policy_result["explanation"],
        risk_score=policy_result["riskScore"],
        matched_rules=policy_result["matchedRules"],
        decision=policy_result["decision"],
        status=status,
        decision_path=pre_result["decision_path"],
        llm_provider=llm_provider,
        llm_model=llm_model,
        presidio_ms=presidio_ms,
        eci_ms=eci_ms,
        policy_ms=policy_ms,
        total_ms=total_ms,
    )

    return ScanResponse(
        status=status,
        sanitizedPrompt=result["maskedText"],
        reason=policy_result["explanation"],
        issues=issues,
        eci=eci_result,
        riskScore=policy_result["riskScore"],
        matchedRules=policy_result["matchedRules"],
    )
