# product_names.py
# Derives the set of enterprise product/platform names that spaCy's built-in
# NER is prone to mislabelling as PERSON, so presidio_engine.py can drop those
# specific false positives after detection.
#
# WHY AN ALLOWLIST AT ALL
# -----------------------
# Measured against the running analyzer (specs/lexical-semantic-fix, Finding 7):
#
#     "...routes a transaction through Orion Identity, Token Vault, and
#      Merchant Registry."        -> PERSON score=0.8500 value='Token Vault'
#     "Please email Rajesh Kumar about the merchant dispute."
#                                 -> PERSON score=0.8500 value='Rajesh Kumar'
#
# A product name and a real person's name score *identically*, to four decimal
# places, and both land exactly on presidio_engine.MIN_SCORE. Confidence
# therefore carries no information that separates the two, and raising
# MIN_SCORE above 0.85 would delete every PERSON detection this system makes.
# Identifying the specific names by value is the only route left.
#
# WHERE THE NAMES COME FROM  (spec task 5.2)
# ------------------------------------------
# The enterprise knowledge corpus is the source of truth, but only its
# *structured* parts are read: the YAML front matter of the documents under
# knowledge/products/ and knowledge/architecture/, plus the document filenames
# themselves. Specifically, per file:
#
#   1. the filename slug            token-vault.md      -> "Token Vault"
#   2. the front-matter `title:`     title: Token Vault  -> "Token Vault"
#   3. front-matter related-document references that point at a product doc
#      (`- merchant-registry.md` inside products/, or
#       `- ../products/merchant-registry.md` inside architecture/)
#                                                        -> "Merchant Registry"
#
# Prose is deliberately NOT scanned. Every name this list wrongly contains is a
# real person whose name Presidio will stop masking, so a false entry here is a
# silent PII leak - strictly worse than the cosmetic false positive being fixed.
# Extracting capitalised phrases from 48 documents of running text would be the
# easiest way to acquire such an entry (headings, team names, "Change Advisory
# Board", the signatories in `approved_by:`), so the extractor is restricted to
# fields that name exactly one thing each and are checked by the shape rule
# below. Rule 3 exists because "Merchant Registry" is a real platform in the
# corpus that has no document of its own; it is referenced only as a related
# document, so rules 1 and 2 alone would miss it.
#
# Every candidate must additionally match _NAME_SHAPE: two or three
# capitalised alphabetic words. That rejects the single-word case ("Atlas",
# "Mercury"), which is the dangerous one - a lone corpus word is far more
# likely to collide with a real given name or surname than a full two-word
# product name is.
#
# RESIDUAL RISK, STATED PLAINLY
# -----------------------------
# If a product were ever named after a plausible person - "Grace Hopper", say -
# this list would suppress that person's name. Full-span equality (see
# is_product_name) bounds the damage to that exact full name: a person whose
# surname or given name merely appears in the list is unaffected, verified
# against "Mercury Sharma", "Vault Ramachandran" and "Atlas Fernandes", all of
# which still detect at 0.85. No current corpus name has that shape.
#
# Deliberately NOT importing ai/context_loader.load_knowledge_base(): it walks
# and caches all 48 documents including their full text, and presidio_engine.py
# has no other dependency on backend/ai/. Nine small front-matter reads on
# first use are cheaper than that cache and keep the detection layer
# independent of the classification layer.

import os
import re
from functools import lru_cache

from utils.logger import get_logger

log = get_logger("presidio.product_names")

# knowledge/ lives at the project root: backend/presidio/ -> backend/ -> root/
KNOWLEDGE_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "knowledge")
)

# Subfolders of knowledge/ that describe products and platforms. Other
# subfolders (company/, organization/, support/, ...) name people and teams and
# are never read.
_SOURCE_SUBDIRS = ("products", "architecture")

# Two or three capitalised alphabetic words. Single words are rejected on
# purpose - see RESIDUAL RISK above.
_NAME_SHAPE = re.compile(r"^[A-Z][A-Za-z]*(?: [A-Z][A-Za-z]*){1,2}$")

# Front-matter keys whose list items may reference a sibling product document.
_RELATED_KEYS = ("related_documents", "related-documents")

# Punctuation that may sit at the edge of a detected span but is not part of
# the name. The apostrophe is handled separately (possessive stripping).
_EDGE_PUNCT = " \t\r\n.,;:!?\"“”()[]{}<>*_-–—/\\"

_POSSESSIVE = re.compile(r"['\u2019]s$", re.IGNORECASE)

_cache: frozenset[str] | None = None


# ---------------------------------------------------------------------------
# Front-matter parsing (intentionally minimal: no YAML dependency)
# ---------------------------------------------------------------------------

def _front_matter(text: str) -> dict:
    """
    Extracts the leading `--- ... ---` block as a dict of
    {key: str} and {key: [str, ...]} for simple `- item` lists.

    Returns {} when the document has no front-matter fence. Anything past the
    closing fence is body prose and is never parsed.
    """
    lines = text.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    fields: dict = {}
    current_key = None
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            break
        if stripped.startswith("- "):
            if current_key is not None:
                fields.setdefault(current_key, [])
                if isinstance(fields[current_key], list):
                    fields[current_key].append(stripped[2:].strip())
            continue
        if ":" in stripped:
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()
            current_key = key
            fields[key] = value if value else []
    return fields


def _name_from_slug(slug: str) -> str:
    """`token-vault.md` / `../products/token-vault.md` -> `Token Vault`."""
    base = os.path.basename(slug.strip()).removesuffix(".md")
    words = [w for w in re.split(r"[-_\s]+", base) if w]
    return " ".join(w[:1].upper() + w[1:] for w in words)


def _candidates_from_file(path: str, subdir: str) -> list[str]:
    """Yields raw name candidates from one knowledge document."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as exc:
        log.warning("Could not read knowledge document %s: %s", path, exc)
        return []

    found: list[str] = []
    fields = _front_matter(text)

    # Rules 1 and 2 apply to product documents only. An architecture document's
    # filename and title name a *document* ("Application Landscape"), not a
    # platform, so they are not treated as product names.
    if subdir == "products":
        found.append(_name_from_slug(path))
        title = fields.get("title")
        if isinstance(title, str) and title:
            found.append(title)

    # Rule 3: related-document references that resolve inside products/.
    for key in _RELATED_KEYS:
        for entry in fields.get(key, []) or []:
            if not isinstance(entry, str) or not entry.endswith(".md"):
                continue
            normalized = entry.replace("\\", "/")
            has_dir = "/" in normalized
            points_at_products = "products/" in normalized
            # Bare filenames inside products/ are siblings, i.e. product docs.
            if points_at_products or (subdir == "products" and not has_dir):
                found.append(_name_from_slug(normalized))

    return found


def load_product_names(force_reload: bool = False) -> frozenset[str]:
    """
    Returns the derived product/platform names, in their corpus casing.

    Cached after the first call. Returns an empty set if the knowledge corpus
    is missing or unreadable - the fail-open direction is "suppress nothing",
    which keeps masking maximal.
    """
    global _cache
    if _cache is not None and not force_reload:
        return _cache

    names: set[str] = set()
    files_read = 0
    for subdir in _SOURCE_SUBDIRS:
        directory = os.path.join(KNOWLEDGE_DIR, subdir)
        if not os.path.isdir(directory):
            log.warning(
                "Knowledge subfolder %s not found; product-name allowlist will be "
                "incomplete (no PERSON suppression from it).", directory,
            )
            continue
        for fname in sorted(os.listdir(directory)):
            if not fname.endswith(".md"):
                continue
            files_read += 1
            for candidate in _candidates_from_file(
                os.path.join(directory, fname), subdir
            ):
                cleaned = re.sub(r"\s+", " ", candidate).strip()
                if _NAME_SHAPE.match(cleaned):
                    names.add(cleaned)
                elif cleaned:
                    log.debug(
                        "Rejected product-name candidate %r from %s "
                        "(does not match two/three-capitalised-word shape)",
                        cleaned, fname,
                    )

    if not names:
        log.warning(
            "Derived an EMPTY product-name allowlist from %s; PERSON false "
            "positives on product names will not be suppressed.", KNOWLEDGE_DIR,
        )
    else:
        log.info(
            "Derived product-name allowlist from %d knowledge document(s) in %s: %s",
            files_read, "/".join(_SOURCE_SUBDIRS), sorted(names),
        )

    _cache = frozenset(names)
    _normalized_names.cache_clear()
    return _cache


@lru_cache(maxsize=1)
def _normalized_names() -> frozenset[str]:
    return frozenset(_normalize(n) for n in load_product_names())


def _normalize(span: str) -> str:
    """
    Canonical form used for comparison: whitespace collapsed (a detected span
    can straddle a line break), edge punctuation and a trailing possessive
    removed, case folded.

    Normalization is limited to differences in how the *same* name can be
    written. It does not reorder, truncate or drop words, so it cannot turn one
    name into a different one.
    """
    text = re.sub(r"\s+", " ", span).strip()
    text = text.strip(_EDGE_PUNCT)
    text = _POSSESSIVE.sub("", text)
    text = text.strip(_EDGE_PUNCT + "'\u2019")
    return text.casefold()


def is_product_name(span: str) -> bool:
    """
    True when `span` is, in its entirety, a known product/platform name.

    Full-span equality, NOT substring containment. Containment would suppress
    any person whose name happens to contain a corpus word - "Mercury Sharma",
    "Vault Ramachandran" - and those are exactly the real names this filter
    must never touch. Equality means the blast radius of a wrong entry is that
    one exact full name and nothing else.
    """
    if not span:
        return False
    return _normalize(span) in _normalized_names()
