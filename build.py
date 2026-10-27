#!/usr/bin/env python3
"""Build the BNI Tech lab page.

  python3 build.py                 # write _site/index.html (and an empty .nojekyll)
  python3 build.py --check         # validate data/*.json only, write nothing
  python3 build.py --out DIR       # write somewhere else

Reads, all inside this repository:
  data/marked.json   the rows Dawn chose to show: ideas, works and notes, each with one topic
                     from TOPICS. The private master list never lives here, and check_rows()
                     rejects any field it does not know.
  data/eras.json     what Dawn was doing in each period; the History headers.
  data/stacks.json   every tool name a row uses, mapped to one stack family.
  page.html          the template, with the CSS and the small script that opens years and cards
                     and filters by chip; render() fills its five placeholders.
  git history        the date of the last commit that touched data/ ("Data changed" on the page).

Writes one static page: a year strip and legend, topic and stack-family chips, and the History,
where rows sit under the era they started in, one line per year, grouped by stage, each title
with a detail card. Everything on the page is rendered here, at build time.

--check fails when a row has a bad field, kind or topic, when an era is malformed, or when a tool
a row uses is in no family or in two. A build also prints a "still running?" line for each running
row without a repo whose as_of is more than twelve months old; that is the log only, not a failure.

The build makes no network call and needs no token. It needs a git checkout with full history and
fails on a shallow one. Standard library only.
"""
import argparse
import datetime as dt
import html
import json
import os
import re
import subprocess
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
DATE = re.compile(r"^\d{4}(-(0[1-9]|1[0-2]))?\Z")
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
    in STAGE_ORDER, and within a stage the later start first (the order the History shows)."""
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


def all_years(rows, today):
    """Every year from the earliest start to today's year, inclusive; no rows, no years."""
    if not rows:
        return []
    first = min(int(r["started"][:4]) for r in rows)
    return [str(y) for y in range(first, int(today[:4]) + 1)]


def strip(rows, years):
    """One cell per year for the year strip: how many rows started then, and how many of those are running."""
    return [{"year": y,
             "count": sum(1 for r in rows if r["started"][:4] == y),
             "running": sum(1 for r in rows if r["started"][:4] == y and r["stage"] == "running")}
            for y in years]


def counts(rows):
    """The legend totals; `first_year` is empty when there are no rows."""
    return {"total": len(rows),
            "running": sum(1 for r in rows if r["stage"] == "running"),
            "finished": sum(1 for r in rows if r["stage"] == "finished"),
            "first_year": min((r["started"][:4] for r in rows), default="")}


def data_changed_date(run=subprocess.check_output):
    """The date (YYYY-MM-DD, in UTC like the "page built" date) of the last commit that touched
    data/, read from git as a Unix timestamp. A shallow checkout, or a history with no commit
    touching data/, would give a wrong or empty date, so both are refused. `run` is a parameter
    only so tests can fake git."""
    if run(["git", "rev-parse", "--is-shallow-repository"], cwd=HERE, text=True).strip() == "true":
        raise RuntimeError("shallow checkout: set fetch-depth: 0 in the workflow")
    stamp = run(["git", "log", "-1", "--format=%ct", "--", "data"], cwd=HERE, text=True).strip()
    if not stamp:
        raise RuntimeError("no commit touches data/")
    return dt.datetime.fromtimestamp(int(stamp), dt.timezone.utc).strftime("%Y-%m-%d")


def stale_running(rows, today):
    """Log lines for running ideas without a repo whose as_of is older than twelve months: the
    month 12 months before today's month is the line, and as_of strictly before it is stale.
    A bare-year as_of counts as January. These go to the build log, never to the page."""
    line = "%04d-%s" % (int(today[:4]) - 1, today[5:7])
    out = []
    for r in rows:
        as_of = r.get("as_of")
        if r["stage"] != "running" or r.get("repo") or not as_of:
            continue
        month = as_of if len(as_of) == 7 else as_of + "-01"
        if month < line:
            out.append("still running? %s (as_of %s)" % (r["title"], as_of))
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


STAGE_WORD = {"finished": "finished", "running": "running", "stopped": "stopped", "retired": "retired",
              "planned": "planned", "thought": "idea"}  # the word a card and a group label use for each stage
TAGGED_KINDS = ("contribution", "note")  # kinds that get a small tag after the title
PLACEHOLDER = re.compile(r"\{\{(STRIP|LEGEND|FILTERS|SUMMARIES|HISTORY)\}\}")


def attr(value):
    """Text made safe inside a double-quoted HTML attribute."""
    return html.escape(str(value), quote=True)


def _plural(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _axis(year_list):
    """Year labels under a row of per-year cells: the first, middle and last year, each under its own cell."""
    marks = {year_list[0], year_list[(len(year_list) - 1) // 2], year_list[-1]} if year_list else set()
    spans = "".join(f"<span>{y}</span>" if y in marks else "<span></span>" for y in year_list)
    return f'<div class="axis" aria-hidden="true">{spans}</div>'


def render_strip(cells):
    """The year strip: one button per year, a bar scaled to the busiest year with its running share
    in yellow, and the count under it. A year with rows never drops below 3%; an empty year is 0."""
    if not cells:
        return ""
    top = max(c["count"] for c in cells)
    out = []
    for c in cells:
        bar = max(3, round(100 * c["count"] / top)) if c["count"] else 0
        run = round(100 * c["running"] / c["count"]) if c["count"] else 0
        label = f'{c["year"]}: {_plural(c["count"], "thing")}, {c["running"]} running'
        out.append(f'<button type="button" class="cell" data-year="{attr(c["year"])}" aria-label="{attr(label)}">'
                   f'<span class="bar" style="height: {bar}%"><span class="run" style="height: {run}%"></span></span>'
                   f'<span class="n">{c["count"]}</span></button>')
    return f'<div class="strip" role="group" aria-label="Things per year">{"".join(out)}</div>{_axis([c["year"] for c in cells])}'


def render_legend(rows, built, changed):
    """Two lines under the strip: the totals, with the running count in the yellow tag that also
    explains the yellow bars, then the two dates."""
    c = counts(rows)
    if not c["total"]:
        return ""
    return (f'<p class="legend"><span>{_plural(c["total"], "thing")} since {attr(c["first_year"])}</span> · '
            f'<span class="tag">{c["running"]} running</span> · <span>{c["finished"]} finished</span></p>'
            f'<p class="legend dates">Data changed {attr(changed)} · page built {attr(built)}</p>')


def _chip(pick, label, n, pressed=False):
    return (f'<button type="button" class="chip" data-pick="{attr(pick)}" aria-pressed="{"true" if pressed else "false"}">'
            f'{html.escape(label)} <span class="count">{n}</span></button>')


def render_filters(rows, stacks):
    """The By topic / By stack switch and one chip row per mode; the stack row starts hidden."""
    if not rows:
        return ""
    first = _chip("all", "All", len(rows), pressed=True)
    topics = "".join(_chip(key, label, n) for key, label, n in topic_counts(rows))
    families = "".join(_chip(key, name, n) for key, name, n in family_counts(rows, stacks))
    return ('<div class="switch" role="group" aria-label="Group the history">'
            '<button type="button" data-mode="topic" aria-pressed="true">By topic</button>'
            '<button type="button" data-mode="stack" aria-pressed="false">By stack</button></div>'
            f'<div class="chips" data-mode="topic">{first}{topics}</div>'
            f'<div class="chips" data-mode="stack" hidden>{first}{families}</div>')


def render_summaries(rows, stacks, year_list):
    """One hidden summary box per stack family that has rows; the page script shows the picked one."""
    out = []
    for _, name, _ in family_counts(rows, stacks):
        s = family_summary(name, rows, stacks, year_list)
        if s["first"] == s["last"]:
            span = f'only {s["first"]}'
        else:
            span = f'{s["first"]} to {s["last"]} · used in {s["used"]} of {len(year_list)} years'
        used = ", ".join(year for year, level in s["cells"] if level)
        cells = "".join(f'<span class="l{level}"></span>' for _, level in s["cells"])
        tools = " · ".join(f"{html.escape(tool)} {n}" for tool, n in s["tools"])
        out.append(f'<div class="family" data-family="{attr(s["slug"])}" hidden>'
                   f'<p class="fhead"><span class="fname">{html.escape(name)}</span>'
                   f'<span class="made">{s["count"]} made</span></p>'
                   f'<p class="fspan">{html.escape(span)}</p>'
                   f'<div class="use" role="img" aria-label="{attr(name + " used in " + used)}">{cells}</div>'
                   f'{_axis(year_list)}'
                   f'<p class="tools">{tools}</p></div>')
    return "".join(out)


def _card_when(r):
    """The date line on a detail card: "since Mar 2019" for running work, else years(row); then the stage."""
    if r["stage"] == "running":
        started = r["started"]
        date = f"since {month_name(started)} {started[:4]}" if len(started) == 7 else f"since {started}"
    else:
        date = years(r)
    return f'{date} · {STAGE_WORD[r["stage"]]}'


def render_row(r, family_by_tool):
    """One row: its title is a button, and the detail card under it holds the dates, the summary,
    the stack and the GitHub link. Private rows show the code name and a fixed sentence instead."""
    families = []
    for tool in r.get("stack", []):
        key = slug(family_by_tool[tool]) if tool in family_by_tool else ""
        if key and key not in families:
            families.append(key)
    private = r["mode"] == "private"
    code = f'<span class="code">{html.escape(r["code_name"])}</span> ' if private else ""
    kind = (f' <span class="kind">{html.escape(r["kind"])}</span>'
            if r.get("kind") in TAGGED_KINDS and not private else "")
    if private:
        summary = (f'Shown under the code name {html.escape(r["code_name"])}. '
                   "Only the title, stack, stage and dates are public.")
    else:
        summary = inline(r.get("summary", ""))
    stack = ", ".join(html.escape(s) for s in r.get("stack", []))
    card = (f'<span class="cwhen">{_card_when(r)}</span>'
            + (f"<p>{summary}</p>" if summary else "")
            + (f'<span class="cstack">{stack}</span>' if stack else "")
            + (f'<a href="https://github.com/{attr(r["repo"])}">Code on GitHub</a>' if r.get("repo") else ""))
    return (f'<div class="row" data-stage="{attr(r["stage"])}" data-topic="{attr(r.get("topic", ""))}" '
            f'data-families="{attr(" ".join(families))}" data-title="{attr(r["title"])}">'
            f'<button type="button" class="name" aria-expanded="false">{code}{html.escape(r["title"])}{kind}</button>'
            f'<div class="card" role="tooltip">{card}</div></div>')


def render_year(entry, family_by_tool):
    """One year inside a block: the toggle with the tally, the preview and the count, then the rows
    grouped by stage in STAGE_ORDER. Rows keep history()'s order inside each group."""
    groups = []
    for stage in STAGE_ORDER:
        rs = [r for r in entry["rows"] if r["stage"] == stage]
        if rs:
            groups.append(f'<div class="group" data-stage="{stage}">'
                          f'<p class="glabel">{STAGE_WORD[stage].capitalize()} · {len(rs)}</p>'
                          f'{"".join(render_row(r, family_by_tool) for r in rs)}</div>')
    return (f'<div class="year" data-year="{attr(entry["year"])}" data-count="{entry["count"]}">'
            f'<button type="button" class="toggle" aria-expanded="false"><span class="y">{attr(entry["year"])}</span>'
            f'<span class="sum"><span class="tally">{html.escape(entry["tally"])}</span>'
            f'<span class="preview">{html.escape(entry["preview"])}</span></span>'
            f'<span class="n">{entry["count"]} +</span></button>'
            f'<div class="rows">{"".join(groups)}</div></div>')


def render_block(block, family_by_tool):
    """One era (or gap) block: its header, then one year row per year, newest first."""
    return (f'<section class="block" data-key="{attr(block["key"])}">'
            f'<header><span class="when">{html.escape(block["when"])}</span>'
            f'<span class="label">{html.escape(block["label"])}</span></header>'
            f'{"".join(render_year(y, family_by_tool) for y in block["years"])}</section>')


def render_history(rows, eras, stacks):
    if not rows:
        return ""
    family_by_tool = family_of(stacks)
    blocks = "".join(render_block(b, family_by_tool) for b in history(rows, eras))
    return ('<section class="history"><h2>History</h2>'
            '<p class="hint">One year opens at a time. Point at a name, or tap it, for details.</p>'
            f'{blocks}</section>')


def render(rows, eras, stacks, built, changed, today=None):
    """The whole page: page.html with its five placeholders filled. `built` and `changed` are the
    page-built and data-changed dates for the legend; `today` (default `built`) ends the year strip."""
    years_shown = all_years(rows, today or built)
    parts = {
        "STRIP": render_strip(strip(rows, years_shown)),
        "LEGEND": render_legend(rows, built, changed),
        "FILTERS": render_filters(rows, stacks),
        "SUMMARIES": render_summaries(rows, stacks, years_shown),
        "HISTORY": render_history(rows, eras, stacks),
    }
    with open(os.path.join(HERE, "page.html"), encoding="utf-8") as f:
        page = f.read()
    return PLACEHOLDER.sub(lambda m: parts[m.group(1)], page)  # one pass, so data text is never re-read as a placeholder


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
    changed = data_changed_date()  # fails a shallow checkout before anything is written
    for line in stale_running(rows, built):
        print(line)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "index.html"), "w", encoding="utf-8") as f:
        f.write(render(rows, eras, stacks, built, changed))
    open(os.path.join(a.out, ".nojekyll"), "w").close()
    print("built %s: %d row(s)" % (a.out, len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
