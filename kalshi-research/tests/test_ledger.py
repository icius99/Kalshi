import tempfile
import unittest
from pathlib import Path

from paper.ledger import connect, has_open_position


class LedgerTests(unittest.TestCase):
    def test_open_position_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paper.db"
            conn = connect(path)
            self.assertFalse(has_open_position(conn, "ABC"))
            conn.execute(
                """
                INSERT INTO paper_signals (
                    created_at_utc,market_snapshot_utc,forecast_runtime_utc,
                    event_ticker,market_ticker,side,entry_price,quantity,
                    model_probability_yes,estimated_edge,lead_hours,
                    model_lead_bucket,model_sample_n
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    "2026-10-03T20:00:00+00:00",
                    "2026-10-03T20:00:00+00:00",
                    "2026-10-03T18:00:00+00:00",
                    "E",
                    "ABC",
                    "YES",
                    0.2,
                    10,
                    0.3,
                    0.09,
                    20,
                    24,
                    100,
                ),
            )
            conn.commit()
            self.assertTrue(has_open_position(conn, "ABC"))
            conn.close()


if __name__ == "__main__":
    unittest.main()
