"""Redact personal data before it is sent to a model."""
import re

from .config import ORDER_ID

ORDER_TOKEN = "<demo order reference>"
EMAIL_TOKEN = "<email>"
PHONE_TOKEN = "<phone>"
CARD_TOKEN = "<card>"
NAME_TOKEN = "<name>"

EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
PHONE = re.compile(
    r"(?<!\d)(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]\d{3}[\s.-]\d{4}(?!\d)"
)
PHONE_INTL = re.compile(r"(?<!\w)\+\d{10,15}(?!\d)")
HONORIFIC = re.compile(
    r"\b(?:Mr|Mrs|Ms|Miss|Dr|Prof)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b"
)
# The cue is case-insensitive. The name itself stays case-sensitive so
# "I am not sure" is not treated as a name.
NAME_CUE = re.compile(
    r"((?i:\b(?:my name is|name is|i am|i'm|this is|customer(?:'s)? name is)\s+))"
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b"
)
ZH_NAME = re.compile(r"(?:我叫|我的名字是|姓名[:：]|客户(?:姓名)?是)[\u4e00-\u9fff]{2,4}")


def redact(text):
    """Replace emails, cards, phones, order ids, and cued names.

    The same string redacts to itself again. Order ids become the historical
    demo token so a model request never carries the raw NM-#### value.
    """
    if not isinstance(text, str) or not text:
        return "" if text is None else str(text)
    cleaned = EMAIL.sub(EMAIL_TOKEN, text)
    cleaned = ORDER_ID.sub(ORDER_TOKEN, cleaned)
    cleaned = CARD.sub(CARD_TOKEN, cleaned)
    cleaned = PHONE.sub(PHONE_TOKEN, cleaned)
    cleaned = PHONE_INTL.sub(PHONE_TOKEN, cleaned)
    cleaned = HONORIFIC.sub(NAME_TOKEN, cleaned)
    cleaned = NAME_CUE.sub(lambda match: match.group(1) + NAME_TOKEN, cleaned)
    cleaned = ZH_NAME.sub(NAME_TOKEN, cleaned)
    return cleaned
