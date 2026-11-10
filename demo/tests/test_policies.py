"""Unit tests for policy loading, search, and clause selection."""
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from return_desk.config import ROOT
from return_desk.policies import PolicyLibrary
from return_desk.text import reported_facts, terms


class TestPolicyLibrary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = PolicyLibrary()

    def test_loads_required_documents(self):
        self.assertEqual(len(self.library.policies), 3)
        self.assertIn("RET-01.1", self.library.clauses)
        self.assertEqual(self.library.return_windows["general"][1], 30)

    def test_search_ranks_title_matches(self):
        self.assertEqual(self.library.search("refund method")[0]["id"], "RET-03.1")
        self.assertEqual(self.library.search("unrelated astronomy"), [])

    def test_applicable_policy_routes(self):
        cases = [
            ("Where is my refund sent?", {}, "RET-03.1"),
            ("What is the exchange policy?", {}, "RET-03.2"),
            ("What is the return policy for opened headphones?", {"opened": True}, "RET-02.2"),
            ("Can I return a used item without a receipt?", {"used": True}, ("RET-01.1", "RET-01.2")),
            ("What is the standard return window?", {}, "RET-01.1"),
        ]
        for message, extra_facts, expected in cases:
            with self.subTest(message=message):
                words = terms(message)
                facts = {**reported_facts(message), **extra_facts}
                result = self.library.applicable_policy(message, words, facts)
                if isinstance(expected, str):
                    self.assertEqual(result, (expected,))
                else:
                    self.assertEqual(result, expected)

    def test_duplicate_clause_ids_are_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "policies", root / "policies")
            path = root / "policies" / "RET-01.md"
            path.write_text(path.read_text().replace("[RET-01.2]", "[RET-01.1]"))
            with self.assertRaisesRegex(ValueError, "Duplicate policy clause ID"):
                PolicyLibrary(policies_dir=root / "policies")

    def test_missing_required_clause_is_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "policies", root / "policies")
            (root / "policies" / "RET-03.md").unlink()
            with self.assertRaisesRegex(ValueError, "Missing required policy clauses"):
                PolicyLibrary(policies_dir=root / "policies")


if __name__ == "__main__":
    unittest.main(verbosity=2)
