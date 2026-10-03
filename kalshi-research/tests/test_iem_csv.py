import unittest
from unittest.mock import patch

import requests

from historical.build_nbm_history import fetch_csv


class FakeResponse:
    status_code = 200
    headers = {}

    def __init__(self, text):
        self.text = text
        self.url = "https://example.test/cli.csv"

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self, text):
        self.response = FakeResponse(text)

    def get(self, *args, **kwargs):
        return self.response


class FlakySession:
    def __init__(self, text):
        self.calls = 0
        self.response = FakeResponse(text)

    def get(self, *args, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise requests.ConnectionError("temporary disconnect")
        return self.response


class IEMCSVTests(unittest.TestCase):
    def test_trailing_unnamed_column_is_discarded(self):
        text = "station,valid,high\nKNYC,2026-09-25,72,\n"
        rows = fetch_csv(FakeSession(text), "https://example.test", {})
        self.assertEqual(
            rows,
            [{"station": "KNYC", "valid": "2026-09-25", "high": "72"}],
        )
        self.assertNotIn(None, rows[0])

    @patch("historical.build_nbm_history.time.sleep")
    def test_transient_connection_error_is_retried(self, sleep):
        text = "station,valid,high\nKNYC,2026-09-25,72\n"
        session = FlakySession(text)
        rows = fetch_csv(session, "https://example.test", {}, max_attempts=2)
        self.assertEqual(session.calls, 2)
        self.assertEqual(rows[0]["high"], "72")
        sleep.assert_called_once()


if __name__ == "__main__":
    unittest.main()
