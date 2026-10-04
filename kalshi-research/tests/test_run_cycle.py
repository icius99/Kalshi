import sys
import unittest
from argparse import Namespace
from pathlib import Path

from paper.run_cycle import build_commands


class PaperCycleTests(unittest.TestCase):
    def test_builds_settle_then_record(self):
        args = Namespace(
            db=Path("kalshi.db"),
            ledger=Path("paper.db"),
            model=Path("model.json"),
            event=None,
            min_edge=0.05,
            execution_buffer=0.005,
            min_qty=10.0,
            max_contracts=25,
            max_model_distance=6.0,
            anchor_hour=15,
            observation_buffer_f=1.0,
            max_snapshot_age_minutes=20.0,
            min_market_lead_hours=3.0,
            skip_settle=False,
        )
        commands = build_commands(args)
        self.assertEqual(len(commands), 2)
        self.assertEqual(
            commands[0][:3],
            [sys.executable, "-m", "paper.settle"],
        )
        self.assertEqual(
            commands[1][:3],
            [sys.executable, "-m", "paper.record_signals"],
        )
        self.assertIn("--model", commands[1])
        self.assertIn("model.json", commands[1])

    def test_skip_settle(self):
        args = Namespace(
            db=Path("kalshi.db"),
            ledger=Path("paper.db"),
            model=Path("model.json"),
            event="KXHIGHNY-26OCT04",
            min_edge=0.05,
            execution_buffer=0.005,
            min_qty=10.0,
            max_contracts=25,
            max_model_distance=6.0,
            anchor_hour=15,
            observation_buffer_f=1.0,
            max_snapshot_age_minutes=20.0,
            min_market_lead_hours=3.0,
            skip_settle=True,
        )
        commands = build_commands(args)
        self.assertEqual(len(commands), 1)
        self.assertIn("--event", commands[0])
        self.assertIn("KXHIGHNY-26OCT04", commands[0])


if __name__ == "__main__":
    unittest.main()
