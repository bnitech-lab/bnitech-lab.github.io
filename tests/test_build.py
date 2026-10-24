"""Offline tests for build.py. Every value here is made up."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build  # noqa: E402

README = """# example-repo

<!-- bnitech:card -->
- **Problem:** Example problem with `a command`.
- **Who it helps:** Example readers.
- **Try it (about 7 minutes):** Run `python3 example.py` and read the output.
<!-- /bnitech:card -->

Body text.
"""


class ParseCard(unittest.TestCase):
    def test_reads_three_fields_and_minutes(self):
        card = build.parse_card(README)
        self.assertEqual(card["problem"], "Example problem with `a command`.")
        self.assertEqual(card["who"], "Example readers.")
        self.assertEqual(card["minutes"], 7)
        self.assertIn("python3 example.py", card["try"])

    def test_missing_block_fails(self):
        with self.assertRaises(ValueError):
            build.parse_card("# no card here\n")

    def test_missing_field_fails(self):
        broken = README.replace("- **Who it helps:** Example readers.\n", "")
        with self.assertRaises(ValueError):
            build.parse_card(broken)


def private_row(**extra):
    row = {"mode": "private", "code_name": "K-01", "title": "Example idea",
           "stack": ["Java"], "stage": "planned", "started": "2015"}
    row.update(extra)
    return row


class CheckRows(unittest.TestCase):

    def test_valid_private_and_public_rows(self):
        rows = [private_row(),
                {"mode": "public", "title": "Example game", "stack": ["C"], "stage": "finished",
                 "started": "2011-12", "restarted": ["2012-07"], "repo": "example/example-game"}]
        self.assertEqual(build.check_rows(rows), [])

    def test_unknown_field_is_rejected(self):
        problems = build.check_rows([private_row(notes="anything")])
        self.assertTrue(any("notes" in p for p in problems))

    def test_private_row_cannot_link_a_repo(self):
        problems = build.check_rows([private_row(repo="example/example")])
        self.assertTrue(any("repo" in p for p in problems))

    def test_private_row_needs_code_name(self):
        row = private_row()
        del row["code_name"]
        self.assertTrue(build.check_rows([row]))

    def test_bad_stage_and_date(self):
        problems = build.check_rows([private_row(stage="maybe", started="last year")])
        self.assertEqual(len(problems), 2)

    def test_running_without_repo_needs_as_of(self):
        self.assertTrue(build.check_rows([private_row(stage="running")]))
        self.assertEqual(build.check_rows([private_row(stage="running", as_of="2026-10")]), [])


class Render(unittest.TestCase):
    def test_page_without_rows_has_no_ideas_section(self):
        card = dict(build.parse_card(README), repo="example/example-repo", title="Example",
                    url="https://github.com/example/example-repo", license="MIT", updated="2026-01-01")
        page = build.render([card], [], "2026-01-02")
        self.assertIn("Not a company.", page)
        self.assertIn("about 7 min", page)
        self.assertIn("<code>python3 example.py</code>", page)
        self.assertNotIn("Ideas by the year", page)
        self.assertNotIn("{{", page)

    def test_rows_group_by_start_year_oldest_first(self):
        rows = [dict(private_row(), started="2016", code_name="K-02"),
                dict(private_row(), started="2011", code_name="K-01")]
        page = build.render([], rows, "2026-01-02")
        self.assertLess(page.index(">2011<"), page.index(">2016<"))
        self.assertIn("K-01", page)

    def test_html_in_data_is_escaped(self):
        rows = [private_row(title="<script>x</script>")]
        page = build.render([], rows, "2026-01-02")
        self.assertNotIn("<script>x", page)


if __name__ == "__main__":
    unittest.main()
