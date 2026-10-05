import sqlite3
import unittest

from paper.summary import primary_evaluations


class SummaryCalibrationTests(unittest.TestCase):
    def test_primary_evaluations_choose_closest_runtime_per_event_bucket(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE x (
                id INTEGER,
                event_ticker TEXT,
                model_lead_hours REAL,
                model_lead_bucket INTEGER,
                status TEXT,
                multiclass_brier REAL,
                log_loss REAL,
                signal_count INTEGER,
                probability_method TEXT,
                forecast_runtime_utc TEXT,
                winning_market_ticker TEXT
            )
            """
        )
        conn.executemany(
            "INSERT INTO x VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [
                (1, "E1", 19.0, 24, "SETTLED", 0.4, 1.0, 0, "empirical", "a", "W"),
                (2, "E1", 25.0, 24, "SETTLED", 0.2, 0.5, 0, "empirical", "b", "W"),
                (3, "E1", 13.0, 12, "SETTLED", 0.3, 0.8, 0, "empirical", "c", "W"),
                (4, "E2", 25.0, 24, "OPEN", None, None, 0, "empirical", "d", None),
            ],
        )
        rows = conn.execute("SELECT * FROM x ORDER BY id").fetchall()
        primary = primary_evaluations(rows)
        self.assertEqual({row["id"] for row in primary}, {2, 3})
        conn.close()


if __name__ == "__main__":
    unittest.main()
