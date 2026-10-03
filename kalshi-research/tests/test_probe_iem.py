import unittest

from historical.probe_iem import assert_aliases


class ProbeTests(unittest.TestCase):
    def test_aliases_accept_supported_names(self):
        assert_aliases(
            {"runtime": "x", "ftime": "y", "txn": "65"},
            {
                "runtime": ("runtime", "runtime_utc"),
                "valid": ("ftime", "valid"),
                "txn": ("txn",),
            },
            "test",
        )

    def test_aliases_reject_missing_fields(self):
        with self.assertRaises(SystemExit):
            assert_aliases(
                {"runtime": "x"},
                {"runtime": ("runtime",), "txn": ("txn",)},
                "test",
            )


if __name__ == "__main__":
    unittest.main()
