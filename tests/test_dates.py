"""Offline tests for the year range, the data-changed date and the staleness lines in build.py. Every value here is made up."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build  # noqa: E402
from test_build import private_row  # noqa: E402


class Dates(unittest.TestCase):
    def test_all_years_runs_from_the_first_row_to_today(self):
        rows = [private_row(started="2011-04"), private_row(started="2013-06", stage="running", as_of="2026-10")]
        self.assertEqual(build.all_years(rows, "2014-05-01"), ["2011", "2012", "2013", "2014"])
        self.assertEqual(build.all_years([], "2026-10-26"), [])

    def test_data_changed_date_refuses_a_shallow_checkout(self):
        answers = iter(["true\n"])
        with self.assertRaises(RuntimeError):
            build.data_changed_date(run=lambda *a, **k: next(answers))
        answers = iter(["false\n", "1792973100\n"])  # 2026-10-26 00:05 UTC
        self.assertEqual(build.data_changed_date(run=lambda *a, **k: next(answers)), "2026-10-26")

    def test_data_changed_date_is_utc_not_the_committers_timezone(self):
        # 2026-11-13 08:30 in Korea (+0900) is 2026-11-12 23:30 UTC; the page says "page built" in UTC.
        seen = []

        def fake(cmd, **kwargs):
            seen.append(cmd)
            return "false\n" if cmd[:2] == ["git", "rev-parse"] else "1794526200\n"

        self.assertEqual(build.data_changed_date(run=fake), "2026-11-12")
        self.assertIn("--format=%ct", seen[1])

    def test_data_changed_date_refuses_a_history_without_data_commits(self):
        answers = iter(["false\n", ""])
        with self.assertRaisesRegex(RuntimeError, "no commit touches data/"):
            build.data_changed_date(run=lambda *a, **k: next(answers))

    def test_stale_running_uses_a_twelve_month_line(self):
        rows = [private_row(title="Old", stage="running", as_of="2025-09"),
                private_row(title="Edge", stage="running", as_of="2025-10"),
                private_row(title="Linked", stage="running", as_of="2020-01", mode="public", repo="x/y")]
        del rows[2]["code_name"]
        self.assertEqual(build.stale_running(rows, "2026-10-26"), ["still running? Old (as_of 2025-09)"])


if __name__ == "__main__":
    unittest.main()
