from presidio_analyzer import Pattern, PatternRecognizer


def get_recognizers():
    recognizers = []

    # -----------------------------------
    # Host Name / FQDN
    # Example:
    # server01.company.local
    # api.prod.company.com
    # -----------------------------------
    recognizers.append(
        PatternRecognizer(
            supported_entity="HOST_NAME",
            supported_language="en",
            patterns=[
                Pattern(
                    name="HOST_NAME",
                    regex=r"\b(?:[a-zA-Z0-9-]+\.)+[A-Za-z]{2,}\b",
                    score=0.80
                )
            ],
            context=["host", "hostname", "server", "fqdn", "dns"]
        )
    )

    # -----------------------------------
    # MAC Address
    # Example:
    # 00:1A:2B:3C:4D:5E
    # -----------------------------------
    recognizers.append(
        PatternRecognizer(
            supported_entity="MAC_ADDRESS",
            supported_language="en",
            patterns=[
                Pattern(
                    name="MAC_ADDRESS",
                    regex=r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b",
                    score=0.95
                )
            ],
            context=["mac", "mac address"]
        )
    )

    return recognizers
