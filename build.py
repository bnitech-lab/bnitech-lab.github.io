#!/usr/bin/env python3
"""Build the BNI Tech idea page.

  python3 build.py                 # fetch cards from GitHub, write _site/index.html
  python3 build.py --check         # validate data/*.json only, no network
  python3 build.py --out DIR       # write somewhere else

Cards come from the README of each repo in data/cards.json: the lines between
<!-- bnitech:card --> and <!-- /bnitech:card -->. Ideas by year come from
data/marked.json, rows Dawn has chosen to show. The private master list never
lives in this repo, and check_rows() rejects any field it does not know.

Standard library only. GITHUB_TOKEN, when set, raises the API rate limit.
"""
import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
API = "https://api.github.com"

STAGES = {
    "thought": "Thought only",
    "planned": "Planned",
    "stopped": "Stopped mid-build",
    "finished": "Finished",
    "running": "Running",
    "retired": "Retired",
}
COMMON_FIELDS = {"mode", "title", "stack", "stage", "started", "restarted", "ended", "as_of"}
ALLOWED = {
    "private": COMMON_FIELDS | {"code_name"},
    "public": COMMON_FIELDS | {"summary", "repo"},
}
DATE = re.compile(r"^\d{4}(-\d{2})?$")
REPO = re.compile(r"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$")
CARD = re.compile(r"<!--\s*bnitech:card\s*-->(.*?)<!--\s*/bnitech:card\s*-->", re.S)
LINE = re.compile(r"^\s*-\s*\*\*(.+?):\*\*\s*(.+?)\s*$")
MINUTES = re.compile(r"^Try it \(about (\d+) minutes?\)$")


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
    return problems


def parse_card(readme):
    """Pull problem, audience, try-it text and minutes out of a README card block."""
    m = CARD.search(readme)
    if not m:
        raise ValueError("no bnitech:card block")
    fields = {}
    for line in m.group(1).strip().splitlines():
        lm = LINE.match(line)
        if lm:
            fields[lm.group(1).strip()] = lm.group(2)
    card = {"problem": fields.get("Problem"), "who": fields.get("Who it helps")}
    for key, value in fields.items():
        mm = MINUTES.match(key)
        if mm:
            card["minutes"] = int(mm.group(1))
            card["try"] = value
    missing = [k for k in ("problem", "who", "try") if not card.get(k)]
    if missing:
        raise ValueError("card block is missing: %s" % ", ".join(missing))
    return card


def get(path, raw=False):
    req = urllib.request.Request(API + path)
    req.add_header("Accept", "application/vnd.github.raw" if raw else "application/vnd.github+json")
    req.add_header("User-Agent", "bnitech-lab-build")
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode("utf-8")
    return body if raw else json.loads(body)


def last_commit(repo):
    commits = get("/repos/%s/commits?per_page=1" % repo)
    return commits[0]["commit"]["committer"]["date"][:10]


def fetch_card(entry):
    repo = entry["repo"]
    meta = get("/repos/" + repo)
    card = parse_card(get("/repos/%s/readme" % repo, raw=True))
    card.update({
        "repo": repo,
        "title": entry.get("title") or meta["name"],
        "url": meta["html_url"],
        "license": (meta.get("license") or {}).get("spdx_id"),
        "updated": last_commit(repo),
    })
    return card


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
    if row.get("stage") == "running":
        if row.get("updated"):
            span += " &middot; last commit " + row["updated"]
        elif row.get("as_of"):
            span += " &middot; as of " + row["as_of"]
    return span


def render_card(c):
    lic = " &middot; %s licence" % html.escape(c["license"]) if c.get("license") and c["license"] != "NOASSERTION" else ""
    return f"""
      <article class="card">
        <h3><a href="{html.escape(c['url'])}">{html.escape(c['title'])}</a></h3>
        <p class="problem">{inline(c['problem'])}</p>
        <p class="who"><span class="label">For</span> {inline(c['who'])}</p>
        <div class="try">
          <p class="try-head"><span class="label">Try it</span><span class="minutes">about {c['minutes']} min</span></p>
          <p>{inline(c['try'])}</p>
        </div>
        <p class="meta"><a href="{html.escape(c['url'])}">{html.escape(c['repo'])}</a> &middot; last commit {c['updated']}{lic}</p>
      </article>"""


def render_row(r):
    stage = STAGES[r["stage"]]
    stack = ", ".join(html.escape(s) for s in r.get("stack", []))
    if r["mode"] == "private":
        name = f'<span class="code-name">{html.escape(r["code_name"])}</span> {html.escape(r["title"])}'
    elif r.get("repo"):
        name = f'<a href="https://github.com/{html.escape(r["repo"])}">{html.escape(r["title"])}</a>'
    else:
        name = html.escape(r["title"])
    summary = f'<p class="summary">{inline(r["summary"])}</p>' if r.get("summary") else ""
    return f"""
        <li class="row">
          <p class="row-title">{name}</p>
          {summary}
          <p class="row-meta"><span class="stage stage-{r['stage']}">{stage}</span> {years(r)}{(' &middot; ' + stack) if stack else ''}</p>
        </li>"""


def render(cards, rows, built):
    by_year = {}
    for r in sorted(rows, key=lambda r: r["started"], reverse=True):  # newest first, within a year too
        by_year.setdefault(r["started"][:4], []).append(r)
    ideas = ""
    if rows:
        groups = "".join(
            f'\n      <section class="year"><h3>{y}</h3><ul>{"".join(render_row(r) for r in items)}\n      </ul></section>'
            for y, items in by_year.items())
        ideas = f"""
    <section class="ideas" aria-labelledby="ideas-h">
      <h2 id="ideas-h">Ideas by the year they started</h2>
      <p class="note">Some ideas are shown under a code name, with only a title, stack, stage and dates.</p>{groups}
    </section>"""
    with open(os.path.join(HERE, "page.html"), encoding="utf-8") as f:
        page = f.read()
    return (page.replace("{{CARDS}}", "".join(render_card(c) for c in cards))
                .replace("{{IDEAS}}", ideas)
                .replace("{{BUILT}}", built))


def load(name):
    with open(os.path.join(HERE, "data", name), encoding="utf-8") as f:
        return json.load(f)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--check", action="store_true")
    p.add_argument("--out", default=os.path.join(HERE, "_site"))
    a = p.parse_args(argv)
    rows = load("marked.json")
    problems = check_rows(rows)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    if a.check:
        print("data ok: %d marked row(s)" % len(rows))
        return 0
    cards = [fetch_card(e) for e in load("cards.json")]
    for r in rows:
        if r.get("repo"):
            r["updated"] = last_commit(r["repo"])
    built = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "index.html"), "w", encoding="utf-8") as f:
        f.write(render(cards, rows, built))
    open(os.path.join(a.out, ".nojekyll"), "w").close()
    print("built %s: %d card(s), %d row(s)" % (a.out, len(cards), len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
