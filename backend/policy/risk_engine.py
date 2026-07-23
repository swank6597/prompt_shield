# risk_engine.py
# Computes an aggregate 0-100 risk score from analyzer findings (Regex +
# Presidio entity types) and ECI classification flags. Used by
# policy_engine.py both as an explainable number for the UI/demo and as
# a catch-all signal for rules.json's risk_score_min conditions - it is
# a supporting signal, not the primary decision mechanism (that's the
# explicit boolean rules in rules.json).

# Higher weight = more sensitive entity type. Unknown/future entity
# types not listed here default to a small weight rather than 0, so
# new recognizers contribute something even before this list is updated.
ENTITY_WEIGHTS = {
    "PRIVATE_KEY": 50,
    "GITHUB_TOKEN": 40,
    "OPENAI_API_KEY": 40,
    "AWS_ACCESS_KEY": 40,
    "AWS_SECRET_KEY": 40,
    "JWT_TOKEN": 30,
    "PAN_NUMBER": 20,
    "AADHAAR_NUMBER": 20,
    "PASSPORT_NUMBER": 20,
    "GSTIN": 20,
    "DRIVING_LICENSE": 15,
    "BANK_ACCOUNT": 15,
    "IFSC_CODE": 10,
    "UPI_ID": 10,
    "HOST_NAME": 10,
    "MAC_ADDRESS": 10,
    "EMPLOYEE_ID": 10,
    "VEHICLE_NUMBER": 5,
    "PERSON": 5,
    "EMAIL_ADDRESS": 5,
    "PHONE_NUMBER": 5,
}
DEFAULT_ENTITY_WEIGHT = 5

# Weight applied per ECI boolean flag that is True, scaled by the
# model's own reported confidence for that classification.
ECI_FLAG_WEIGHTS = {
    "containsSecrets": 30,
    "containsInternalArchitecture": 30,
    "containsSourceCode": 25,
    "containsCustomerData": 25,
    "containsImplementationDetails": 20,
    "requiresEnterpriseKnowledge": 10,
}


def compute_risk_score(detection: dict, eci: dict) -> int:
    """
    detection: {"entityCount": int, "entityTypes": [str, ...]}
    eci: dict matching backend/ai/schema.json

    Returns an integer 0-100 (capped).
    """
    score = 0.0

    for entity_type in detection.get("entityTypes", []):
        score += ENTITY_WEIGHTS.get(entity_type, DEFAULT_ENTITY_WEIGHT)

    confidence = eci.get("confidence", 1.0)
    for field, weight in ECI_FLAG_WEIGHTS.items():
        if eci.get(field) is True:
            score += weight * confidence

    return min(100, round(score))