"""Offline tests for build.py. Every value here is made up."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build  # noqa: E402

def private_row(**extra):
    row = {"mode": "private", "code_name": "K-01", "title": "Example idea",
           "stack": ["Java"], "stage": "planned", "started": "2015", "topic": "apps"}
    row.update(extra)
    return row


class CheckRows(unittest.TestCase):

    def test_valid_private_and_public_rows(self):
        rows = [private_row(),
                {"mode": "public", "title": "Example game", "stack": ["C"], "stage": "finished",
                 "started": "2011-12", "restarted": ["2012-07"], "repo": "example/example-game",
                 "topic": "games"}]
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

    def test_topic_is_required_and_known(self):
        row = private_row()
        del row["topic"]
        self.assertTrue(any("topic" in p for p in build.check_rows([row])))
        self.assertTrue(any("topic" in p for p in build.check_rows([private_row(topic="hobby")])))
        self.assertEqual(build.check_rows([private_row(topic="life")]), [])


STACKS = {"families": [{"name": "Java and Spring", "tools": ["Java", "Spring Boot"]},
                       {"name": "Databases", "tools": ["MySQL"]}]}


class CheckStacks(unittest.TestCase):
    def test_valid_map_and_lookup(self):
        rows = [private_row(stack=["Java", "MySQL"])]
        self.assertEqual(build.check_stacks(STACKS, rows), [])
        self.assertEqual(build.family_of(STACKS)["MySQL"], "Databases")

    def test_unmapped_tool_fails_check(self):
        problems = build.check_stacks(STACKS, [private_row(stack=["Kotlin"])])
        self.assertTrue(any("Kotlin" in p for p in problems))

    def test_tool_in_two_families_fails_check(self):
        twice = {"families": [{"name": "A", "tools": ["Java"]}, {"name": "B", "tools": ["Java"]}]}
        self.assertTrue(any("Java" in p for p in build.check_stacks(twice, [])))

    def test_bad_shape_fails_check(self):
        self.assertTrue(build.check_stacks([], []))
        self.assertTrue(build.check_stacks({"families": [{"name": "A"}]}, []))


class Render(unittest.TestCase):
    def test_years_read_first_run_then_restarts(self):
        row = private_row(started="2011-12", ended="2012-01", restarted=["2012-07", "2026-03"])
        self.assertEqual(build.years(row), "2011-12 to 2012-01 &middot; again 2012-07 &middot; again 2026-03")

    def test_years_never_mentions_a_last_commit(self):
        row = private_row(stage="running", as_of="2026-10")
        row["updated"] = "2026-10-20"
        self.assertEqual(build.years(row), "2015 &middot; as of 2026-10")

    def test_html_in_data_is_escaped(self):
        rows = [private_row(title="<script>x</script>")]
        page = build.render(rows, [], STACKS, "2026-01-02", "2026-01-01")
        self.assertNotIn("<script>x", page)

    def test_kind_must_be_known(self):
        problems = build.check_rows([private_row(kind="hobby")])
        self.assertTrue(any("kind" in p for p in problems))
        self.assertEqual(build.check_rows([private_row(kind="contribution")]), [])

    def test_eras_are_checked(self):
        bad = build.check_eras([{"from": "yesterday", "label": "x"}, {"from": "2011", "to": "2012", "label": "x", "colour": "red"}])
        self.assertEqual(len(bad), 2)
        eras = [{"from": "2011-03", "to": "2013-02", "label": "Student", "where": "Example University"},
                {"from": "2018-12", "to": "2021-07", "label": "Software engineer", "where": "Example Corp"}]
        self.assertEqual(build.check_eras(eras), [])


if __name__ == "__main__":
    unittest.main()
