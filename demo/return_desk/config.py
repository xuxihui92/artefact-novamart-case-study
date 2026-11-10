"""Shared constants for the NovaMart return-desk demo."""
from datetime import date
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
DEMO_DATE = date(2026, 11, 9)
STORE = "STORE-014"
ORDER_ID = re.compile(r"\bNM-\d{4}\b", re.I)
TOKENS = re.compile(r"[a-z0-9]+")
STOP = set(
    "a an and are at can could do does for how i in is it me my of on or the this to what when where with you your".split()
)
ALIASES = {
    "refunds": "refund",
    "returns": "return",
    "returned": "return",
    "exchanges": "exchange",
    "receipt": "receipt",
    "headphones": "electronics",
    "laptop": "electronics",
    "opened": "open",
    "unopened": "open",
    "purchased": "purchase",
    "bought": "purchase",
    "time": "days",
    "defective": "defect",
    "coupons": "coupon",
    "promotions": "promotion",
    "discounts": "discount",
    "membership": "member",
    "members": "member",
    "deliveries": "delivery",
    "shipment": "delivery",
    "shipping": "delivery",
    "carrier": "delivery",
    "pricematch": "price",
}
TOOLS = {
    "lookup_return": "Check the return eligibility of a specific purchase or help check the user's own purchase.",
    "lookup_status": "Check a specific order's status, delivery, or pickup readiness.",
    "find_policy": (
        "Answer a general question about NovaMart returns, refunds, exchanges, "
        "price match, promotions, pickup holds, or delivery exceptions."
    ),
    "handoff": "Handle unsupported topics, policy overrides, or actions such as issuing a refund.",
}
CLAUSE_HEADER = re.compile(r"\[(RET-\d{2}\.[1-9]\d*)\] (\S.*)")
WINDOW = re.compile(r"Return window: ([1-9]\d*) calendar days from purchase\.")
REQUIRED_CLAUSES = {
    "RET-01.1",
    "RET-01.2",
    "RET-01.3",
    "RET-02.1",
    "RET-02.2",
    "RET-02.3",
    "RET-03.1",
    "RET-03.2",
    "RET-03.3",
    "RET-04.1",
    "RET-04.2",
    "RET-04.3",
    "RET-05.1",
    "RET-05.2",
    "RET-05.3",
}
