# helpers.py
# Miscellaneous shared helper functions used across backend modules.

import re

# Smart Analysis Router - deterministic, no AI involved. Its entire job is
# avoiding unnecessary Ollama calls, so it must stay cheap: making it agentic
# would mean paying a 30-180s LLM round-trip just to decide whether to make
# one. Kept dependency-free and independently unit-testable.
#
# Any word-count cutoff above 1 is unsafe on its own: "Explain OAuth2." is
# 2 words and must NOT be skipped (it's tests/test_scenarios.md's B1 case,
# the exact regression test for the model laundering facts from retrieved
# knowledge - skipping it here would silently defeat that test). So the
# length-based fallback below only ever catches single-word input; multi-
# word prompts are only trivial via an exact phrase match or the
# small-talk vocabulary check, never by length alone.
_TRIVIAL_PHRASES = {
    "hi", "hello", "hey", "hiya", "thanks", "thank you", "thx",
    "ok", "okay", "yes", "no", "yep", "nope", "bye", "goodbye",
    "good morning", "good night", "test",
}

# Small-talk vocabulary: if EVERY word in the prompt is drawn from this set,
# the whole prompt is trivial regardless of word count (e.g. "Hi, how are
# you?" is 4 words). A word-count cap alone can't catch that without also
# catching real short questions of similar length ("Explain our Mercury
# architecture" is also 4 words) - this checks vocabulary, not length, so
# a single content word (e.g. "architecture", "mercury") breaks the match
# and the prompt correctly falls through to a real ECI classification.
_SMALL_TALK_WORDS = {
    "hi", "hello", "hey", "hiya", "hows", "how", "are", "you", "youre",
    "going", "doing", "today", "good", "morning", "night", "evening",
    "thanks", "thank", "welcome", "bye", "goodbye", "ok", "okay", "yes",
    "no", "yep", "nope", "please", "fine", "great", "test",
}


def is_trivial_prompt(prompt: str) -> bool:
    """
    True if a prompt is trivial enough to skip the ECI (Ollama) call
    entirely - empty, a bare greeting/filler phrase or small-talk
    sentence, or very short. routes.py only skips ECI when this is True
    AND Presidio found zero entities, so anything Presidio flags still
    gets the full ECI pass regardless of length.
    """
    stripped = prompt.strip()
    if not stripped:
        return True

    normalized = stripped.lower().rstrip("!.?, ")
    if normalized in _TRIVIAL_PHRASES:
        return True

    words = re.findall(r"[a-z0-9]+", normalized.replace("'", ""))
    if words and all(word in _SMALL_TALK_WORDS for word in words):
        return True

    return len(words) == 1
