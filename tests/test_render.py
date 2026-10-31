"""Offline tests for the rendered page in build.py. Every value here is made up."""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build  # noqa: E402
from test_build import private_row  # noqa: E402

ERAS = [{"from": "2014-03", "to": "2018-02", "label": "Student", "where": "Other University"},
        {"from": "2018-12", "label": "Software engineer", "where": "Example Corp"}]
STACKS = {"families": [{"name": "Java and Spring", "tools": ["Java"]}, {"name": "Python", "tools": ["Python"]}]}


def page(rows, today="2026-10-27"):
    return build.render(rows, ERAS, STACKS, "2026-10-27", "2026-10-26", today=today)


class RenderPage(unittest.TestCase):
    def test_no_placeholder_survives_and_header_copy_is_there(self):
        p = page([])
        self.assertNotIn("{{", p)
        self.assertIn("Lab is where I work on it. Not a company.", p)
        self.assertIn("You are welcome to look around.", p)

    def test_strip_cells_and_legend(self):
        rows = [private_row(started="2015-01", stage="finished"), private_row(started="2016-02", stage="running", as_of="2026-10"),
                private_row(started="2016-03", stage="thought")]
        p = page(rows, today="2017-01-01")
        self.assertEqual(p.count('class="cell"'), 3)
        self.assertIn('data-year="2017"', p)
        self.assertIn('aria-label="2016: 2 things, 1 running"', p)
        self.assertIn('aria-label="2015: 1 thing, 0 running"', p)
        self.assertIn('<span class="tag">1 running</span>', p)
        self.assertIn("3 things since 2015", p)
        self.assertIn("Data changed 2026-10-26 · page built 2026-10-27", p)

    def test_filters_and_summaries(self):
        rows = [private_row(topic="ai", stack=["Python"]), private_row(topic="games", stack=["Java"]), private_row(topic="ai", stack=[])]
        p = page(rows)
        self.assertIn('data-pick="ai" aria-pressed="false">AI tools <span class="count">2</span>', p)
        self.assertIn('data-pick="all" aria-pressed="true">All <span class="count">3</span>', p)
        self.assertIn('data-family="python" hidden', p)
        self.assertIn('<span class="made">1 made</span>', p)

    def test_history_blocks_years_groups_and_rows(self):
        rows = [dict(private_row(started="2019-01", stage="finished", title="Done", topic="web", stack=["Java"]), code_name="K-1"),
                {"mode": "public", "title": "Live", "summary": "Runs daily.", "stack": ["Python"], "stage": "running",
                 "started": "2019-03", "as_of": "2026-10", "topic": "ai", "kind": "contribution", "repo": "x/y"},
                private_row(started="2018-06", title="Gap")]
        p = page(rows)
        self.assertLess(p.index("Software engineer · Example Corp"), p.index(build.GAP_LABEL))
        self.assertIn('data-key="2018-03"', p)
        self.assertIn('<p class="glabel">Finished · 1</p>', p)
        self.assertLess(p.index('data-title="Done"'), p.index('data-title="Live"'))
        self.assertIn('data-families="python"', p)
        self.assertIn('<span class="kind">contribution</span>', p)
        self.assertEqual(p.count('class="kind"'), 1)  # the public row only
        self.assertIn("Shown under the code name K-1.", p)
        self.assertIn('href="https://github.com/x/y">Code on GitHub', p)
        self.assertIn("since Mar 2019 · running", p)
        section = p[p.index('class="history"'):p.index("<footer>")]
        self.assertIsNone(re.search(r'\shidden(\s|>|=)', section))
        self.assertEqual(p.count('aria-expanded="false"'), 2 + 3)  # two year toggles, three names

    def test_rows_adopted_at_a_meeting_carry_a_tag_a_card_line_and_a_count(self):
        rows = [{"mode": "public", "title": "Picked", "summary": "Chosen after a meeting.", "stack": [],
                 "stage": "planned", "started": "2026-10", "adopted": "2026-10", "topic": "ai"},
                private_row(started="2026-10", adopted="2026-10", title="Quiet pick")]
        p = page(rows)
        self.assertEqual(p.count('<span class="kind">meeting</span>'), 1)  # the public row only
        self.assertIn('<span class="cmeet">Adopted at an idea meeting, Oct 2026</span>', p)
        self.assertEqual(p.count('class="cmeet"'), 1)
        self.assertIn("<span>2 from idea meetings</span>", p)
        self.assertIn("<span>1 from an idea meeting</span>", page(rows[:1]))
        self.assertNotIn("idea meeting", page([private_row()]))

    def test_private_row_never_shows_a_kind_tag(self):
        p = page([private_row(kind="contribution", title="Quiet one")])
        self.assertIn('data-title="Quiet one"', p)
        self.assertNotIn('class="kind"', p)
        p = page([private_row(kind="note", title="Quiet note")])
        self.assertNotIn('class="kind"', p)

    def test_nothing_from_data_breaks_out_of_attributes(self):
        p = page([private_row(title='a"b<c')])
        self.assertIn('data-title="a&quot;b&lt;c"', p)

    def test_years_newest_first_and_stages_in_order_inside_a_year(self):
        # Rewritten from the old layout tests: years newest first inside an era, and inside a year
        # finished first, then the other stages in STAGE_ORDER.
        rows = [dict(private_row(stage="stopped", started="2016-01"), code_name="K-02"),
                dict(private_row(stage="finished", started="2016-03"), code_name="K-01"),
                dict(private_row(stage="running", as_of="2026-10", started="2016-05"), code_name="K-03"),
                dict(private_row(started="2015-04"), code_name="K-00")]
        p = page(rows)
        self.assertLess(p.index('<div class="year" data-year="2016"'), p.index('<div class="year" data-year="2015"'))
        self.assertLess(p.index(">K-01<"), p.index(">K-03<"))
        self.assertLess(p.index(">K-03<"), p.index(">K-02<"))


if __name__ == "__main__":
    unittest.main()
