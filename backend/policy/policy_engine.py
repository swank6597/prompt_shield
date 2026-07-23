# policy_engine.py
# Deterministic, rule-based decision engine. Consumes the merged
# detection result (Regex + Presidio entity findings) and the ECI
# classification result, evaluates them against rules.json, and returns
# the final decision (ALLOW/WARN/MASK/BLOCK) plus a human-readable
# explanation. No AI involved in the decision itself - this is the
# deterministic layer everything else feeds into.
#
# NOTE: expects `detection` already merged from Regex + Presidio layers
# (see utils/helpers.py's merge_detection_results(), not yet built as of
# this file's creation - routes.py will be responsible for producing
# this shape before calling decide()).

import json
import os

from risk_engine import compute_risk_score

_DIR = os.path.dirname(__file__)
RULES_PATH = os.path.join(_DIR, "rules.json")

SEVERITY_ORDER = ["ALLOW", "WARN", "MASK", "BLOCK"]


def _load_rules() -> dict:
    with open(RULES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _condition_matches(condition: dict, detection: dict, eci: dict, risk_score: int) -> bool:
    entity_types = set(detection.get("entityTypes", []))

    if "entityTypes_any_of" in condition:
        if not entity_types.intersection(condition["entityTypes_any_of"]):
            return False

    if "eci_field_true_any_of" in condition:
        if not any(eci.get(field) is True for field in condition["eci_field_true_any_of"]):
            return False

    if "eci_min_confidence" in condition:
        if eci.get("confidence", 0) < condition["eci_min_confidence"]:
            return False

    if "eci_max_confidence" in condition:
        if eci.get("confidence", 1) > condition["eci_max_confidence"]:
            return False

    if "risk_score_min" in condition:
        if risk_score < condition["risk_score_min"]:
            return False

    return True


def decide(detection: dict, eci: dict) -> dict:
    """
    detection: {"entityCount": int, "entityTypes": [str, ...]}
               - merged, deduped output of Regex + Presidio layers.
    eci: dict matching backend/ai/schema.json - ECI's classification.

    Returns the INTERNAL decision result (routes.py trims this further
    before it crosses back to the extension - see the maskedText note
    below):
        {
            "decision": "ALLOW" | "WARN" | "MASK" | "BLOCK",
            "explanation": str,
            "riskScore": int,
            "matchedRules": [str, ...]
        }

    Does not include maskedText/entityCount in its return value - the
    caller (routes.py) already has those and attaches them when building
    the final response, so policy_engine.py stays focused purely on the
    decision itself.
    """
    rules = _load_rules()
    risk_score = compute_risk_score(detection, eci)

    matched = [
        rule for rule in rules["rules"]
        if _condition_matches(rule["condition"], detection, eci, risk_score)
    ]

    if not matched:
        return {
            "decision": rules.get("default_decision", "ALLOW"),
            "explanation": "No policy rules matched - prompt appears safe to send.",
            "riskScore": risk_score,
            "matchedRules": [],
        }

    matched.sort(key=lambda r: SEVERITY_ORDER.index(r["decision"]), reverse=True)
    top_rule = matched[0]

    return {
        "decision": top_rule["decision"],
        "explanation": top_rule["description"],
        "riskScore": risk_score,
        "matchedRules": [r["id"] for r in matched],
    }


if __name__ == "__main__":
    # Quick manual check: python policy_engine.py
    # Uses hand-built detection/eci dicts since the real merge step
    # (utils/helpers.py) doesn't exist yet - this validates the rules
    # engine logic in isolation.
    test_cases = [
        (
            "Secret detected (should BLOCK)",
            {"entityCount": 1, "entityTypes": ["GITHUB_TOKEN"]},
            {"requiresEnterpriseKnowledge": False, "containsInternalArchitecture": False,
             "containsImplementationDetails": False, "containsSourceCode": False,
             "containsCustomerData": False, "containsSecrets": False, "confidence": 0.9},
        ),
        (
            "Enterprise OAuth2 question (should BLOCK - internal architecture)",
            {"entityCount": 0, "entityTypes": []},
            {"requiresEnterpriseKnowledge": True, "containsInternalArchitecture": True,
             "containsImplementationDetails": True, "containsSourceCode": False,
             "containsCustomerData": False, "containsSecrets": False, "confidence": 0.95},
        ),
        (
            "Only PII detected, no secrets/architecture (should MASK)",
            {"entityCount": 1, "entityTypes": ["PAN_NUMBER"]},
            {"requiresEnterpriseKnowledge": False, "containsInternalArchitecture": False,
             "containsImplementationDetails": False, "containsSourceCode": False,
             "containsCustomerData": False, "containsSecrets": False, "confidence": 0.9},
        ),
        (
            "Public OAuth2 question (should ALLOW)",
            {"entityCount": 0, "entityTypes": []},
            {"requiresEnterpriseKnowledge": False, "containsInternalArchitecture": False,
             "containsImplementationDetails": False, "containsSourceCode": False,
             "containsCustomerData": False, "containsSecrets": False, "confidence": 0.95},
        ),
        (
            "ECI fallback / could not classify (should WARN)",
            {"entityCount": 0, "entityTypes": []},
            {"requiresEnterpriseKnowledge": True, "containsInternalArchitecture": False,
             "containsImplementationDetails": False, "containsSourceCode": False,
             "containsCustomerData": False, "containsSecrets": False, "confidence": 0.0},
        ),
    ]

    for label, detection, eci in test_cases:
        result = decide(detection, eci)
        print(f"\n--- {label} ---")
        print(json.dumps(result, indent=2))