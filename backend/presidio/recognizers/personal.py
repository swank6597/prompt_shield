from presidio_analyzer import Pattern, PatternRecognizer


def get_recognizers():
    recognizers = []

    # -------------------------
    # PAN Number
    # -------------------------
    recognizers.append(
        PatternRecognizer(
            supported_entity="PAN_NUMBER",
            supported_language="en",
            patterns=[
                Pattern(
                    name="PAN",
                    regex=r"\b[A-Z]{5}[0-9]{4}[A-Z]\b",
                    score=0.95
                )
            ],
            context=["pan", "permanent account number"]
        )
    )

    # -------------------------
    # Aadhaar Number
    # -------------------------
    recognizers.append(
        PatternRecognizer(
            supported_entity="AADHAAR_NUMBER",
            supported_language="en",
            patterns=[
                Pattern(
                    name="AADHAAR",
                    regex=r"\b[2-9][0-9]{3}\s?[0-9]{4}\s?[0-9]{4}\b",
                    score=0.95
                )
            ],
            context=["aadhaar", "uidai", "uid"]
        )
    )

    # -------------------------
    # Passport Number
    # -------------------------
    recognizers.append(
        PatternRecognizer(
            supported_entity="PASSPORT_NUMBER",
            supported_language="en",
            patterns=[
                Pattern(
                    name="PASSPORT",
                    regex=r"\b[A-Z][0-9]{7}\b",
                    score=0.90
                )
            ],
            context=["passport"]
        )
    )

    # -------------------------
    # Driving License
    # -------------------------
    recognizers.append(
        PatternRecognizer(
            supported_entity="DRIVING_LICENSE",
            supported_language="en",
            patterns=[
                Pattern(
                    name="DL",
                    regex=r"\b[A-Z]{2}[0-9]{2}\s?[0-9]{11}\b",
                    score=0.85
                )
            ],
            context=["driving", "license", "licence", "dl"]
        )
    )

    # -------------------------
    # GSTIN
    # -------------------------
    recognizers.append(
        PatternRecognizer(
            supported_entity="GSTIN",
            supported_language="en",
            patterns=[
                Pattern(
                    name="GSTIN",
                    regex=r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b",
                    score=0.95
                )
            ],
            context=["gst", "gstin"]
        )
    )

    # -------------------------
    # Employee ID
    # -------------------------
    recognizers.append(
        PatternRecognizer(
            supported_entity="EMPLOYEE_ID",
            supported_language="en",
            patterns=[
                Pattern(
                    name="EMPLOYEE_ID",
                    regex=r"\bEMP\d{4,8}\b",
                    score=0.90
                )
            ],
            context=["employee", "emp", "employee id"]
        )
    )

    # -------------------------
    # US Phone Number
    # -------------------------
    recognizers.append(
        PatternRecognizer(
            supported_entity="PHONE_NUMBER",
            supported_language="en",
            patterns=[
                Pattern(
                    name="US_PHONE",
                    regex=r"\b(?:\+1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}\b",
                    score=0.85
                )
            ],
            context=["phone", "mobile", "cell", "tel"]
        )
    )

    return recognizers
