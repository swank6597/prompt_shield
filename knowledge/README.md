# Knowledge Base

A fictional enterprise knowledge base for **NovaBank Financial Technologies** — a made-up
bank with made-up products (Mercury Payments, Orion Identity, Atlas Analytics, Nexus
Portal, Token Vault). It exists purely as retrieval context so the backend's
lexical/semantic pre-classifier and ECI (Enterprise Context Intelligence) layer have
something concrete to detect "enterprise-sensitive" leaks against. **None of this is
real company data** — no real names, financial data, or identifiable entities appear
anywhere in this folder.

## How it's used

- `backend/ai/context_loader.py` walks this directory with `os.walk()` at startup and
  loads every `.md` file into memory, deriving each doc's `category` from its immediate
  subfolder name.
- `backend/ai/lexical_engine.py` builds a TF-IDF inverted index from these documents.
- `backend/ai/semantic_engine.py` chunks these documents (on `##` headings or ~500-char
  boundaries) and embeds them into a FAISS index.
- `backend/ai/semantic_classifier.py` retrieves the most relevant chunks/docs for a
  given prompt and includes them as context in the LLM classification call.

`knowledge_index.json` at the root of this folder is a **stub only** (`{"_comment": ...}`)
— it is not read by any code today. `context_loader.py` walks the filesystem directly
instead. `scripts/seed_knowledge.py` is intended to eventually validate these docs and
populate that index, but is currently an unimplemented stub itself.

## Structure

Each subfolder is a category (~4-5 docs each, ~48 total):

| Folder | Contents |
|---|---|
| `apis/` | API reference docs — Identity API, Payment API, integration guide, event catalog |
| `architecture/` | Enterprise/system architecture, deployment architecture, system integrations |
| `company/` | Company profile, business overview, corporate governance, mission/vision |
| `compliance/` | Access governance, audit guidelines, exception management, regulatory compliance |
| `data/` | Data classification, retention policy, customer data model, enterprise data glossary |
| `engineering/` | Branching/release process, CI/CD, code review guidelines, coding standards |
| `governance/` | Enterprise risk management, business continuity, vendor risk, operational resilience |
| `operations/` | Monitoring/observability, runbooks, production support, disaster recovery, incident management |
| `organization/` | Business units, departments, engineering organization, ownership model |
| `products/` | Product docs for Mercury Payments, Atlas Analytics, Nexus Portal, Orion Identity, Token Vault |
| `support/` | Incident escalation, service catalog, SLA/SLO policy, support roles |

Documents use structured frontmatter (title, classification, owner, document ID,
version, dates) followed by generic corporate-style prose — written to exercise the
detection pipeline, not to read as a real company handbook.

## Adding or editing content

- New/edited `.md` files are picked up automatically on backend restart (the FAISS
  index compares file modification times and rebuilds only what changed — see
  `backend/ai/README.md`).
- Keep additions clearly fictional and internally consistent with the existing NovaBank
  product/org names so retrieval and ECI classification stay coherent.
- There's no strict frontmatter schema enforced by code today — follow the existing
  files' style for consistency.

## Related docs

- Pre-classifier and ECI pipeline: [`../backend/ai/README.md`](../backend/ai/README.md)
- Lexical/semantic retrieval design: [`../specs/lexical-semantic-upgrade/`](../specs/lexical-semantic-upgrade/)
- System architecture: [`../docs/architecture.md`](../docs/architecture.md)
