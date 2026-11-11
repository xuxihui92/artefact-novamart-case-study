"""Unit tests for tool-argument validation and condition merging."""
import unittest

from store_assistant.tools import merge_facts, validate_tool_call


class TestToolValidation(unittest.TestCase):
    def test_search_and_lookup_arguments(self):
        search = validate_tool_call("search_policy", {"query": "refund method"}, "Where is a refund sent?")
        self.assertEqual(search["route"], "find_policy")
        self.assertEqual(search["query"], "refund method")
        lookup = validate_tool_call(
            "lookup_order",
            {"order_id": "nm-1042", "purpose": "order_status", "opened": None},
            "Status for NM-1042",
        )
        self.assertEqual(lookup["route"], "lookup_status")
        self.assertEqual(lookup["order_id"], "NM-1042")
        self.assertEqual(lookup["facts"], {})

    def test_accepts_json_string_and_redacted_order_token(self):
        result = validate_tool_call(
            "lookup_order",
            '{"purpose": "return_eligibility", "order_id": "<demo order reference>", "used": false}',
            "Can I return NM-1042?",
        )
        self.assertEqual(result["order_id"], "NM-1042")
        self.assertEqual(result["facts"], {"used": False})
        self.assertEqual(result["route"], "lookup_return")

    def test_rejects_unknown_tool_key_type_and_foreign_order(self):
        with self.assertRaises(ValueError):
            validate_tool_call("delete_order", {}, "hello")
        with self.assertRaises(ValueError):
            validate_tool_call("search_policy", {"query": "refund", "approve": True}, "refund?")
        with self.assertRaises(ValueError):
            validate_tool_call("lookup_order", {"purpose": "order_status", "opened": "yes"}, "NM-1042")
        with self.assertRaises(ValueError):
            validate_tool_call("lookup_order", {"purpose": "drop"}, "NM-1042")
        with self.assertRaises(ValueError):
            validate_tool_call("search_policy", {"query": ""}, "hello")
        with self.assertRaisesRegex(ValueError, "not in the customer message"):
            validate_tool_call(
                "lookup_order",
                {"purpose": "return_eligibility", "order_id": "NM-2042"},
                "Can I return NM-1046?",
            )
        with self.assertRaises(ValueError):
            validate_tool_call("handoff", {"reason": "x" * 301}, "hello")

    def test_legacy_route_names_map_to_current_tools(self):
        status = validate_tool_call("lookup_status", {"order_id": "NM-1045"}, "NM-1045")
        self.assertEqual(status["route"], "lookup_status")
        policy = validate_tool_call("find_policy", {"query": "price match"}, "price match")
        self.assertEqual(policy["route"], "find_policy")


class TestMergeFacts(unittest.TestCase):
    def test_regex_fact_wins_and_bare_questions_ignore_invented_facts(self):
        self.assertEqual(
            merge_facts({"opened": True}, {"opened": False, "used": False}, "I opened it."),
            {"opened": True},
        )
        self.assertEqual(
            merge_facts({}, {"used": False, "resalable": True}, "Can I return NM-1042?"),
            {},
        )

    def test_corroborated_paraphrase_and_chinese_are_kept(self):
        self.assertEqual(
            merge_facts({}, {"used": True}, "Can I return NM-1042? I have worn it."),
            {"used": True},
        )
        self.assertEqual(
            merge_facts({}, {"used": False, "resalable": True}, "没有使用过，还可以销售"),
            {"used": False, "resalable": True},
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
