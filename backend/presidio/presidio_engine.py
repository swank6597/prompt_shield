# presidio_engine.py
# Layer 2 detection - wraps Microsoft Presidio Analyzer/Anonymizer to detect
# and mask PII (names, emails, phone numbers, credit cards, addresses, etc.)
# plus custom enterprise/India-specific entities registered via recognizers/.
#
# This module is intentionally FastAPI-agnostic: routes.py calls into it,
# it does not know about HTTP. Merged from the standalone Presidio POC's
# api.py (analyzer/anonymizer setup + core analyze logic).

from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

from presidio.recognizers.registry import register_all

# Minimum confidence score to keep a detection (filters out low-confidence noise).
MIN_SCORE = 0.85

# ----------------------------------------------------
# Initialize Presidio (runs once, at import time)
# ----------------------------------------------------
analyzer = AnalyzerEngine()
register_all(analyzer)

anonymizer = AnonymizerEngine()


def analyze_text(text: str) -> dict:
    """
    Runs Presidio analysis + anonymization on the given text.

    Returns a plain dict (not a pydantic model) so this module has no
    dependency on backend/models.py - routes.py is responsible for
    wrapping this into the AnalyzeResponse schema.

    Shape:
        {
            "entityCount": int,
            "maskedText": str,
            "entities": [
                {"entity_type": str, "value": str, "score": float,
                 "start": int, "end": int},
                ...
            ]
        }
    """
    results = analyzer.analyze(text=text, language="en")

    # Filter out low-confidence detections
    results = [r for r in results if r.score >= MIN_SCORE]

    anonymized = anonymizer.anonymize(text=text, analyzer_results=results)

    entities = [
        {
            "entity_type": r.entity_type,
            "value": text[r.start:r.end],
            "score": round(r.score, 2),
            "start": r.start,
            "end": r.end,
        }
        for r in results
    ]

    return {
        "entityCount": len(entities),
        "maskedText": anonymized.text,
        "entities": entities,
    }
