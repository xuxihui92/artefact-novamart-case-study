"""Acceptance and orchestration tests for StoreAssistant.chat."""
from pathlib import Path
import shutil
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from store_assistant import StoreAssistant
from store_assistant.config import ROOT


class StoreAssistantChecks(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.desk = StoreAssistant(Path(temp.name) / "test.sqlite3")

    def test_search_finds_refund_clause(self):
        self.assertEqual(len(self.desk.policies), 5)
        self.assertEqual(self.desk.search("refund method")[0]["id"], "RET-03.1")
        self.assertEqual(self.desk.search("unrelated astronomy"), [])

    def test_new_policy_topics_are_grounded(self):
        price = self.desk.chat("Can you price match a local competitor?")
        pickup = self.desk.chat("How long does the store hold pickup orders?")
        self.assertEqual(price["kind"], "policy")
        self.assertEqual(price["citations"][0]["id"], "RET-04.1")
        self.assertEqual(pickup["kind"], "policy")
        self.assertEqual(pickup["citations"][0]["id"], "RET-05.1")

    def test_order_number_followup(self):
        first = self.desk.chat("I need to return an item.")
        self.assertEqual(first["kind"], "clarify")
        result = self.desk.chat("NM-1042", first["context"])
        self.assertEqual(result["kind"], "clarify")
        self.assertIn("30-day", result["text"])
        self.assertEqual(result["citations"][0]["id"], "RET-01.1")
        verified = self.desk.chat("No", result["context"])
        self.assertIn("resalable", verified["text"])
        self.assertEqual(self.desk.chat("Yes", verified["context"])["kind"], "eligible")

    def test_electronics_condition_changes_outcome(self):
        first = self.desk.chat("Can I return order NM-1043?")
        self.assertEqual(first["kind"], "clarify")
        opened = self.desk.chat("I opened it.", first["context"])
        sealed = self.desk.chat("It is unopened.", first["context"])
        self.assertEqual(opened["kind"], "handoff")
        self.assertEqual(opened["handoff"]["policy"], ["RET-02.2"])
        self.assertEqual(sealed["kind"], "clarify")
        self.assertEqual(self.desk.chat("Yes", sealed["context"])["kind"], "eligible")

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
        with patch.object(self.desk, "lookup") as lookup:
            result = self.desk.chat("How long after you process a refund will I get my money for NM-1042?")
        lookup.assert_not_called()
        self.assertEqual(result["kind"], "policy")
        self.assertIn("3–5 business days", result["text"])

    def test_unknown_topic_hands_off_without_claim(self):
        result = self.desk.chat("Is the cafeteria open?")
        self.assertEqual(result["kind"], "handoff")
        self.assertEqual(result["citations"], [])
        self.assertEqual(result["handoff"]["action"], "remote_chat")
        self.assertIn("contact a remote office associate", result["text"].lower())

    def test_used_general_merchandise_is_outside_standard_conditions(self):
        answer = self.desk.chat("Can I return NM-1042? I have used it.")
        self.assertEqual(answer["kind"], "review")
        self.assertIn("unused", answer["text"])
        self.assertEqual(answer["citations"][0]["id"], "RET-01.1")

    def test_not_sealed_is_not_unopened(self):
        answer = self.desk.chat("Can I return NM-1043? It is not sealed.")
        self.assertEqual(answer["kind"], "handoff")
        self.assertEqual(answer["handoff"]["policy"], ["RET-02.2"])

    def test_refund_status_does_not_run_order_tool(self):
        with patch.object(self.desk, "lookup") as lookup:
            for question in ("What is the refund status for NM-1042?", "Where is my refund for NM-1042?"):
                with self.subTest(question=question):
                    answer = self.desk.chat(question)
                    self.assertIsNone(answer["order"])
                    self.assertIn("refund status", answer["text"].lower())
        lookup.assert_not_called()

    def test_multiple_order_ids_require_selection(self):
        with patch.object(self.desk, "lookup") as lookup:
            answer = self.desk.chat("Can I return both NM-1042 and NM-1043?")
        lookup.assert_not_called()
        self.assertEqual(answer["kind"], "clarify")
        selected = self.desk.chat("NM-1043", answer["context"])
        self.assertEqual(selected["order"]["id"], "NM-1043")

    def test_opened_headphones_uses_exception_clause(self):
        answer = self.desk.chat("What is the return policy for opened headphones?")
        self.assertEqual([clause["id"] for clause in answer["citations"]], ["RET-02.2"])

    def test_used_merchandise_and_receipt_question_cites_both_conditions(self):
        answer = self.desk.chat("Can I return a used item without a receipt?")
        self.assertEqual([clause["id"] for clause in answer["citations"]], ["RET-01.1", "RET-01.2"])

    def test_correction_keeps_conditions_bound_to_original_order(self):
        first = self.desk.chat("Can I return NM-1043? It is unopened.")
        corrected = self.desk.chat("Actually, check NM-1042", first["context"])
        self.assertEqual(corrected["kind"], "handoff")
        self.assertIsNone(corrected["order"])

    def test_duplicate_clause_ids_are_rejected_at_startup(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copy(ROOT / "seed.sql", root)
            shutil.copytree(ROOT / "policies", root / "policies")
            path = root / "policies" / "RET-01.md"
            path.write_text(path.read_text().replace("[RET-01.2]", "[RET-01.1]"))
            with self.assertRaisesRegex(ValueError, "Duplicate policy clause ID"):
                StoreAssistant(
                    root / "duplicate.sqlite3",
                    policies_dir=root / "policies",
                    seed_path=root / "seed.sql",
                )

    def test_policy_reorder_preserves_citation_and_return_window(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copy(ROOT / "seed.sql", root)
            shutil.copytree(ROOT / "policies", root / "policies")
            path = root / "policies" / "RET-01.md"
            header, window, receipt, online = path.read_text().split("\n## ")
            path.write_text("\n## ".join((header, receipt.strip(), window.strip(), online)))
            desk = StoreAssistant(
                root / "reordered.sqlite3",
                policies_dir=root / "policies",
                seed_path=root / "seed.sql",
            )
            result = desk.chat("Can I return NM-1042? It is unused and resalable.")
            self.assertEqual(result["kind"], "eligible")
            self.assertEqual(result["citations"][0]["id"], "RET-01.1")
            self.assertEqual(result["citations"][0]["title"], "Return window")

    def test_last_day_is_inclusive_and_unknown_condition_is_clarified(self):
        with sqlite3.connect(self.desk.database) as connection:
            connection.execute("UPDATE orders SET purchased_on = ? WHERE id = ?", ("2026-10-10", "NM-1042"))
        first = self.desk.chat("Can I return NM-1042?")
        self.assertEqual(first["kind"], "clarify")
        result = self.desk.chat("It is unused and resalable.", first["context"])
        self.assertEqual(result["kind"], "eligible")
        self.assertIn("30 days since purchase", result["text"])

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
