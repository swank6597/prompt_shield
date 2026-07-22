from presidio_analyzer import Pattern, PatternRecognizer


def get_recognizers():
    recognizers = []

    # -----------------------------------
    # IFSC Code
    # Example: HDFC0001234
    # -----------------------------------
    recognizers.append(
        PatternRecognizer(
            supported_entity="IFSC_CODE",
            supported_language="en",
            patterns=[
                Pattern(
                    name="IFSC",
                    regex=r"\b[A-Z]{4}0[A-Z0-9]{6}\b",
                    score=0.95
                )
            ],
            context=["ifsc", "bank", "branch"]
        )
    )

    # -----------------------------------
    # UPI ID
    # Example: gaurav@oksbi
    # -----------------------------------
    recognizers.append(
        PatternRecognizer(
            supported_entity="UPI_ID",
            supported_language="en",
            patterns=[
                Pattern(
                    name="UPI",
                    regex=r"\b[a-zA-Z0-9._-]+@[a-zA-Z]{2,20}\b",
                    score=0.75
                )
            ],
            context=["upi", "upi id", "payment", "paytm", "gpay", "phonepe"]
        )
    )

    # -----------------------------------
    # Bank Account Number
    # Example: 1234567890123456
    # -----------------------------------
    recognizers.append(
        PatternRecognizer(
            supported_entity="BANK_ACCOUNT",
            supported_language="en",
            patterns=[
                Pattern(
                    name="BANK_ACCOUNT",
                    regex=r"\b\d{9,18}\b",
                    score=0.50
                )
            ],
            context=["account", "account number", "bank"]
        )
    )

    return recognizers
