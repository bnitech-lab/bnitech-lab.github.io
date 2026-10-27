#!/usr/bin/env python3
"""Build the BNI Tech lab page.

  python3 build.py                 # write _site/index.html
  python3 build.py --check         # validate data/*.json only, write nothing
  python3 build.py --out DIR       # write somewhere else

The page lists the rows in data/marked.json, the ideas, works and notes Dawn has chosen to
show, by the year they started. Every row carries one topic from TOPICS. data/eras.json says
what I was doing in each period, and data/stacks.json maps every tool name a row uses to one
stack family; --check fails when a tool is in no family. The private master list never lives
in this repo, and check_rows() rejects any field it does not know.

The build reads only the files in this repository. It makes no network call and needs no token.
Standard library only.
"""
import argparse
import datetime as dt
import html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

STAGE_ORDER = ["finished", "running", "stopped", "retired", "planned", "thought"]  # order inside a year
STAGES = {
    "thought": "Thought only",
    "planned": "Planned",
    "stopped": "Stopped mid-build",
    "finished": "Finished",
    "running": "Running",
    "retired": "Retired",
}
COMMON_FIELDS = {"mode", "title", "stack", "stage", "started", "restarted", "ended", "as_of", "kind", "topic"}
KINDS = {"project", "contribution", "note"}  # contribution: my part in someone else's work; note: writing, study, not software
TOPICS = {"games": "Games", "apps": "Apps", "web": "Web and backend", "ai": "AI tools", "study": "Study", "life": "Life"}  # insertion order is the display order for ties
ALLOWED = {
    "private": COMMON_FIELDS | {"code_name"},
    "public": COMMON_FIELDS | {"summary", "repo"},
}
DATE = re.compile(r"^\d{4}(-\d{2})?$")
REPO = re.compile(r"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$")


ERA_FIELDS = {"from", "to", "label", "where"}


def check_eras(eras):
    """Return problems with data/eras.json: what I was doing, by period, shown beside each year."""
    problems = []
    if not isinstance(eras, list):
        return ["eras.json must hold a list"]
    for i, e in enumerate(eras):
        where = "era %d" % (i + 1)
        if not isinstance(e, dict):
            problems.append("%s: not an object" % where)
            continue
        extra = sorted(set(e) - ERA_FIELDS)
        if extra:
            problems.append("%s: fields not allowed: %s" % (where, ", ".join(extra)))
        if not e.get("from") or not DATE.match(str(e.get("from"))):
            problems.append("%s: from must be YYYY or YYYY-MM" % where)
        if "to" in e and not DATE.match(str(e["to"])):
            problems.append("%s: to must be YYYY or YYYY-MM" % where)
        if not e.get("label"):
            problems.append("%s: label is required" % where)
    return problems


def check_stacks(stacks, rows):
    """Return problems with data/stacks.json: every tool belongs to exactly one family, and every
    tool a marked row uses is mapped."""
    if not isinstance(stacks, dict) or not isinstance(stacks.get("families"), list):
        return ["stacks.json must hold an object with a families list"]
    problems = []
    seen = {}  # tool -> family that claimed it first
    for i, fam in enumerate(stacks["families"]):
        where = "family %d" % (i + 1)
        if not isinstance(fam, dict):
            problems.append("%s: not an object" % where)
            continue
        name = fam.get("name")
        if not name or not isinstance(name, str):
            problems.append("%s: name is required" % where)
        else:
            where = "family %s" % name
        tools = fam.get("tools")
        if not isinstance(tools, list) or not tools or not all(isinstance(t, str) for t in tools):
            problems.append("%s: tools must be a non-empty list of names" % where)
            continue
        for tool in tools:
            if tool in seen:
                problems.append("%s: tool %s is already in family %s" % (where, tool, seen[tool]))
            else:
                seen[tool] = name
    if isinstance(rows, list):
        used = set()
        for row in rows:
            stack = row.get("stack", []) if isinstance(row, dict) else []
            if isinstance(stack, list):
                used.update(s for s in stack if isinstance(s, str))
        for tool in sorted(used - set(seen)):
            problems.append("tool %s is used in marked.json but is in no stack family" % tool)
    return problems


def family_of(stacks):
    """Map each tool name to the name of the family that holds it."""
    return {tool: fam["name"] for fam in stacks["families"] for tool in fam["tools"]}


def slug(name):
    """Lowercase name with every run of characters outside a-z and 0-9 turned into one hyphen."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def topic_counts(rows):
    """(key, label, count) for each topic that has rows, most rows first; ties keep TOPICS order."""
    counts = {key: 0 for key in TOPICS}
    for row in rows:
        if row.get("topic") in counts:
            counts[row["topic"]] += 1
    found = [(key, label, counts[key]) for key, label in TOPICS.items() if counts[key]]
    return sorted(found, key=lambda t: -t[2])  # sorted() is stable, so equal counts keep TOPICS order


def _uses(row, tools):
    return bool(tools.intersection(row.get("stack", [])))


def family_counts(rows, stacks):
    """(slug, name, count) for each stack family that has rows, most rows first, then by name.
    A row counts once for a family however many of its tools the row lists."""
    found = []
    for fam in stacks["families"]:
        tools = set(fam["tools"])
        n = sum(1 for row in rows if _uses(row, tools))
        if n:
            found.append((slug(fam["name"]), fam["name"], n))
    return sorted(found, key=lambda t: (-t[2], t[1]))


def _level(n):
    """Shade of one year in the family box: 0 none, 1 one row, 2 two or three, 3 four or more."""
    return 0 if n == 0 else 1 if n == 1 else 2 if n <= 3 else 3


def family_summary(name, rows, stacks, years):
    """What one stack family looks like across the years: how many rows use it, the first and last
    year it was used, the number of distinct years, a shade level for every year in `years`, and
    how many rows use each of its tools (tools no row uses are left out)."""
    fam = next((f for f in stacks["families"] if f["name"] == name), None)
    if fam is None:
        raise ValueError("no stack family named %s" % name)
    mine = [row for row in rows if _uses(row, set(fam["tools"]))]
    per_year = {}
    for row in mine:
        year = row["started"][:4]
        per_year[year] = per_year.get(year, 0) + 1
    per_tool = {}
    for row in mine:
        for tool in set(row["stack"]) & set(fam["tools"]):
            per_tool[tool] = per_tool.get(tool, 0) + 1
    return {
        "name": name,
        "slug": slug(name),
        "count": len(mine),
        "first": min(per_year) if per_year else None,
        "last": max(per_year) if per_year else None,
        "used": len(per_year),
        "cells": [(year, _level(per_year.get(year, 0))) for year in years],
        "tools": sorted(per_tool.items(), key=lambda t: (-t[1], t[0])),
    }


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def month_name(ym):
    return MONTHS[int(ym[5:7]) - 1] if len(ym) == 7 else ""


def eras_for_year(eras, year):
    """The eras that overlap a calendar year, oldest first, each with the months it covers
    inside that year when it starts or ends there ("to Jul", "from Aug", "Mar to Jul")."""
    out = []
    for e in eras:
        start, end = str(e["from"]), str(e.get("to", "9999"))
        if not (start[:4] <= year <= end[:4]):
            continue
        begins = month_name(start) if start[:4] == year else ""
        ends = month_name(end) if end[:4] == year else ""
        if begins and ends:
            span = f"{begins} to {ends}"
        elif begins:
            span = f"from {begins}"
        elif ends:
            span = f"to {ends}"
        else:
            span = ""
        out.append(dict(e, span=span))
    return out


GAP_LABEL = "Between school and work"


def _first_month(date):
    """The first month an era covers on its `from` side; a bare year means January."""
    return date if len(date) == 7 else date + "-01"


def _last_month(date):
    """The last month an era covers on its `to` side; a bare year means December."""
    return date if len(date) == 7 else date + "-12"


def _covers(e, ym):
    return _first_month(str(e["from"])) <= ym <= _last_month(str(e.get("to", "9999")))


def era_of(eras, started):
    """The era a row belongs to, or None when it belongs to none of them.

    A month (YYYY-MM) goes to the era that contains it. A bare year goes to the era covering the
    most of its twelve months (the earlier era on a tie), but only if that is more months than no
    era covers at all; otherwise the year sits between eras and the row has no era."""
    ordered = sorted(eras, key=lambda e: str(e["from"]))
    if len(started) == 7:
        return next((e for e in ordered if _covers(e, started)), None)
    months = [f"{started}-{m:02d}" for m in range(1, 13)]
    best, best_count = None, 0
    for e in ordered:
        count = sum(_covers(e, ym) for ym in months)
        if count > best_count:
            best, best_count = e, count
    uncovered = sum(not any(_covers(e, ym) for e in ordered) for ym in months)
    return best if best_count > uncovered else None


def era_key(e):
    return str(e["from"])


def tally(rows):
    """Counts by stage in STAGE_ORDER, e.g. "5 finished · 19 running · 1 idea"; empty stages are left out."""
    parts = []
    for stage in STAGE_ORDER:
        n = sum(1 for r in rows if r["stage"] == stage)
        if not n:
            continue
        word = stage if stage != "thought" else ("idea" if n == 1 else "ideas")
        parts.append(f"{n} {word}")
    return " · ".join(parts)


def preview(rows):
    """The first three titles, then "and N more"."""
    text = ", ".join(r["title"] for r in rows[:3])
    return text + (f" and {len(rows) - 3} more" if len(rows) > 3 else "")


def _when(e):
    def part(ym):
        return f"{month_name(ym)} {ym[:4]}" if len(ym) == 7 else ym
    return f"{part(str(e['from']))} to {part(str(e['to'])) if 'to' in e else 'now'}"


def _gap_key(eras, year):
    """Where a gap block sorts: the month after the latest era that ends inside the year
    (December has no month after inside the year), else the year's January."""
    ends = [str(e["to"]) for e in eras
            if len(str(e.get("to", ""))) == 7 and str(e["to"])[:4] == year and str(e["to"])[5:] != "12"]
    if not ends:
        return f"{year}-01"
    last = max(ends)
    return f"{year}-{int(last[5:]) + 1:02d}"


def _year_entries(rows):
    """One entry per year, newest first; inside a year finished work first, then the other stages
    in STAGE_ORDER, and within a stage the later start first (the order render() uses)."""
    rank = {s: i for i, s in enumerate(STAGE_ORDER)}
    ordered = sorted(sorted(rows, key=lambda r: r["started"], reverse=True),
                     key=lambda r: rank.get(r["stage"], len(rank)))
    by_year = {}
    for r in ordered:
        by_year.setdefault(r["started"][:4], []).append(r)
    return [{"year": y, "rows": rs, "count": len(rs), "tally": tally(rs), "preview": preview(rs)}
            for y, rs in sorted(by_year.items(), reverse=True)]


def history(rows, eras):
    """The History as data: blocks newest first, one per era, plus one per year that falls between
    eras. Each block is {"key", "label", "when", "years"}; a block with no rows is left out."""
    members = {}
    for r in rows:
        e = era_of(eras, r["started"])
        if e is not None:
            members.setdefault(("era", era_key(e)), []).append(r)
        else:
            members.setdefault(("gap", r["started"][:4]), []).append(r)
    blocks = []
    for e in eras:
        rs = members.get(("era", era_key(e)))
        if rs:
            label = f"{e['label']} · {e['where']}" if e.get("where") else e["label"]
            blocks.append({"key": era_key(e), "label": label, "when": _when(e), "years": _year_entries(rs)})
    for (kind, year), rs in members.items():
        if kind == "gap":
            blocks.append({"key": _gap_key(eras, year), "label": GAP_LABEL, "when": year,
                           "years": _year_entries(rs)})
    return sorted(blocks, key=lambda b: b["key"], reverse=True)


def check_rows(rows):
    """Return a list of problems with the marked rows; empty means valid."""
    problems = []
    if not isinstance(rows, list):
        return ["marked.json must hold a list"]
    for i, row in enumerate(rows):
        where = "row %d" % (i + 1)
        if not isinstance(row, dict):
            problems.append("%s: not an object" % where)
            continue
        mode = row.get("mode")
        if mode not in ALLOWED:
            problems.append("%s: mode must be public or private" % where)
            continue
        extra = sorted(set(row) - ALLOWED[mode])
        if extra:
            problems.append("%s: fields not allowed in %s mode: %s" % (where, mode, ", ".join(extra)))
        for key in ("title", "stage", "started"):
            if not row.get(key):
                problems.append("%s: %s is required" % (where, key))
        if mode == "private" and not row.get("code_name"):
            problems.append("%s: code_name is required in private mode" % where)
        if row.get("stage") and row["stage"] not in STAGES:
            problems.append("%s: stage must be one of %s" % (where, ", ".join(STAGES)))
        stack = row.get("stack", [])
        if not isinstance(stack, list) or not all(isinstance(s, str) for s in stack):
            problems.append("%s: stack must be a list of names" % where)
        for key in ("started", "ended", "as_of"):
            if key in row and not DATE.match(str(row[key])):
                problems.append("%s: %s must be YYYY or YYYY-MM" % (where, key))
        restarted = row.get("restarted", [])
        if not isinstance(restarted, list) or not all(DATE.match(str(d)) for d in restarted):
            problems.append("%s: restarted must be a list of YYYY or YYYY-MM" % where)
        if "repo" in row and not REPO.match(str(row["repo"])):
            problems.append("%s: repo must look like owner/name" % where)
        if row.get("stage") == "running" and not row.get("repo") and not row.get("as_of"):
            problems.append("%s: a running idea without a repo needs as_of" % where)
        if "kind" in row and row["kind"] not in KINDS:
            problems.append("%s: kind must be one of %s" % (where, ", ".join(sorted(KINDS))))
        if not row.get("topic"):
            problems.append("%s: topic is required" % where)
        elif row["topic"] not in TOPICS:
            problems.append("%s: topic must be one of %s" % (where, ", ".join(TOPICS)))
    return problems


def inline(text):
    """Escape text, then turn `code` spans into <code>."""
    parts = text.split("`")
    out = []
    for i, part in enumerate(parts):
        out.append(("<code>%s</code>" if i % 2 else "%s") % html.escape(part))
    return "".join(out)


def years(row):
    span = row["started"]
    if row.get("ended"):
        span += " to " + row["ended"]
    for d in row.get("restarted", []):
        span += " &middot; again " + d
    if row.get("stage") == "running" and row.get("as_of"):
        span += " &middot; as of " + row["as_of"]
    return span


def render_row(r):
    """One row: the title line is always visible; the summary opens on a tap."""
    stage = STAGES[r["stage"]]
    stack = ", ".join(html.escape(s) for s in r.get("stack", []))
    if r["mode"] == "private":
        name = f'<span class="code-name">{html.escape(r["code_name"])}</span> {html.escape(r["title"])}'
    elif r.get("repo"):
        name = f'<a href="https://github.com/{html.escape(r["repo"])}">{html.escape(r["title"])}</a>'
    else:
        name = html.escape(r["title"])
    meta = f'<span class="stage stage-{r["stage"]}">{stage}</span> {years(r)}{(" &middot; " + stack) if stack else ""}'
    if not r.get("summary"):
        return f"""
        <li class="row">
          <p class="row-title">{name}</p>
          <p class="row-meta">{meta}</p>
        </li>"""
    return f"""
        <li class="row">
          <details>
            <summary><span class="row-title">{name}</span><span class="row-meta">{meta}</span></summary>
            <p class="summary">{inline(r["summary"])}</p>
          </details>
        </li>"""


def kind_of(r):
    if r["stage"] in ("thought", "planned"):
        return "note"
    return r.get("kind", "project")


def render_year(year, items, eras=()):
    groups = [("project", None), ("contribution", "Contributions"), ("note", "Ideas and notes")]
    labels = "".join(
        f'<p class="era">{html.escape(e["label"])}{("<br>" + html.escape(e["where"])) if e.get("where") else ""}'
        f'{("<br><span class=\"era-span\">" + html.escape(e["span"]) + "</span>") if e["span"] else ""}</p>'
        for e in eras_for_year(eras, year))
    out = f'\n      <section class="year"><div class="year-head"><h3>{year}</h3>{labels}</div><div class="year-body">'
    for kind, label in groups:
        rs = [r for r in items if kind_of(r) == kind]
        if not rs:
            continue
        if label:
            out += f'<p class="label">{label}</p>'
        out += f'<ul class="{kind}s">{"".join(render_row(r) for r in rs)}\n      </ul>'
    return out + "</div></section>"


def render(rows, built, eras=()):
    by_year = {}
    # Years newest first. Inside a year: finished work first, then the other stages in STAGE_ORDER,
    # and within a stage the later start first.
    rank = {s: i for i, s in enumerate(STAGE_ORDER)}
    ordered = sorted(sorted(rows, key=lambda r: r["started"], reverse=True),
                     key=lambda r: (-int(r["started"][:4]), rank.get(r["stage"], len(rank))))
    for r in ordered:
        by_year.setdefault(r["started"][:4], []).append(r)
    ideas = ""
    if rows:
        groups = "".join(render_year(y, items, eras) for y, items in by_year.items())
        ideas = f"""
    <section class="ideas" aria-labelledby="ideas-h">
      <h2 id="ideas-h">Ideas by the year they started</h2>
      <p class="note">Beside each year: what I was doing then. Some ideas are shown under a code name, with only a title, stack, stage and dates.</p>{groups}
    </section>"""
    with open(os.path.join(HERE, "page.html"), encoding="utf-8") as f:
        page = f.read()
    return page.replace("{{IDEAS}}", ideas).replace("{{BUILT}}", built)


def load(name):
    with open(os.path.join(HERE, "data", name), encoding="utf-8") as f:
        return json.load(f)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--check", action="store_true")
    p.add_argument("--out", default=os.path.join(HERE, "_site"))
    a = p.parse_args(argv)
    rows = load("marked.json")
    eras = load("eras.json") if os.path.exists(os.path.join(HERE, "data", "eras.json")) else []
    stacks = load("stacks.json")
    problems = check_rows(rows) + check_eras(eras) + check_stacks(stacks, rows)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    if a.check:
        print("data ok: %d marked row(s), %d era(s), %d stack famil(ies)"
              % (len(rows), len(eras), len(stacks["families"])))
        return 0
    built = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "index.html"), "w", encoding="utf-8") as f:
        f.write(render(rows, built, eras))
    open(os.path.join(a.out, ".nojekyll"), "w").close()
    print("built %s: %d row(s)" % (a.out, len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
