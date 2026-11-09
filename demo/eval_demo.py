"""Run deterministic checks against a temporary copy of the synthetic database."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app import ReturnDesk


class ReturnDeskChecks(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.desk = ReturnDesk(Path(temp.name) / "test.sqlite3")

    def test_search_finds_refund_clause(self):
        self.assertEqual(len(self.desk.policies), 3)
        self.assertEqual(self.desk.search("refund method")[0]["id"], "RET-03.1")
        self.assertEqual(self.desk.search("unrelated astronomy"), [])

    def test_order_number_followup(self):
        first = self.desk.chat("I need to return an item.")
        self.assertEqual(first["kind"], "clarify")
        result = self.desk.chat("NM-1042", first["context"])
        self.assertEqual(result["kind"], "eligible")
        self.assertIn("30-day", result["text"])
        self.assertEqual(result["citations"][0]["id"], "RET-01.1")

    def test_electronics_condition_changes_outcome(self):
        first = self.desk.chat("Can I return order NM-1043?")
        self.assertEqual(first["kind"], "clarify")
        opened = self.desk.chat("I opened it.", first["context"])
        sealed = self.desk.chat("It is unopened.", first["context"])
        self.assertEqual(opened["kind"], "handoff")
        self.assertEqual(opened["handoff"]["policy"], ["RET-02.2"])
        self.assertEqual(sealed["kind"], "eligible")

    def test_collects_order_number_without_losing_item_condition(self):
        first = self.desk.chat("Can I return my headphones? I opened them.")
        self.assertEqual(first["kind"], "clarify")
        result = self.desk.chat("The order is NM-1043", first["context"])
        self.assertEqual(result["handoff"]["policy"], ["RET-02.2"])

    def test_window_and_final_sale(self):
        expired = self.desk.chat("Can I return NM-1044?")
        final_sale = self.desk.chat("Can I return NM-1046?")
        self.assertIn("outside the 30-day", expired["text"])
        self.assertEqual(final_sale["citations"][0]["id"], "RET-02.3")

    def test_order_status_uses_database(self):
        result = self.desk.chat("What is the order status for NM-1045?")
        self.assertEqual(result["kind"], "order")
        self.assertEqual(result["order"]["status"], "Ready for pickup")
        self.assertNotIn("store_id", result["order"])

    def test_cross_store_order_is_indistinguishable_from_missing_order(self):
        denied = self.desk.chat("Order status for NM-2042")
        missing = self.desk.chat("Order status for NM-9999")
        self.assertEqual(denied, missing)
        self.assertIsNone(denied["order"])

    def test_refund_is_policy_guidance(self):
        result = self.desk.chat("Where is my refund sent?")
        self.assertEqual(result["kind"], "policy")
        self.assertEqual(result["citations"][0]["id"], "RET-03.1")

    def test_unknown_topic_hands_off_without_claim(self):
        result = self.desk.chat("Is the cafeteria open?")
        self.assertEqual(result["kind"], "handoff")
        self.assertEqual(result["citations"], [])

    def test_optional_model_path_still_enforces_store_scope(self):
        self.desk.api_key = "test-only"
        with patch.object(self.desk, "model_route", return_value="lookup_status"):
            result = self.desk.chat("Please check NM-2042")
        self.assertEqual(result["engine"], "OpenAI tool routing")
        self.assertEqual(result["kind"], "handoff")
        self.assertIsNone(result["order"])

    def test_model_failure_falls_back_to_local_rules(self):
        self.desk.api_key = "test-only"
        with patch.object(self.desk, "model_route", return_value=None):
            result = self.desk.chat("Where is my refund sent?")
        self.assertEqual(result["engine"], "Local fallback")
        self.assertEqual(result["citations"][0]["id"], "RET-03.1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
