import unittest
from datetime import date

from historical.build_nbm_history import parse_cli_observations


class CLIObservationTests(unittest.TestCase):
    def test_parses_valid_and_high(self):
        rows = [
            {"valid": "2026-09-24", "high": "68"},
            {"valid": "2026-09-25", "high": "72"},
            {"valid": "2026-09-26", "high": "M"},
        ]
        result = parse_cli_observations(
            rows,
            date(2026, 9, 25),
            date(2026, 9, 26),
        )
        self.assertEqual(result, {date(2026, 9, 25): 72.0})


if __name__ == "__main__":
    unittest.main()
