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
