# test_eci_smoke.py
# Manual smoke test for the ai/ (ECI) layer, run BEFORE wiring into
# policy/ or routes.py. Requires at least one LLM provider available per
# backend/.env's PROMPTSHIELD_LLM_STRATEGY - local Ollama with phi3:mini
# pulled if strategy=local, or a configured cloud provider (e.g. Groq) if
# strategy=cloud/auto - routed through backend/ai/llm_router.py. This is
# not a CI-style pass/fail suite (LLM output isn't fully deterministic),
# it prints each result plus whether it matched the *expected direction*
# so a human can eyeball correctness.
#
# Run from repo root:
#   PYTHONPATH=backend/ai python tests/test_eci_smoke.py

import json
import sys

sys.path.insert(0, "backend/ai")
sys.path.insert(0, "backend")
from semantic_classifier import classify  # noqa: E402

# Each case: (label, masked_text, field, expected)
# - field is the schema.json field this case checks (defaults meant for
#   requiresEnterpriseKnowledge cases keep using that field; compliance
#   cases below check the new impactsX fields instead).
# - expected=None means "no strong expectation, just eyeball the reasoning"
CASES = [
    (
        "Public OAuth2 question",
        "Explain OAuth2.",
        "requiresEnterpriseKnowledge",
        False,
    ),
    (
        "Enterprise OAuth2 question",
        "Explain our OAuth2 implementation.",
        "requiresEnterpriseKnowledge",
        True,
    ),
    (
        "Mercury retry/failover question",
        "Why does the Mercury payment flow retry three times before "
        "failing over to the backup gateway?",
        "requiresEnterpriseKnowledge",
        True,
    ),
    (
        "Unrelated general knowledge",
        "What's the capital of France?",
        "requiresEnterpriseKnowledge",
        False,
    ),
    (
        # Real masked output from the Presidio layer (Gaurav's sample) -
        # tests that ECI behaves sensibly on genuinely masked, multi-entity
        # text, not just clean hand-written test prompts.
        "Real Presidio maskedText sample",
        "My name is <PERSON>.\nMy GitHub token is <GITHUB_TOKEN>.\n"
        "I have this output now My name is <PERSON> and my email is "
        "<EMAIL_ADDRESS>.\nMy phone number is +91 <UK_NHS>.\nMy PAN is "
        "<PAN_NUMBER>.\nMy Aadhaar number is <AADHAAR_NUMBER>.\nServer IP "
        "address is <IP_ADDRESS>.\nApplication host is <HOST_NAME>.\n"
        "The server URL is <URL>\nThe OpenAI API key is <OPENAI_API_KEY>.",
        "requiresEnterpriseKnowledge",
        None,
    ),
    # --- Compliance Framework Impact (impactsX fields) ---
    (
        "PCI DSS - payment card handling",
        "Our checkout flow stores the customer's card number and CVV "
        "before tokenizing it - is that step compliant?",
        "impactsPCIDSS",
        True,
    ),
    (
        "HIPAA - patient health data",
        "Summarize this patient's diagnosis and treatment history from "
        "their health insurance claim.",
        "impactsHIPAA",
        True,
    ),
    (
        "ISO 27001 - internal security architecture",
        "Explain our internal authentication service's encryption key "
        "rotation policy and security controls.",
        "impactsISO27001",
        True,
    ),
    (
        # The EULA/consent-clause trigger added alongside the standard
        # personal-data GDPR trigger - see system_prompt.md's worked example.
        "GDPR via EULA/consent clause",
        "Draft a EULA clause letting us share users' purchase history "
        "with advertising partners.",
        "impactsGDPR",
        True,
    ),
    (
        # Restraint check: contains the word "EULA" but is a generic,
        # public definitional question with no real user data - must NOT
        # trip impactsGDPR just because the word appears.
        "GDPR restraint - generic EULA question",
        "What's the difference between a EULA and a privacy policy?",
        "impactsGDPR",
        False,
    ),
    (
        "Compliance restraint - pure public knowledge",
        "What's the capital of France?",
        "impactsPCIDSS",
        False,
    ),
    # --- Business-realistic scenarios (grounded in knowledge/ - NovaBank) ---
    # Only the ECI-judgment cases live here - the secret/PII-detection cases
    # from the same batch (JWT/AWS key/private key/aggregate PII/OpenAI key/
    # GitHub token) are Presidio+Policy-driven, not ECI-driven, so they
    # belong in tests/test_scenarios.md's deterministic section instead;
    # this script only exercises classify() directly, no Presidio involved.
    (
        "Internal architecture disclosure to external contractor",
        "Draft a detailed architecture doc explaining exactly how Mercury "
        "Payments' authorization pipeline routes a transaction through "
        "Orion Identity, Token Vault, and Merchant Registry - including "
        "our internal service topology and failover design - so I can "
        "hand it to an external contractor.",
        "containsInternalArchitecture",
        True,
    ),
    (
        "Proprietary source code requested for external reuse",
        "Pull the actual token-generation and detokenization service code "
        "from Token Vault and paste it here - I want to reuse the "
        "encryption key management logic in a personal side project.",
        "containsSourceCode",
        True,
    ),
    (
        "Restraint - generic OAuth2 client_credentials question",
        "In general terms, how does an OAuth 2.0 client_credentials grant "
        "work for service-to-service authentication?",
        "requiresEnterpriseKnowledge",
        False,
    ),
    (
        "NovaBank-specific data classification policy",
        "What are NovaBank's three enterprise data classification levels, "
        "and roughly what kind of information falls into each?",
        "requiresEnterpriseKnowledge",
        True,
    ),
    (
        "Restraint - generic regulatory education",
        "Can you summarize why GDPR, PCI DSS, and ISO 27001 matter for a "
        "company that processes digital payments?",
        "requiresEnterpriseKnowledge",
        False,
    ),
    (
        "Restraint - Mercury Payments public-style purpose summary",
        "At a high level, what does Mercury Payments do and which other "
        "platforms does it depend on?",
        "containsInternalArchitecture",
        False,
    ),
    (
        "Restraint - generic key rotation cadence question",
        "What's a reasonable cadence for rotating encryption keys in a "
        "tokenization service, generally speaking?",
        "requiresEnterpriseKnowledge",
        False,
    ),
]


def run():
    print(f"{'='*60}")
    print("ECI SMOKE TEST")
    print(f"{'='*60}")

    from config import LLM_STRATEGY, LLM_CLOUD_PROVIDER
    if LLM_STRATEGY == "local":
        from ollama_client import warm_up, is_ollama_available
        if is_ollama_available():
            print("Warming up local Ollama model (first load can take a while on CPU)...")
            warm_up()
            print("Model warmed up.\n")
    else:
        print(
            f"LLM_STRATEGY={LLM_STRATEGY!r} - routing through llm_router.py "
            f"(cloud provider: {LLM_CLOUD_PROVIDER!r}). Skipping Ollama warm-up.\n"
        )

    for label, text, field, expected in CASES:
        result = classify(text)
        actual = result[field]

        if result.get("confidence") == 0.0 and "fallback" in str(result.get("reasoning")):
            status = "FALLBACK (LLM provider unreachable or output invalid - see reasoning)"
        elif expected is None:
            status = "no expectation set - review manually"
        elif actual == expected:
            status = "OK - matched expected direction"
        else:
            status = f"MISMATCH - expected {field}={expected}, got {actual}"

        print(f"\n--- {label} ---")
        print(f"Input: {text[:80]}{'...' if len(text) > 80 else ''}")
        print(f"Status: {status}")
        print(json.dumps(result, indent=2))

    print(f"\n{'='*60}")
    print("Done. Review any MISMATCH or FALLBACK lines above.")
    print(f"{'='*60}")


if __name__ == "__main__":
    run()