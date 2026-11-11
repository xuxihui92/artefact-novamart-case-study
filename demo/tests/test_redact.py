"""Unit tests for redaction that runs before a model call."""
import unittest

from store_assistant.redact import redact


class TestRedact(unittest.TestCase):
    def test_redacts_email_phone_card_name_and_order_id(self):
        text = (
            "My name is Jane Doe, email jane.doe@example.com, call (415) 555-0199 "
            "or +447911123456, card 4111 1111 1111 1111, order NM-1042."
        )
        cleaned = redact(text)
        for secret in (
            "Jane Doe",
            "jane.doe@example.com",
            "415",
            "555-0199",
            "447911123456",
            "4111",
            "NM-1042",
        ):
            self.assertNotIn(secret, cleaned)
        self.assertIn("<name>", cleaned)
        self.assertIn("<email>", cleaned)
        self.assertIn("<phone>", cleaned)
        self.assertIn("<card>", cleaned)
        self.assertIn("<demo order reference>", cleaned)

    def test_honorific_name(self):
        cleaned = redact("Ask Dr. Ada Lovelace about the return.")
        self.assertNotIn("Ada", cleaned)
        self.assertNotIn("Lovelace", cleaned)
        self.assertIn("<name>", cleaned)

    def test_leaves_policy_wording_and_is_idempotent(self):
        text = "Can I return the headphones? Allow 3–5 business days. The window is 30-day."
        cleaned = redact(text)
        self.assertEqual(cleaned, text)
        sample = "Email jane@example.com about NM-1042"
        self.assertEqual(redact(redact(sample)), redact(sample))

    def test_does_not_treat_uncertainty_as_a_name(self):
        self.assertNotIn("<name>", redact("I am not sure if it is opened."))
        self.assertNotIn("<name>", redact("This is unopened."))


if __name__ == "__main__":
    unittest.main(verbosity=2)
