# custom_recognizers.py
# Originally contained PAN_NUMBER, AADHAAR_NUMBER, PASSPORT_NUMBER, and
# HOST_NAME/EMPLOYEE_ID recognizers that duplicated (with weaker context
# matching) what personal.py and infrastructure.py already define more
# thoroughly. Trimmed to keep only the genuinely unique entity - if any
# of the removed ones were intentional, re-add here rather than in
# personal.py/infrastructure.py to avoid re-introducing duplicate
# recognizers for the same entity_type.
#
# NOTE: function renamed get_custom_recognizers -> get_recognizers to
# match the interface every other recognizer module uses (registry.py
# expects get_recognizers() on every module it imports).

from presidio_analyzer import Pattern, PatternRecognizer


def get_recognizers():
    recognizers = []

    # --------------------------------------------------
    # Indian Vehicle Number
    # Example:
    # MH12AB1234
    # MH 12 AB 1234
    # --------------------------------------------------
    recognizers.append(
        PatternRecognizer(
            supported_entity="VEHICLE_NUMBER",
            supported_language="en",
            patterns=[
                Pattern(
                    name="VEHICLE",
                    regex=r"\b[A-Z]{2}\s?\d{1,2}\s?[A-Z]{1,2}\s?\d{4}\b",
                    score=0.90
                )
            ],
            context=["vehicle", "registration", "number plate"]
        )
    )

    return recognizers
