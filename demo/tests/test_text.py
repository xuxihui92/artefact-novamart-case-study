"""Unit tests for keyword and condition extraction."""
import unittest

from store_assistant.text import reported_facts, terms


class TextTerms(unittest.TestCase):
    def test_aliases_and_stopwords(self):
        self.assertEqual(terms("Can I return the headphones?"), {"return", "electronics"})
        self.assertEqual(terms("refunds and exchanges"), {"refund", "exchange"})

    def test_empty_and_noise(self):
        self.assertEqual(terms("the a an"), set())
        self.assertEqual(terms(""), set())


class TestReportedFacts(unittest.TestCase):
    def test_opened_and_sealed(self):
        self.assertEqual(reported_facts("I opened it.")["opened"], True)
        self.assertEqual(reported_facts("It is not sealed.")["opened"], True)
        self.assertEqual(reported_facts("It is unopened.")["opened"], False)

    def test_used_and_resalable(self):
        self.assertEqual(reported_facts("I have used it.")["used"], True)
        self.assertEqual(reported_facts("It is unused and resalable."), {"used": False, "resalable": True})
        self.assertEqual(reported_facts("It is not resalable.")["resalable"], False)

    def test_uncertain_language_yields_no_facts(self):
        self.assertEqual(reported_facts("I am not sure if it is opened."), {})
        self.assertEqual(reported_facts("Maybe it is used."), {})

    def test_conflicting_mentions_are_ambiguous(self):
        facts = reported_facts("It is opened and unopened.")
        self.assertIn("opened", facts)
        self.assertIsNone(facts["opened"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
