# prompt_builder.py
# Assembles the final system/user prompt sent to Ollama by combining:
#   - the system_prompt.md template (role/constraints)
#   - schema.json (turned into inline output-format instructions, so the
#     schema only ever lives in one file - no risk of the prompt text
#     drifting out of sync with schema.json over time)
#   - the classifier_prompt.md template (per-request placeholders)
#   - the merged masked prompt text and any retrieved knowledge snippets
#
# Does NOT call keyword_search.py itself - semantic_classifier.py is
# responsible for orchestrating retrieval -> build_prompt() -> Ollama,
# keeping this module a pure "assemble strings" step.

import json
import os

_DIR = os.path.dirname(__file__)
PROMPTS_DIR = os.path.join(_DIR, "prompts")
SCHEMA_PATH = os.path.join(_DIR, "schema.json")

NO_KNOWLEDGE_MESSAGE = "No relevant enterprise knowledge was retrieved for this prompt."


def _load_template(filename: str) -> str:
    with open(os.path.join(PROMPTS_DIR, filename), "r", encoding="utf-8") as f:
        return f.read()


def _generate_schema_instructions() -> str:
    """
    Reads schema.json and renders it as a human/LLM-readable output-format
    block, in the exact order fields are required. This is regenerated
    from schema.json every call, so editing schema.json is the only
    place that needs to change - system_prompt.md never needs updating
    when a field is added/renamed.
    """
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = json.load(f)

    props = schema["properties"]
    required = schema["required"]

    lines = ["```json", "{"]
    for idx, field in enumerate(required):
        spec = props[field]
        ftype = spec.get("type")
        desc = spec.get("description", "")
        enum = spec.get("enum")
        comma = "," if idx < len(required) - 1 else ""

        if enum:
            allowed = " | ".join(f'"{e}"' for e in enum)
            value_hint = f"<one of: {allowed}>"
        elif ftype == "boolean":
            value_hint = "<true|false>"
        elif ftype == "number":
            value_hint = "<number between 0.0 and 1.0>"
        elif ftype == "array":
            value_hint = '["<short reason>", ...]'
        else:
            value_hint = "<string>"

        lines.append(f'  "{field}": {value_hint}{comma}  // {desc}')

    lines.append("}")
    lines.append("```")
    return "\n".join(lines)


def _format_retrieved_knowledge(retrieved_docs: list[dict]) -> str:
    if not retrieved_docs:
        return NO_KNOWLEDGE_MESSAGE

    sections = []
    for doc in retrieved_docs:
        sections.append(f"### {doc['filename']} ({doc['category']})\n\n{doc['content']}")
    return "\n\n".join(sections)


def build_prompt(masked_text: str, retrieved_docs: list[dict] | None = None) -> dict:
    """
    Returns {"system": "<system prompt>", "user": "<user/classifier prompt>"}
    ready to hand to ollama_client.py's chat-style call.
    """
    retrieved_docs = retrieved_docs or []

    system_prompt = _load_template("system_prompt.md").replace(
        "{{SCHEMA_INSTRUCTIONS}}", _generate_schema_instructions()
    )

    user_prompt = (
        _load_template("classifier_prompt.md")
        .replace("{{RETRIEVED_KNOWLEDGE}}", _format_retrieved_knowledge(retrieved_docs))
        .replace("{{MASKED_PROMPT}}", masked_text)
    )

    return {"system": system_prompt, "user": user_prompt}


if __name__ == "__main__":
    # Quick manual check: python prompt_builder.py
    from keyword_search import search

    test_prompt = "Explain our OAuth2 implementation."
    docs = search(test_prompt)
    built = build_prompt(test_prompt, docs)

    print("=== SYSTEM PROMPT ===")
    print(built["system"])
    print("\n=== USER PROMPT ===")
    print(built["user"])