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

    def test_provenance_columns_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paper.db"
            conn = connect(path)
            columns = {
                row[1]
                for row in conn.execute(
                    "PRAGMA table_info(paper_signals)"
                ).fetchall()
            }
            for expected in (
                "model_version",
                "forecast_definition",
                "probability_method",
                "forecast_high_f",
                "forecast_sigma_f",
                "forecast_source",
                "intraday_conditioning",
                "observed_high_f",
                "minimum_actual_f",
                "observation_buffer_f",
                "entry_policy",
                "execution_quote_utc",
                "invalidation_reason",
            ):
                self.assertIn(expected, columns)
            conn.close()

    def test_live_evaluation_table_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paper.db"
            conn = connect(path)
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            self.assertIn("paper_evaluations", tables)

            columns = {
                row[1]
                for row in conn.execute(
                    "PRAGMA table_info(paper_evaluations)"
                ).fetchall()
            }
            for expected in (
                "evaluation_key",
                "probabilities_json",
                "model_lead_bucket",
                "signal_count",
                "winning_market_ticker",
                "multiclass_brier",
                "log_loss",
            ):
                self.assertIn(expected, columns)
            conn.close()


if __name__ == "__main__":
    unittest.main()
