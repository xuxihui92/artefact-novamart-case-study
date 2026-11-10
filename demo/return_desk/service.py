"""ReturnDesk orchestration: routing, eligibility, and handoff responses."""
from datetime import date
import re
import sqlite3

from .config import DEMO_DATE, ORDER_ID, STORE
from .model import model_route
from .orders import OrderStore
from .policies import PolicyLibrary
from .text import FACT_PATTERNS, reported_facts, terms


class ReturnDesk:
    def __init__(self, database, api_key="", model="gpt-4.1-mini", policies_dir=None, seed_path=None):
        self.orders = OrderStore(database, seed_path=seed_path)
        self.database = self.orders.database
        self.api_key = api_key
        self.model = model
        self.library = PolicyLibrary(policies_dir=policies_dir)
        self.policies = self.library.policies
        self.clauses = self.library.clauses
        self.return_windows = self.library.return_windows

    def search(self, query):
        return self.library.search(query)

    def lookup(self, order_id):
        return self.orders.lookup(order_id)

    def applicable_policy(self, message, words, facts):
        return self.library.applicable_policy(message, words, facts)

    def model_route(self, message):
        return model_route(self.api_key, self.model, message)

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

        def answer(kind, text, citations=(), state=None, order=None, handoff=None):
            public_order = (
                {field: order[field] for field in ("id", "item", "channel", "status")} if order else None
            )
            return {
                "kind": kind,
                "text": text,
                "citations": [self.clauses[key] for key in citations],
                "context": state or {},
                "order": public_order,
                "handoff": handoff,
                "engine": engine,
            }

        def escalate(reason, citations=(), order=None):
            summary = {
                "store": STORE,
                "reason": reason,
                "policy": list(citations),
                "order": order["id"] if order else None,
                "next_step": "Ask the store lead to review.",
            }
            return answer("handoff", reason, citations, order=order, handoff=summary)

        if re.search(
            r"\b(ignore|override|bypass)\b|^(?:(?:please|can you|could you)\s+)?"
            r"(?:issue|process|approve|initiate)\b.{0,24}\brefund\b",
            message,
            re.I,
        ):
            return escalate(
                "The return desk can explain policy and read order status. Refund actions go through the store lead."
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
                "I cannot check the refund status of a specific transaction. The order tool only shows fulfillment status.",
                ("RET-03.1",),
            )

        order_status = re.search(
            r"\b(order status|where is (my |the )?order|ready for pickup|track (my |the )?order|has it arrived)\b",
            message,
            re.I,
        ) or (order_ids and "refund" not in words and re.search(r"\bwhere is\b", message, re.I))
        return_request = re.search(
            r"\b(check|start|want to|need to)\b.{0,32}\breturn\b|\bcan i return (my|this|it|the)\b",
            message,
            re.I,
        ) or ("return" in words and bool(order_ids))
        policy_ids = self.applicable_policy(message, words, facts)
        if len(order_ids) > 1:
            next_route = "lookup_status" if order_status else "lookup_return"
            return answer(
                "clarify",
                "I found more than one order number. Which single order should I check first?",
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
        elif policy_ids and (words & {"refund", "exchange", "marketplace"} or not (return_request or order_id)):
            route = "find_policy"
        elif return_request or (order_id and message.rstrip("?.! ").upper() == order_id):
            route = "lookup_return"
        elif policy_ids:
            route = "find_policy"
        else:
            route = "handoff"

        if self.api_key and not resumed:
            selected = self.model_route(message)
            engine = "OpenAI tool routing" if selected else "Local fallback"
            if selected and route not in ("lookup_return", "lookup_status"):
                route = selected

        if route == "find_policy" and policy_ids:
            return answer(
                "policy",
                "\n\n".join(self.clauses[key]["text"] for key in policy_ids),
                policy_ids,
            )

        if route in ("find_policy", "handoff"):
            return escalate(
                "The return desk cannot confirm this request from the available policies and order data."
            )

        if not order_id:
            return answer(
                "clarify",
                "What is the NovaMart order number? Use a sample ID such as NM-1042.",
                state={"pending": route, "facts": facts},
            )
        try:
            row = self.lookup(order_id)
        except sqlite3.Error:
            return escalate("The order tool is temporarily unavailable.")
        if row is None:
            return escalate("I could not provide an order result for this store session.")

        order = dict(row)
        if route == "lookup_status":
            return answer("order", f'{order_id} is {order["status"].lower()}.', order=order)

        if order["status"] not in ("Delivered", "Collected"):
            return answer(
                "review",
                f'{order_id} is {order["status"].lower()}. Check return eligibility once the item is received.',
                order=order,
            )

        electronics = order["category"] == "electronics"
        if facts.get("defect") is True:
            citation = "RET-02.3" if order["final_sale"] else ("RET-02.2" if electronics else "RET-03.3")
            return escalate("The reported defect requires an exception review.", (citation,), order)
        if order["final_sale"]:
            return answer(
                "review",
                "The order is marked final sale and is excluded from standard returns.",
                ("RET-02.3",),
                order=order,
            )
        if electronics and facts.get("opened") is True:
            return escalate("Opened electronics require a store-lead review.", ("RET-02.2",), order)

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
                "The recorded purchase date is after the demo date. The store lead should verify the record.",
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
            f"{timing} The reported item condition meets the standard policy. "
            "The mock order confirms the purchase record. Bring the receipt or order confirmation for the return.",
            (clause, "RET-01.2"),
            order=order,
        )
