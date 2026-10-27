"""Offline tests for the topic and stack-family counts in build.py. Every value here is made up."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build  # noqa: E402
from test_build import private_row  # noqa: E402

STACKS = {"families": [{"name": "Java and Spring", "tools": ["Java", "Spring Boot"]},
                       {"name": "C, C++ and Unity", "tools": ["C", "Unity"]}]}


class Filters(unittest.TestCase):

    def test_slug(self):
        self.assertEqual(build.slug("C, C++ and Unity"), "c-c-and-unity")
        self.assertEqual(build.slug("Java and Spring"), "java-and-spring")

    def test_topic_counts_sorted_by_count_then_topic_order(self):
        rows = [private_row(topic="games"), private_row(topic="apps"), private_row(topic="apps")]
        self.assertEqual(build.topic_counts(rows), [("apps", "Apps", 2), ("games", "Games", 1)])

    def test_family_counts_count_rows_not_tools(self):
        rows = [private_row(stack=["Java", "Spring Boot"]), private_row(stack=["C"])]
        self.assertEqual(build.family_counts(rows, STACKS),
                         [("c-c-and-unity", "C, C++ and Unity", 1), ("java-and-spring", "Java and Spring", 1)])

    def test_family_summary_levels_and_tools(self):
        rows = [private_row(started="2011", stack=["Java"]),
                private_row(started="2012-03", stack=["Java", "Spring Boot"]),
                private_row(started="2012-05", stack=["Spring Boot"])]
        s = build.family_summary("Java and Spring", rows, STACKS, ["2011", "2012", "2013"])
        self.assertEqual((s["count"], s["first"], s["last"], s["used"]), (3, "2011", "2012", 2))
        self.assertEqual(s["cells"], [("2011", 1), ("2012", 2), ("2013", 0)])
        self.assertEqual(s["tools"], [("Java", 2), ("Spring Boot", 2)])


if __name__ == "__main__":
    unittest.main()
