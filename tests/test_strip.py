"""Offline tests for the year strip, the counts and the staleness lines in build.py. Every value here is made up."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build  # noqa: E402
from test_build import private_row  # noqa: E402


class Strip(unittest.TestCase):
    def test_strip_has_a_cell_for_every_year_including_empty_ones(self):
        rows = [private_row(started="2011-04"), private_row(started="2013-06", stage="running", as_of="2026-10")]
        years = build.all_years(rows, "2014-05-01")
        self.assertEqual(years, ["2011", "2012", "2013", "2014"])
        self.assertEqual(build.strip(rows, years),
                         [{"year": "2011", "count": 1, "running": 0}, {"year": "2012", "count": 0, "running": 0},
                          {"year": "2013", "count": 1, "running": 1}, {"year": "2014", "count": 0, "running": 0}])

    def test_counts(self):
        rows = [private_row(started="2011", stage="finished"), private_row(started="2012", stage="running", as_of="2026-10"),
                private_row(started="2012", stage="thought")]
        self.assertEqual(build.counts(rows), {"total": 3, "running": 1, "finished": 1, "meeting": 0, "first_year": "2011"})

    def test_no_rows_gives_empty_strip_and_zero_counts(self):
        self.assertEqual(build.all_years([], "2026-10-26"), [])
        self.assertEqual(build.strip([], []), [])
        self.assertEqual(build.counts([]), {"total": 0, "running": 0, "finished": 0, "meeting": 0, "first_year": ""})

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
