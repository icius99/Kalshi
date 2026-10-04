import unittest
from pathlib import Path

from paper.install_timer import render_service, render_timer


class PaperTimerInstallTests(unittest.TestCase):
    def test_service_freezes_research_safeguards(self):
        text = render_service(
            Path("/tmp/kalshi-research"),
            Path("/tmp/kalshi-research/.venv/bin/python"),
        )
        self.assertIn("-m paper.run_cycle", text)
        self.assertIn("--min-market-lead-hours 3", text)
        self.assertIn("--max-snapshot-age-minutes 20", text)
        self.assertIn("--observation-buffer-f 1", text)
        self.assertIn("WorkingDirectory=/tmp/kalshi-research", text)

    def test_timer_is_offset_from_collector(self):
        text = render_timer()
        self.assertIn("OnCalendar=*:2/5", text)
        self.assertIn("Persistent=true", text)


if __name__ == "__main__":
    unittest.main()
