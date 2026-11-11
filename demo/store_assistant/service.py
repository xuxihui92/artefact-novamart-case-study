"""Store assistant orchestration.

The model and the rules have different jobs. When a provider key is configured,
the model may call one tool to interpret the question and may phrase the reply.
This class still decides. Return windows, final sale, opened electronics, and
store-scoped lookup are applied below, and a model reply that disagrees is discarded.
Follow-up turns such as "Yes" stay on the local state machine.
"""
from datetime import date
import re
import sqlite3

from .config import DEFAULT_MODEL, DEMO_DATE, ORDER_ID, ROUTES, STORE
from .model import OpenAIClient, answer_is_grounded, model_route, render_tool_content
from .orders import OrderStore
from .policies import PolicyLibrary
from .redact import ORDER_TOKEN, redact
from .text import FACT_PATTERNS, reported_facts, terms
from .tools import merge_facts, route_locked, validate_tool_call

KIND_DECISION = {
    "policy": "explain",
    "clarify": "clarify",
    "eligible": "yes",
    "review": "no",
    "order": "status",
    "handoff": "handoff",
}


class StoreAssistant:
    def __init__(
        self,
        database,
        api_key="",
        model=None,
        policies_dir=None,
        seed_path=None,
        base_url=None,
        provider="openai",
        client=None,
        min_interval=None,
    ):
        self.orders = OrderStore(database, seed_path=seed_path)
        self.database = self.orders.database
        self.api_key = api_key
        self.model = model or DEFAULT_MODEL
        self.provider = provider or "openai"
        self.base_url = base_url
        self.library = PolicyLibrary(policies_dir=policies_dir)
        self.policies = self.library.policies
        self.clauses = self.library.clauses
        self.return_windows = self.library.return_windows
        self.client = client
        if self.client is None and api_key:
            interval = min_interval
            if interval is None:
                interval = 1.0 if self.provider == "gemini" else 0.0
            try:
                self.client = OpenAIClient(
                    api_key,
                    self.model,
                    base_url=base_url,
                    min_interval=interval,
                    provider=self.provider,
                )
            except ValueError:
                self.client = None

    def search(self, query):
        return self.library.search(query)

    def lookup(self, order_id):
        return self.orders.lookup(order_id)

    def applicable_policy(self, message, words, facts):
        return self.library.applicable_policy(message, words, facts)

    def model_route(self, message):
        return model_route(self.api_key, self.model, message, base_url=self.base_url)

    def _propose(self, message):
        redacted = redact(message)
        if self.client is not None:
            try:
                return self.client.propose(redacted)
            except (OSError, ValueError, TypeError):
                return None
        return self.model_route(redacted)

    def _rewrite(self, payload, message, proposal):
        if self.client is None or not proposal or not proposal.get("assistant_message"):
            return payload
        try:
            written = self.client.complete(
                proposal.get("messages") or [],
                proposal["assistant_message"],
                redact(render_tool_content(payload, message)),
            )
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            return payload
        if not written or not answer_is_grounded(
            written,
            payload["decision"],
            [clause["id"] for clause in payload["citations"]],
            order_visible=payload["order"] is not None,
            order_status=(payload["order"] or {}).get("status"),
        ):
            return payload
        shown = written.strip()
        if payload["order"] is not None:
            shown = shown.replace(ORDER_TOKEN, payload["order"]["id"])
        else:
            shown = shown.replace(ORDER_TOKEN, "that order")
        payload["text"] = shown
        payload["engine"] = "Gemini" if self.provider == "gemini" else "OpenAI"
        return payload

    def chat(self, message, context=None):
        context = context or {}
        order_ids = list(dict.fromkeys(match.upper() for match in ORDER_ID.findall(message)))
        order_id = order_ids[0] if len(order_ids) == 1 else None
        words = terms(message)
        facts = reported_facts(message)
        pending = context.get("pending")
        previous_order = context.get("order")
        if not isinstance(previous_order, str) or not ORDER_ID.fullmatch(previous_order):
            previous_order = None
        prior_facts = context.get("facts")
        if not isinstance(prior_facts, dict):
            prior_facts = {}
        prior_facts = {
            field: prior_facts[field]
            for field in FACT_PATTERNS
            if isinstance(prior_facts.get(field), bool)
        }

        engine = "Local rules"
        route = "handoff"
        proposal = None
        search_query = None

        def answer(kind, text, citations=(), state=None, order=None, handoff=None, decision=None):
            public_order = (
                {field: order[field] for field in ("id", "item", "channel", "status")} if order else None
            )
            payload = {
                "kind": kind,
                "text": text,
                "citations": [self.clauses[key] for key in citations],
                "context": state or {},
                "order": public_order,
                "handoff": handoff,
                "engine": engine,
                "route": route,
                "decision": decision or KIND_DECISION[kind],
            }
            return self._rewrite(payload, message, proposal)

        def escalate(reason, citations=(), order=None, action=None, decision=None):
            summary = {
                "store": STORE,
                "reason": reason,
                "policy": list(citations),
                "order": order["id"] if order else None,
                "next_step": (
                    "Contact a remote office associate to confirm the next step."
                    if action == "remote_chat"
                    else "Ask the store lead to review."
                ),
                "action": action or "copy_summary",
            }
            return answer(
                "handoff",
                reason,
                citations,
                order=order,
                handoff=summary,
                decision=decision or "handoff",
            )

        if re.search(
            r"\b(ignore|override|bypass)\b|^(?:(?:please|can you|could you)\s+)?"
            r"(?:issue|process|approve|initiate)\b.{0,24}\brefund\b",
            message,
            re.I,
        ):
            return escalate(
                "This assistant explains policy and reads order status. Refunds are handled by the store lead."
            )

        refund_status = re.search(
            r"\b(?:refund status|status of (?:my |the )?refund|(?:check|track) (?:my |the )?refund|"
            r"has (?:my |the )?refund been (?:issued|processed)|did (?:my |the )?refund go through)\b",
            message,
            re.I,
        ) or (
            re.search(r"\bwhere is (?:my |the )?refund\b", message, re.I)
            and not words & {"sent", "returned", "deposited", "method"}
        )
        if refund_status:
            return escalate(
                "I can't check the refund status of a specific payment. Order lookup only shows fulfillment status.",
                ("RET-03.1",),
            )

        pickup_hold_policy = "pickup" in words and re.search(
            r"\b(?:how long|hold|holds|held|policy)\b", message, re.I
        )
        order_status = (
            re.search(
                r"\b(order status|where is (my |the )?order|ready for pickup|track (my |the )?order|has it arrived)\b",
                message,
                re.I,
            )
            or (order_ids and "refund" not in words and re.search(r"\bwhere is\b", message, re.I))
        ) and not pickup_hold_policy
        return_request = re.search(
            r"\b(check|start|want to|need to)\b.{0,32}\breturn\b|\bcan i return (my|this|it|the)\b",
            message,
            re.I,
        ) or ("return" in words and bool(order_ids))
        policy_ids = self.applicable_policy(message, words, facts)
        if len(order_ids) > 1:
            next_route = "lookup_status" if order_status else "lookup_return"
            route = "clarify"
            return answer(
                "clarify",
                "More than one order number was found. Which order should I check first?",
                state={"pending": next_route},
            )

        expected = context.get("expected")
        if not isinstance(expected, str) or expected not in FACT_PATTERNS:
            expected = None
        yes_no = message.lower().rstrip(".! ").strip()
        is_condition_reply = (
            pending == "condition"
            and previous_order
            and (not order_id or order_id == previous_order)
            and not order_status
            and "refund" not in words
            and (facts or (expected and yes_no in ("yes", "no")))
        )

        resumed = False
        if is_condition_reply:
            if yes_no in ("yes", "no") and expected:
                facts[expected] = yes_no == "yes"
            facts = {**prior_facts, **facts}
            route, order_id, resumed = "lookup_return", previous_order, True
        elif pending in ("lookup_return", "lookup_status") and order_id and not (
            order_status or return_request or policy_ids
        ):
            route, resumed = pending, True
            if route == "lookup_return":
                facts = {**prior_facts, **facts}
        elif order_status:
            route = "lookup_status"
        elif policy_ids and (
            words
            & {
                "refund",
                "exchange",
                "marketplace",
                "coupon",
                "promotion",
                "promo",
                "member",
                "discount",
                "price",
                "delivery",
                "pickup",
                "hold",
                "holds",
            }
            or not (return_request or order_id)
        ):
            route = "find_policy"
        elif return_request or (order_id and message.rstrip("?.! ").upper() == order_id):
            route = "lookup_return"
        elif policy_ids:
            route = "find_policy"
        else:
            route = "handoff"

        # Language understanding. A locked order or policy route is not replaced.
        # Arguments can still fill a condition the code did not already extract.
        local_route = route
        original_policy_ids = policy_ids
        if self.api_key and not resumed:
            raw = self._propose(message)
            understood = None
            if isinstance(raw, str):
                selected = raw if raw in ROUTES else None
                if not selected:
                    engine = "Local fallback"
                else:
                    engine = "OpenAI tool routing"
                    if not route_locked(local_route, original_policy_ids):
                        route = selected
            elif isinstance(raw, dict):
                try:
                    understood = validate_tool_call(raw.get("name"), raw.get("arguments") or {}, message)
                except (TypeError, ValueError):
                    understood = None
                if understood is None:
                    engine = "Local fallback"
                else:
                    label = "Gemini" if self.provider == "gemini" else "OpenAI"
                    engine = label + " tool routing"
                    proposal = raw
                    facts = merge_facts(facts, understood["facts"], message)
                    refreshed = self.applicable_policy(message, words, facts)
                    if refreshed:
                        policy_ids = refreshed
                    if not route_locked(local_route, original_policy_ids):
                        route = understood["route"]
                    search_query = understood.get("query")
            else:
                engine = "Local fallback"

        if route == "find_policy" and not policy_ids and search_query:
            found = [clause["id"] for clause in self.search(search_query)]
            if found:
                policy_ids = (found[0],)

        if route == "find_policy" and policy_ids:
            return answer(
                "policy",
                "\n\n".join(self.clauses[key]["text"] for key in policy_ids),
                policy_ids,
            )

        if route in ("find_policy", "handoff"):
            route = "handoff"
            return escalate(
                "I can't match this question to a policy or an order. "
                "Contact a remote office associate to confirm.",
                action="remote_chat",
            )

        if not order_id:
            return answer(
                "clarify",
                "What is the order number? For this demo, try NM-1042.",
                state={"pending": route, "facts": facts},
            )
        try:
            row = self.lookup(order_id)
        except sqlite3.Error:
            return escalate("Order lookup is temporarily unavailable. Try again, or ask the store lead.")
        if row is None:
            return escalate("I can't show an order result for this store.")

        order = dict(row)
        if route == "lookup_status":
            return answer("order", f'{order_id} is {order["status"].lower()}.', order=order)

        if order["status"] not in ("Delivered", "Collected"):
            return answer(
                "review",
                f'{order_id} is {order["status"].lower()}. Check the return once the customer has the item.',
                order=order,
                decision="pending",
            )

        electronics = order["category"] == "electronics"
        if facts.get("defect") is True:
            citation = "RET-02.3" if order["final_sale"] else ("RET-02.2" if electronics else "RET-03.3")
            return escalate(
                "This defect needs a store-lead review.",
                (citation,),
                order,
                decision="no",
            )
        if order["final_sale"]:
            return answer(
                "review",
                "This item is final sale and is not covered by the standard return policy.",
                ("RET-02.3",),
                order=order,
            )
        if electronics and facts.get("opened") is True:
            return escalate(
                "Opened electronics need a store-lead review.",
                ("RET-02.2",),
                order,
                decision="no",
            )

        clause, window = self.return_windows[order["category"]]
        age = (DEMO_DATE - date.fromisoformat(order["purchased_on"])).days
        if age > window:
            return answer(
                "review",
                f"This purchase is {age} days old and falls outside the {window}-day return window.",
                (clause,),
                order=order,
            )
        if age < 0:
            return escalate(
                "The purchase date is after the demo date. Ask the store lead to check the record.",
                order=order,
            )

        timing = f"This purchase is within the {window}-day return window ({age} days since purchase)."
        if electronics:
            required = {
                "opened": (False, "Has the item been opened?"),
                "original_packaging": (True, "Is the item in its original packaging?"),
            }
            condition_text = "Electronics must be unopened and in their original packaging."
        else:
            required = {
                "used": (False, "Has the item been used?"),
                "resalable": (True, "Is the item in resalable condition?"),
            }
            condition_text = "General merchandise must be unused and resalable."

        if any(facts.get(field) is not None and facts[field] != value for field, (value, _) in required.items()):
            return answer(
                "review",
                f"{timing} The reported condition falls outside the standard return rules. {condition_text}",
                (clause,),
                order=order,
            )

        for field, (_, question) in required.items():
            if facts.get(field) is None:
                state = {"pending": "condition", "order": order_id, "facts": facts, "expected": field}
                return answer("clarify", f"{timing} {question}", (clause,), state, order)

        return answer(
            "eligible",
            f"{timing} The reported condition meets the standard policy. "
            "Bring the receipt or order confirmation to complete the return.",
            (clause, "RET-01.2"),
            order=order,
        )
