import json
import sys
import tempfile
import unittest
from argparse import Namespace
from datetime import date
from pathlib import Path

from historical.run_research_pipeline import build_commands, make_paths, validate_promotion


class ResearchPipelineTests(unittest.TestCase):
    def test_paths_are_date_stamped(self):
        paths = make_paths(
            date(2021, 1, 1),
            date(2026, 9, 30),
            Path("hist"),
            Path("models"),
        )
        self.assertEqual(
            paths.dataset,
            Path("hist/nbm_nyc_20210101_20260930.csv"),
        )
        self.assertEqual(
            paths.walkforward,
            Path("models/nbm_walkforward_20210101_20260930.json"),
        )
        self.assertEqual(
            paths.model,
            Path("models/nbm_error_model_20210101_20260930.json"),
        )

    def test_commands_are_ordered_build_audit_validate_fit(self):
        args = Namespace(
            start=date(2021, 1, 1),
            end=date(2026, 9, 30),
            test_start=date(2025, 1, 1),
            buckets="12,24,36,48,60",
            skip_build=False,
        )
        paths = make_paths(
            args.start,
            args.end,
            Path("data/historical"),
            Path("data/models"),
        )
        commands = build_commands(args, paths)

        self.assertEqual(len(commands), 6)
        self.assertEqual(
            commands[0][0:3],
            [sys.executable, "-m", "historical.build_nbm_history"],
        )
        self.assertEqual(
            commands[1][0:3],
            [sys.executable, "-m", "historical.audit_dataset"],
        )
        self.assertEqual(
            commands[2][0:3],
            [sys.executable, "-m", "historical.compare_calendar_high"],
        )
        self.assertEqual(
            commands[3][0:3],
            [sys.executable, "-m", "historical.validate_chronological"],
        )
        self.assertIn("--test-start", commands[3])
        self.assertEqual(
            commands[4][0:3],
            [sys.executable, "-m", "historical.walkforward_compare"],
        )
        self.assertEqual(
            commands[5][0:3],
            [sys.executable, "-m", "historical.forecast_error"],
        )

    def test_skip_build_starts_with_audit(self):
        args = Namespace(
            start=date(2021, 1, 1),
            end=date(2026, 9, 30),
            test_start=None,
            buckets="12,24,36,48,60",
            skip_build=True,
        )
        paths = make_paths(
            args.start,
            args.end,
            Path("data/historical"),
            Path("data/models"),
        )
        commands = build_commands(args, paths)
        self.assertEqual(len(commands), 5)
        self.assertEqual(
            commands[0][0:3],
            [sys.executable, "-m", "historical.audit_dataset"],
        )

    def test_promotion_requires_current_schema_and_walkforward_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(
                date(2021, 1, 1),
                date(2026, 9, 30),
                root / "hist",
                root / "models",
            )
            paths.model.parent.mkdir(parents=True, exist_ok=True)
            paths.model.write_text(
                json.dumps(
                    {
                        "version": 4,
                        "forecast_definition": "calendar_day_nbm_txn_plus_early_tmp_v1",
                        "default_probability_method": "empirical_integer_errors",
                    }
                ),
                encoding="utf-8",
            )
            paths.walkforward.write_text(
                json.dumps({"recommended_probability_method": "empirical"}),
                encoding="utf-8",
            )
            result = validate_promotion(paths)
            self.assertEqual(result["model_version"], 4)

    def test_promotion_rejects_old_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(
                date(2021, 1, 1),
                date(2026, 9, 30),
                root / "hist",
                root / "models",
            )
            paths.model.parent.mkdir(parents=True, exist_ok=True)
            paths.model.write_text(json.dumps({"version": 3}), encoding="utf-8")
            paths.walkforward.write_text(
                json.dumps({"recommended_probability_method": "empirical"}),
                encoding="utf-8",
            )
            with self.assertRaises(SystemExit):
                validate_promotion(paths)


if __name__ == "__main__":
    unittest.main()
