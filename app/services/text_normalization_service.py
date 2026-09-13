"""Central text normalization helpers for retrieval and keyword matching."""

import re

GERMAN_CHARACTER_REPLACEMENTS = (
    ("\u00e4", "ae"),
    ("\u00f6", "oe"),
    ("\u00fc", "ue"),
    ("\u00df", "ss"),
    ("\u00c4", "Ae"),
    ("\u00d6", "Oe"),
    ("\u00dc", "Ue"),
    ("\u00c3\u00a4", "ae"),
    ("\u00c3\u00b6", "oe"),
    ("\u00c3\u00bc", "ue"),
    ("\u00c3\u0178", "ss"),
    ("\u00c3\u0192\u00c2\u00a4", "ae"),
    ("\u00c3\u0192\u00c2\u00b6", "oe"),
    ("\u00c3\u0192\u00c2\u00bc", "ue"),
)
DASH_TRANSLATION = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
    }
)
TECHNICAL_SYNONYM_GROUPS = (
    ("frequenzumrichter", ("fu", "frequenzumrichter")),
    ("sps", ("sps", "plc")),
    ("sensor", ("sensor", "naeherungsschalter")),
    ("notaus", ("not-aus", "notaus", "not aus", "emergency stop", "emergencystop")),
    ("motor", ("motor", "antrieb")),
)
SHORT_TECHNICAL_TOKENS = {"fu"}
TOKEN_PATTERN = re.compile(r"[^a-z0-9-]+")


def normalize_text(value, lowercase=True, fold_german=True):
    """Return whitespace-normalized text with optional casing and German folding."""
    text = str(value or "").translate(DASH_TRANSLATION)
    text = " ".join(text.strip().split())
    if lowercase:
        text = text.lower()
    if fold_german:
        text = _fold_german_characters(text)
    return text


def tokenize_text(value, min_length=3, expand_synonyms=True):
    """Return normalized retrieval tokens for local matching."""
    normalized = normalize_query(value) if expand_synonyms else normalize_text(value)
    tokens = set()
    for token in TOKEN_PATTERN.sub(" ", normalized).split():
        _add_token(tokens, token, min_length)
    return tokens


def normalize_query(value):
    """Return a retrieval-oriented query string enriched with technical synonyms."""
    normalized = normalize_text(value)
    expansions = expand_german_synonyms(normalized)
    if not expansions:
        return normalized
    parts = [normalized]
    parts.extend(item for item in expansions if item and item != normalized)
    return " ".join(dict.fromkeys(parts))


def expand_german_synonyms(value):
    """Return deterministic technical synonym expansions found in text."""
    normalized = normalize_text(value)
    if not normalized:
        return ()
    tokens = set(TOKEN_PATTERN.sub(" ", normalized).split())
    compact_tokens = {_compact_term(token) for token in tokens}
    padded_text = f" {normalized} "
    expansions = []
    for canonical, aliases in TECHNICAL_SYNONYM_GROUPS:
        if _group_matches(padded_text, tokens, compact_tokens, aliases):
            _append_unique(expansions, canonical)
            for alias in aliases:
                _append_unique(expansions, normalize_text(alias))
    return tuple(expansions)


def _fold_german_characters(text):
    """Return text with German characters and common mojibake variants folded."""
    folded = text
    for source, target in GERMAN_CHARACTER_REPLACEMENTS:
        folded = folded.replace(source, target)
    return folded


def _group_matches(padded_text, tokens, compact_tokens, aliases):
    """Return whether any alias from a synonym group appears in normalized text."""
    for alias in aliases:
        normalized_alias = normalize_text(alias)
        compact_alias = _compact_term(normalized_alias)
        if normalized_alias in tokens or compact_alias in compact_tokens:
            return True
        if f" {normalized_alias} " in padded_text:
            return True
    return False


def _add_token(tokens, token, min_length):
    """Add a normalized token and its compact hyphen variant when useful."""
    if len(token) >= min_length or token in SHORT_TECHNICAL_TOKENS:
        tokens.add(token)
    if "-" not in token:
        return
    for part in token.split("-"):
        if len(part) >= min_length or part in SHORT_TECHNICAL_TOKENS:
            tokens.add(part)
    compact = token.replace("-", "")
    if len(compact) >= min_length or compact in SHORT_TECHNICAL_TOKENS:
        tokens.add(compact)


def _compact_term(value):
    """Return a term without separators for spelling-variant matching."""
    return TOKEN_PATTERN.sub("", str(value or ""))


def _append_unique(items, value):
    """Append a value once while preserving insertion order."""
    if value and value not in items:
        items.append(value)
