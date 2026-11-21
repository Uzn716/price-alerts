"""Title matching: decides which tracked part (if any) a product title is.

Titles are split into tokens at every letter/digit boundary, so
"RTX5070Ti", "RTX 5070 Ti" and "rtx-5070-ti" all become [rtx, 5070, ti].
A match word like "9800x3d" must appear as a contiguous run of tokens.
"""
from __future__ import annotations

import re

from .models import Part

_TOKEN_RE = re.compile(r"[a-z]+|\d+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _contains_run(tokens: list[str], run: list[str]) -> bool:
    if not run:
        return False
    n = len(run)
    for i in range(len(tokens) - n + 1):
        if tokens[i : i + n] == run:
            return True
    return False


def phrase_in(tokens: list[str], phrase: str) -> bool:
    """True if every word of the phrase appears (each as a contiguous token run)."""
    words = phrase.split()
    return bool(words) and all(_contains_run(tokens, tokenize(w)) for w in words)


def any_phrase_in(tokens: list[str], phrases: list[str]) -> bool:
    return any(phrase_in(tokens, p) for p in phrases)


def match_part(title: str, parts: list[Part]) -> Part | None:
    """Return the first part whose match phrases fit the title and excludes don't."""
    tokens = tokenize(title)
    for part in parts:
        if any_phrase_in(tokens, part.match) and not any_phrase_in(tokens, part.exclude):
            return part
    return None
