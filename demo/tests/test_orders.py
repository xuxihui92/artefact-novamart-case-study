"""Unit tests for store-scoped order lookups."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from store_assistant.orders import OrderStore


class TestOrderStore(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = OrderStore(Path(temp.name) / "orders.sqlite3")

    def test_lookup_within_store(self):
        row = self.store.lookup("NM-1045")
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "Ready for pickup")
        self.assertEqual(row["item"], "Northline travel mug")

    def test_cross_store_and_missing_are_none(self):
        self.assertIsNone(self.store.lookup("NM-2042"))
        self.assertIsNone(self.store.lookup("NM-9999"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
