"""Read-only SQLite order lookups scoped to the demo store."""
from contextlib import closing
from pathlib import Path
import sqlite3

from .config import ROOT, STORE


class OrderStore:
    def __init__(self, database, seed_path=None):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        seed = Path(seed_path or ROOT / "seed.sql")
        with closing(sqlite3.connect(self.database)) as connection:
            connection.executescript(seed.read_text(encoding="utf-8"))
            connection.commit()

    def lookup(self, order_id):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.row_factory = sqlite3.Row
            return connection.execute(
                """SELECT id, item, category, purchased_on, channel, status, final_sale
                   FROM orders WHERE id = ? AND store_id = ?""",
                (order_id, STORE),
            ).fetchone()
