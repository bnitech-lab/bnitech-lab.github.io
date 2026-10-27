"""Offline tests for the era blocks and year entries in build.py. Every value here is made up."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build  # noqa: E402
from test_build import private_row  # noqa: E402

ERAS = [{"from": "2011-03", "to": "2013-02", "label": "Student", "where": "Example University"},
        {"from": "2014-03", "to": "2018-02", "label": "Student", "where": "Other University"},
        {"from": "2018-12", "to": "2021-07", "label": "Software engineer", "where": "Example Corp"},
        {"from": "2021-08", "label": "Own projects", "where": "Example City"}]


class History(unittest.TestCase):
    def test_month_dates_pick_the_containing_era(self):
        self.assertEqual(build.era_of(ERAS, "2019-01")["where"], "Example Corp")
        self.assertEqual(build.era_of(ERAS, "2021-08")["label"], "Own projects")
        self.assertIsNone(build.era_of(ERAS, "2018-06"))

    def test_bare_year_goes_to_the_era_covering_most_of_it(self):
        self.assertEqual(build.era_of(ERAS, "2011")["where"], "Example University")  # Mar to Dec: 10 months
        self.assertIsNone(build.era_of(ERAS, "2018"))  # Feb + Dec covered, 9 months uncovered

    def test_tally_and_preview(self):
        rows = [private_row(stage="finished", title="A"), private_row(stage="thought", title="B"),
                private_row(stage="running", as_of="2026-10", title="C"), private_row(stage="finished", title="D")]
        self.assertEqual(build.tally(rows), "2 finished · 1 running · 1 idea")
        self.assertEqual(build.preview(rows), "A, B, C and 1 more")
        self.assertEqual(build.preview(rows[:3]), "A, B, C")

    def test_blocks_newest_first_with_a_gap_block_between_eras(self):
        rows = [private_row(started="2012"), private_row(started="2018"), private_row(started="2019-01")]
        blocks = build.history(rows, ERAS)
        self.assertEqual([b["label"] for b in blocks],
                         ["Software engineer · Example Corp", build.GAP_LABEL, "Student · Example University"])
        self.assertEqual(blocks[1]["key"], "2018-03")
        self.assertEqual(blocks[1]["when"], "2018")
        self.assertEqual(blocks[0]["when"], "Dec 2018 to Jul 2021")

    def test_split_year_appears_under_each_era_with_its_own_rows(self):
        rows = [private_row(started="2021-03", title="Old"), private_row(started="2021-09", title="New")]
        blocks = build.history(rows, ERAS)
        self.assertEqual([(b["label"], b["years"][0]["year"], b["years"][0]["count"]) for b in blocks],
                         [("Own projects · Example City", "2021", 1), ("Software engineer · Example Corp", "2021", 1)])
        self.assertEqual(blocks[0]["when"], "Aug 2021 to now")

    def test_no_block_for_a_year_without_rows(self):
        blocks = build.history([private_row(started="2012")], ERAS)
        self.assertEqual(len(blocks), 1)
        self.assertEqual([y["year"] for y in blocks[0]["years"]], ["2012"])


if __name__ == "__main__":
    unittest.main()
