from presidio_analyzer import Pattern, PatternRecognizer


def get_recognizers():
    recognizers = []

    # -----------------------------------
    # OpenAI API Key
    # Example:
    # sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    # -----------------------------------
    recognizers.append(
        PatternRecognizer(
            supported_entity="OPENAI_API_KEY",
            supported_language="en",
            patterns=[
                Pattern(
                    name="OPENAI_API_KEY",
                    regex=r"\bsk-[A-Za-z0-9_-]{20,}\b",
                    score=0.90
                )
            ],
            context=["openai", "api key", "secret"]
        )
    )

    # -----------------------------------
    # GitHub Personal Access Token
    #
    # Classic:
    # ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    #
    # Fine-grained:
    # github_pat_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    # -----------------------------------
    recognizers.append(
        PatternRecognizer(
            supported_entity="GITHUB_TOKEN",
            supported_language="en",
            patterns=[
                Pattern(
                    name="GITHUB_CLASSIC_TOKEN",
                    regex=r"\bghp_[A-Za-z0-9]{36}\b",
                    score=0.95
                ),
                Pattern(
                    name="GITHUB_FINE_GRAINED_TOKEN",
                    regex=r"\bgithub_pat_[A-Za-z0-9_]{82}\b",
                    score=0.95
                )
            ],
            context=["github", "token", "pat"]
        )
    )

    # -----------------------------------
    # JWT Token
    # -----------------------------------
    recognizers.append(
        PatternRecognizer(
            supported_entity="JWT_TOKEN",
            supported_language="en",
            patterns=[
                Pattern(
                    name="JWT",
                    regex=r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9._-]+\.[A-Za-z0-9._-]+",
                    score=0.80
                )
            ],
            context=["jwt", "bearer", "authorization"]
        )
    )

    # -----------------------------------
    # AWS Access Key ID
    # Example:
    # AKIAIOSFODNN7EXAMPLE
    # -----------------------------------
    recognizers.append(
        PatternRecognizer(
            supported_entity="AWS_ACCESS_KEY",
            supported_language="en",
            patterns=[
                Pattern(
                    name="AWS_ACCESS_KEY",
                    regex=r"\bAKIA[0-9A-Z]{16}\b",
                    score=0.95
                )
            ],
            context=["aws", "access key", "access key id"]
        )
    )

    # -----------------------------------
    # AWS Secret Access Key
    # Example:
    # wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
    # -----------------------------------
    recognizers.append(
        PatternRecognizer(
            supported_entity="AWS_SECRET_KEY",
            supported_language="en",
            patterns=[
                Pattern(
                    name="AWS_SECRET_KEY",
                    regex=r"\b[A-Za-z0-9/+=]{40}\b",
                    score=0.90
                )
            ],
            context=["aws", "secret", "secret key", "secret access key"]
        )
    )

    # -----------------------------------
    # Private Key
    # -----------------------------------
    recognizers.append(
        PatternRecognizer(
            supported_entity="PRIVATE_KEY",
            supported_language="en",
            patterns=[
                Pattern(
                    name="PRIVATE_KEY",
                    regex=r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
                    score=0.95
                )
            ],
            context=["private key", "pem", "certificate"]
        )
    )

    return recognizers
