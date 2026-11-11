"""Keyword normalization and item-condition fact extraction."""
import re

from .config import ALIASES, STOP, TOKENS

FACT_PATTERNS = {
    "opened": re.compile(
        r"\b(?:(?P<yes>(?:not |isn['’]t )(?:factory[ -])?sealed|not unopened|seal (?:is )?broken|opened|unsealed)|"
        r"(?P<no>not (?:been )?opened|never (?:been )?opened|hasn['’]t (?:been )?opened|unopened|sealed))\b",
        re.I,
    ),
    "used": re.compile(
        r"\b(?:(?P<yes>not unused|used)|(?P<no>not used|never (?:been )?used|unused))\b",
        re.I,
    ),
    "resalable": re.compile(
        r"\b(?:(?P<no>not (?:in )?resalable|unsalable)|(?P<yes>resalable))\b",
        re.I,
    ),
    "original_packaging": re.compile(
        r"\b(?:(?P<no>not in (?:its |the )?original packaging|without (?:its |the )?original packaging|"
        r"no original packaging)|(?P<yes>in (?:its |the )?original packaging))\b",
        re.I,
    ),
    "defect": re.compile(
        r"\b(?:(?P<no>not (?:defective|damaged|broken)|no defects?)|(?P<yes>defect(?:ive|s)?|damaged|broken))\b",
        re.I,
    ),
}


def terms(text):
    return {ALIASES.get(word, word) for word in TOKENS.findall(text.lower()) if word not in STOP}


def reported_facts(message):
    facts = {}
    # Treat uncertain or conditional descriptions as missing information.
    if re.search(r"\b(?:not sure|unsure|maybe|might be|if it)\b", message, re.I):
        return facts
    for field, pattern in FACT_PATTERNS.items():
        values = {match.lastgroup == "yes" for match in pattern.finditer(message)}
        if values:
            facts[field] = values.pop() if len(values) == 1 else None
    return facts
