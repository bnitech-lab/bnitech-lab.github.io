"""Offline tests for the recurring themes block in build.py. Every value here is made up."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build  # noqa: E402
from test_build import private_row  # noqa: E402
from test_render import page  # noqa: E402

THREADS = {"threads": [{"key": "boats", "name": "Boats", "words": ["boat"]},
                       {"key": "notes", "name": "Notes", "words": ["notebook"]}]}
YEARS = [str(y) for y in range(2011, 2027)]


def row(year, stage="thought", threads=("boats",), **extra):
    r = {"mode": "public", "title": "Idea %s %s" % (year, stage), "summary": "", "stack": [], "stage": stage,
         "started": year, "topic": "apps", "threads": list(threads)}
    if stage == "running":
        r["as_of"] = "2026-10"
    r.update(extra)
    return r


class CheckThreads(unittest.TestCase):

    def test_valid_threads_and_rows(self):
        self.assertEqual(build.check_threads(THREADS, [row("2011"), row("2012", threads=())]), [])

    def test_unknown_thread_on_a_row_fails(self):
        problems = build.check_threads(THREADS, [row("2011", threads=("kites",))])
        self.assertTrue(any("kites" in p for p in problems))

    def test_bad_shapes_fail(self):
        self.assertTrue(build.check_threads({"threads": [{"key": "Boats!", "name": "B"}]}, []))
        self.assertTrue(any("used twice" in p for p in
                            build.check_threads({"threads": [{"key": "a", "name": "A"}, {"key": "a", "name": "B"}]}, [])))
        for bad in ({"key": "a", "name": 5}, {"key": "a"}, {"key": 5, "name": "A"}, {"key": "a\n", "name": "A"},
                    {"key": "a", "name": "A", "words": "boat"}, {"key": "a", "name": "A", "word": ["boat"]}):
            self.assertTrue(build.check_threads({"threads": [bad]}, []), bad)
        self.assertTrue(any("threads.json must hold" in p for p in build.check_threads(["a"], [])))
        self.assertEqual(build.check_threads(THREADS, ["oops"]), [])  # check_rows reports the row; this must not crash
        self.assertEqual(build.check_threads(THREADS, {"rows": []}), [])
        self.assertTrue(build.check_rows([private_row(threads="boats")]))
        self.assertEqual(build.check_rows([private_row(threads=["boats"])]), [])


class ThemeLines(unittest.TestCase):

    def test_three_separate_years_make_a_line(self):
        lines = build.theme_lines([row("2011"), row("2015-04"), row("2017")], THREADS, YEARS)
        self.assertEqual([l["key"] for l in lines], ["boats"])
        self.assertEqual((lines[0]["first"], lines[0]["last"], lines[0]["tries"]), ("2011", "2017", 3))

    def test_two_years_are_not_enough(self):
        self.assertEqual(build.theme_lines([row("2011"), row("2011-06"), row("2015")], THREADS, YEARS), [])

    def test_adopted_rows_draw_but_do_not_count(self):
        rows = [row("2011"), row("2015"), row("2026-10", stage="planned", adopted="2026-10")]
        self.assertEqual(build.theme_lines(rows, THREADS, YEARS), [])
        lines = build.theme_lines(rows + [row("2017")], THREADS, YEARS)
        self.assertEqual(lines[0]["last"], "2026")
        self.assertEqual(lines[0]["cells"][-1], ("2026", "o", 1))

    def test_a_cell_shows_its_liveliest_stage_and_a_count(self):
        rows = [row("2011"), row("2015"), row("2026-01", stage="retired"), row("2026-03", stage="running"),
                row("2026-05", stage="planned")]
        cells = dict((y, (c, n)) for y, c, n in build.theme_lines(rows, THREADS, YEARS)[0]["cells"])
        self.assertEqual(cells["2026"], ("r", 3))
        self.assertEqual(cells["2011"], ("o", 1))
        self.assertEqual(cells["2012"], ("", 0))
        rows[2]["stage"] = "finished"
        del rows[3]["as_of"]
        rows[3]["stage"] = "stopped"
        cells = dict((y, (c, n)) for y, c, n in build.theme_lines(rows, THREADS, YEARS)[0]["cells"])
        self.assertEqual(cells["2026"], ("f", 3))

    def test_order_is_latest_year_then_longest_span(self):
        rows = ([row(y, threads=("boats",)) for y in ("2014", "2016", "2020")]
                + [row(y, threads=("notes",)) for y in ("2011", "2013", "2020")])
        self.assertEqual([l["key"] for l in build.theme_lines(rows, THREADS, YEARS)], ["notes", "boats"])
        rows.append(row("2022", threads=("boats",)))
        self.assertEqual([l["key"] for l in build.theme_lines(rows, THREADS, YEARS)], ["boats", "notes"])

    def test_words_lead_each_line(self):
        rows = [row("2011"), row("2015"), row("2017", stage="running")]
        self.assertEqual(build.theme_words(build.theme_lines(rows, THREADS, YEARS)[0]), "3 tries since 2011 · 1 running")
        rows[2]["stage"] = "stopped"
        self.assertEqual(build.theme_words(build.theme_lines(rows, THREADS, YEARS)[0]), "3 tries since 2011 · last in 2017")

    def test_hints_name_untagged_rows_that_share_a_word(self):
        rows = [row("2011", title="Boat app"), row("2012", threads=(), title="A boat timer"),
                row("2013", threads=(), title="Kites")]
        self.assertEqual(build.theme_hints(rows, THREADS), ["thread? A boat timer shares 'boat' with thread boats"])
        rows.append(row("2014", threads=(), title="Sailboat log"))  # a word inside another word is no hint
        self.assertEqual(len(build.theme_hints(rows, THREADS)), 1)

    def test_ties_break_on_tries_then_name(self):
        rows = ([row(y, threads=("boats",)) for y in ("2011", "2013", "2020")]
                + [row(y, threads=("notes",)) for y in ("2011", "2013", "2020", "2020-05")])
        self.assertEqual([l["key"] for l in build.theme_lines(rows, THREADS, YEARS)], ["notes", "boats"])
        rows.pop()
        self.assertEqual([l["key"] for l in build.theme_lines(rows, THREADS, YEARS)], ["boats", "notes"])


class RenderThemes(unittest.TestCase):

    def test_page_shows_the_block_and_moves_the_dates_to_the_footer(self):
        rows = [row("2011"), dict(private_row(started="2015", threads=["boats"]), code_name="K-7"),
                row("2017", threads=("boats", "notes"), title="Two ways"),
                row("2026-10", stage="planned", adopted="2026-10", title="From a meeting")]
        p = page(rows, threads=THREADS)
        block = p[p.index('class="themes"'):p.index('class="browse"')]
        self.assertIn("Boats", block)
        self.assertIn("4 tries since 2011 · last in 2026", block)
        self.assertIn("K-7", block)
        self.assertIn("also on Notes", block)
        self.assertIn("from an idea meeting", block)
        self.assertEqual(block.count("<details"), 1)
        self.assertNotIn('class="strip"', p)
        self.assertNotIn('class="legend', p)
        footer = p[p.index("<footer>"):]
        self.assertIn("Data changed 2026-10-26 · page built 2026-10-27", footer)

    def test_cells_axis_key_and_screen_reader_text(self):
        rows = [row("2011"), row("2015", stage="finished"), row("2015-06", stage="stopped"), row("2026-03", stage="running")]
        p = page(rows, threads=THREADS)
        block = p[p.index('class="themes"'):p.index('class="browse"')]
        self.assertIn('<span class="tc o"></span>', block)       # 2011, not finished
        self.assertIn('<span class="tc f">2</span>', block)      # 2015, two rows, liveliest is finished
        self.assertIn('<span class="tc r"></span>', block)       # 2026, running
        self.assertIn('<span class="tc"></span>', block)         # an empty year
        self.assertIn('class="axis"', block)
        self.assertIn("finished or retired", block)
        self.assertIn("running in 2026; finished in 2015; not finished in 2011", block)
        self.assertIn('class="tcells" aria-hidden="true"', block)
        self.assertIn('<ol class="tries" role="list">', block)

    def test_data_is_escaped_in_the_block(self):
        threads = {"threads": [{"key": "boats", "name": "B<b>&\"", "words": []}]}
        rows = [row("2011", title="T<i>&\""), row("2015"), row("2017")]
        block = page(rows, threads=threads)
        block = block[block.index('class="themes"'):block.index('class="browse"')]
        self.assertNotIn("<b>", block)
        self.assertNotIn("<i>", block)
        self.assertIn("B&lt;b&gt;&amp;&quot;", block)
        self.assertIn("T&lt;i&gt;&amp;&quot;", block)

    def test_a_private_adopted_row_gets_no_meeting_note(self):
        rows = [row("2011"), row("2015"), dict(private_row(started="2017", threads=["boats"], adopted="2017"), code_name="K-9")]
        rows.append(row("2019"))
        block = page(rows, threads=THREADS)
        block = block[block.index('class="themes"'):block.index('class="browse"')]
        self.assertIn("K-9", block)
        self.assertNotIn("from an idea meeting", block)

    def test_no_line_means_no_block(self):
        p = page([row("2011"), row("2012")], threads=THREADS)
        self.assertNotIn("<details", p)
        self.assertIn('<div class="glance"></div>', p)  # empty, so .glance:empty hides it


if __name__ == "__main__":
    unittest.main()
