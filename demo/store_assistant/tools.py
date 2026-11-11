"""Tool schemas and argument checks for the store assistant.

The model may call these functions. This module decides whether the arguments
are usable. It does not decide eligibility.
"""
import json
import re

from .config import ORDER_ID
from .redact import ORDER_TOKEN

CONDITION_FIELDS = ("opened", "used", "resalable", "original_packaging", "defect")
ACCEPTED_TOOLS = frozenset(
    {
        "search_policy",
        "lookup_order",
        "report_item_condition",
        "handoff",
        "find_policy",
        "lookup_return",
        "lookup_status",
    }
)
FACT_CUES = {
    "opened": re.compile(r"open|seal|unopened", re.I),
    "used": re.compile(r"use|used|unused|worn", re.I),
    "resalable": re.compile(r"resal", re.I),
    "original_packaging": re.compile(r"packag", re.I),
    "defect": re.compile(r"defect|broken|damag", re.I),
}


def _bool_property(description):
    return {"type": "boolean", "description": description}


def tool_specs():
    """OpenAI Chat Completions tool definitions with real parameters.

    additionalProperties and strict mode are omitted on the wire. Gemini's
    OpenAI-compatible endpoint has rejected those schema knobs; unknown keys
    are rejected in validate_tool_call instead.
    """
    condition = {
        "opened": _bool_property("True when the customer says the item was opened or unsealed."),
        "used": _bool_property("True when the customer says the item was used."),
        "resalable": _bool_property("True when the customer says the item is resalable."),
        "original_packaging": _bool_property("True when the item is in its original packaging."),
        "defect": _bool_property("True when the customer reports a defect or damage."),
    }
    order_id = {
        "type": "string",
        "description": (
            "Order id exactly as the customer wrote it. "
            "If it was redacted, pass <demo order reference> or omit this field."
        ),
    }
    specs = [
        (
            "search_policy",
            (
                "Look up NovaMart policy for a general question about returns, refunds, "
                "exchanges, price match, coupons, member pricing, pickup holds, or delivery. "
                "query must be short English keywords, "
                "for example: refund method, return window, opened electronics, final sale, "
                "price match, pickup hold, damaged on arrival."
            ),
            {"query": {"type": "string", "description": "English policy keywords."}},
            ["query"],
        ),
        (
            "lookup_order",
            (
                "Look up one NovaMart order to check return eligibility or fulfillment status. "
                "Set condition fields only when the customer actually reported them; otherwise omit them."
            ),
            {
                "order_id": order_id,
                "purpose": {
                    "type": "string",
                    "enum": ["return_eligibility", "order_status"],
                    "description": "return_eligibility or order_status.",
                },
                **condition,
            },
            ["purpose"],
        ),
        (
            "report_item_condition",
            "Record item condition the customer just reported. Use this when they are not asking a new question.",
            {"order_id": order_id, **condition},
            [],
        ),
        (
            "handoff",
            (
                "The question is outside the store assistant, asks to issue a refund or override a rule, "
                "or there is not enough policy evidence. Do not use this to approve a return."
            ),
            {"reason": {"type": "string", "description": "Short reason, with no personal data."}},
            ["reason"],
        ),
    ]
    tools = []
    for name, description, properties, required in specs:
        parameters = {"type": "object", "properties": properties}
        if required:
            parameters["required"] = required
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                },
            }
        )
    return tools


def route_name(tool_name, arguments):
    """Map a tool name to a desk route. Unknown names return None."""
    arguments = arguments or {}
    if tool_name == "lookup_order":
        if arguments.get("purpose") == "order_status":
            return "lookup_status"
        return "lookup_return"
    return {
        "search_policy": "find_policy",
        "find_policy": "find_policy",
        "lookup_return": "lookup_return",
        "lookup_status": "lookup_status",
        "report_item_condition": "lookup_return",
        "handoff": "handoff",
    }.get(tool_name)


def _canonical(name, arguments):
    arguments = dict(arguments)
    if name == "find_policy":
        return "search_policy", arguments
    if name == "lookup_status":
        arguments.setdefault("purpose", "order_status")
        return "lookup_order", arguments
    if name == "lookup_return":
        arguments.setdefault("purpose", "return_eligibility")
        return "lookup_order", arguments
    return name, arguments


def _load_arguments(arguments):
    if arguments is None:
        return {}
    if isinstance(arguments, str):
        if not arguments.strip():
            return {}
        loaded = json.loads(arguments)
        if not isinstance(loaded, dict):
            raise ValueError("arguments must be an object")
        return loaded
    if isinstance(arguments, dict):
        return arguments
    raise ValueError("arguments must be an object")


def _resolve_order_id(value, message):
    found = list(dict.fromkeys(match.upper() for match in ORDER_ID.findall(message or "")))
    if value is None or value == "" or value == ORDER_TOKEN:
        return found[0] if len(found) == 1 else None
    if not isinstance(value, str) or ORDER_ID.fullmatch(value.strip()) is None:
        raise ValueError("order_id is not a NovaMart order id")
    normalized = value.strip().upper()
    if normalized not in found:
        raise ValueError("order_id was not in the customer message")
    return normalized


def validate_tool_call(name, arguments, message):
    """Return a normalized tool call, or raise ValueError.

    order_id is accepted only when that exact id appears in the customer
    message. A model cannot point the lookup at a different order.
    """
    if not isinstance(name, str) or name not in ACCEPTED_TOOLS:
        raise ValueError("unknown tool")
    arguments = _load_arguments(arguments)
    name, arguments = _canonical(name, arguments)
    if name == "search_policy":
        allowed = {"query"}
    elif name == "handoff":
        allowed = {"reason"}
    elif name == "lookup_order":
        allowed = {"order_id", "purpose", *CONDITION_FIELDS}
    else:
        allowed = {"order_id", *CONDITION_FIELDS}
    unknown = set(arguments) - allowed
    if unknown:
        raise ValueError("unknown argument: " + ", ".join(sorted(unknown)))

    facts = {}
    for field in CONDITION_FIELDS:
        if field not in arguments or arguments[field] is None:
            continue
        if not isinstance(arguments[field], bool):
            raise ValueError(field + " must be a boolean")
        facts[field] = arguments[field]

    query = None
    reason = None
    order_id = None
    purpose = None
    if name == "search_policy":
        query = arguments.get("query")
        if not isinstance(query, str):
            raise ValueError("query must be a string")
        query = query.replace("<<<", "").replace(">>>", "").strip()
        if not 1 <= len(query) <= 200:
            raise ValueError("query length")
        route = "find_policy"
    elif name == "handoff":
        reason = arguments.get("reason")
        if not isinstance(reason, str):
            raise ValueError("reason must be a string")
        reason = reason.strip()
        if not 1 <= len(reason) <= 300:
            raise ValueError("reason length")
        route = "handoff"
    elif name == "lookup_order":
        purpose = arguments.get("purpose")
        if purpose not in ("return_eligibility", "order_status"):
            raise ValueError("purpose")
        order_id = _resolve_order_id(arguments.get("order_id"), message)
        route = "lookup_status" if purpose == "order_status" else "lookup_return"
    else:
        order_id = _resolve_order_id(arguments.get("order_id"), message)
        route = "lookup_return"

    return {
        "name": name,
        "route": route,
        "query": query,
        "reason": reason,
        "order_id": order_id,
        "purpose": purpose,
        "facts": facts,
    }


def merge_facts(local, model_facts, message):
    """Fill condition fields the code did not already extract.

    A fact the regex already set is kept, so the model cannot flip "I opened it"
    to unopened. A model fact is used only when the message itself mentions that
    condition, so the model cannot invent "unused and resalable" on a bare order
    question.
    """
    merged = dict(local or {})
    if not model_facts:
        return merged
    for field, value in model_facts.items():
        if field not in FACT_CUES or not isinstance(value, bool):
            continue
        if field in merged:
            continue
        if FACT_CUES[field].search(message or ""):
            merged[field] = value
    return merged


def route_locked(local_route, policy_ids):
    """Order lookups and already-selected policy answers stay with the code."""
    if local_route in ("lookup_return", "lookup_status"):
        return True
    if local_route == "find_policy" and policy_ids:
        return True
    return False
