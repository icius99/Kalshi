import unittest

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


class IEMCSVTests(unittest.TestCase):
    def test_trailing_unnamed_column_is_discarded(self):
        text = "station,valid,high\nKNYC,2026-09-25,72,\n"
        rows = fetch_csv(FakeSession(text), "https://example.test", {})
        self.assertEqual(
            rows,
            [{"station": "KNYC", "valid": "2026-09-25", "high": "72"}],
        )
        self.assertNotIn(None, rows[0])


if __name__ == "__main__":
    unittest.main()
