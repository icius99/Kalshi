import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from paper.health import age_minutes, count_statuses


class PaperHealthTests(unittest.TestCase):
    def test_age_minutes(self):
        now = datetime(2026, 10, 5, 2, 30, tzinfo=timezone.utc)
        timestamp = (now - timedelta(minutes=7)).isoformat()
        self.assertAlmostEqual(age_minutes(timestamp, now), 7.0)

    def test_count_statuses(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE x(status TEXT)")
        conn.executemany(
            "INSERT INTO x VALUES (?)",
            [("OPEN",), ("OPEN",), ("SETTLED",)],
        )
        self.assertEqual(
            count_statuses(conn, "x"),
            {"OPEN": 2, "SETTLED": 1},
        )
        conn.close()


if __name__ == "__main__":
    unittest.main()
