#!/usr/bin/env python3
"""Rolling prod-release pages in the GitHub wiki, driven by deploy events.

  stage-deployed <tag>  open page = PRs from the last prod tag up to <tag>
  prod-deployed  <tag>  stamp the open page as deployed, open the next page

State lives in wiki/release-state.json; every page is re-rendered from it.
"""
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys

WIKI = pathlib.Path("wiki")
STATE_FILE = WIKI / "release-state.json"
REPO = os.environ["GITHUB_REPOSITORY"]


def now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def gh_json(path, paginate=False):
    args = ["gh", "api", path] + (["--paginate", "--slurp"] if paginate else [])
    out = subprocess.run(args, check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def prs_between(base, head, first_seen, stage_tag):
    """Merged PRs reachable from head but not from base."""
    pages = gh_json(f"repos/{REPO}/compare/{base}...{head}", paginate=True)
    commits = [c for page in pages for c in page["commits"]]
    prs = {}
    for c in commits:
        for pr in gh_json(f"repos/{REPO}/commits/{c['sha']}/pulls"):
            n = pr["number"]
            if pr.get("merged_at") and n not in prs:
                prs[n] = {
                    "number": n,
                    "title": pr["title"],
                    # Commit author name: matches the PR author for squash merges
                    "author": c["commit"]["author"]["name"],
                    "url": pr["html_url"],
                    "first_on_stage": first_seen.get(n) or stage_tag,
                }
    return sorted(prs.values(), key=lambda p: p["number"])


def page_name(n):
    return f"Prod-Release-{n}"


def new_page(number, base):
    return {"number": number, "base": base, "head": None, "prs": [], "history": []}


def render(page):
    if page.get("prod_deployed_at"):
        status = f"✅ Deployed to prod **{page['prod_deployed_at']}** (`{page['head']}`)"
    elif page["head"]:
        status = f"🟡 On stage (`{page['head']}`), not yet in prod"
    else:
        status = "⚪ Nothing deployed to stage yet"

    if page["head"]:
        rng = (f"[`{page['base']}` → `{page['head']}`]"
               f"(https://github.com/{REPO}/compare/{page['base']}...{page['head']})")
    else:
        rng = f"from `{page['base']}`"

    out = [
        f"# Prod Release {page['number']}", "",
        f"**Status:** {status}  ",
        f"**Range:** {rng}  ",
        f"**PRs:** {len(page['prs'])}", "",
        "## Pull requests", "",
    ]
    if page["prs"]:
        out += ["| PR | Title | Author | First on stage |",
                "|----|-------|--------|----------------|"]
        for p in page["prs"]:
            title = p["title"].replace("|", "\\|")
            out.append(f"| [#{p['number']}]({p['url']}) | {title} | {p['author']} "
                       f"| `{p['first_on_stage'] or '—'}` |")
    else:
        out.append("_None yet._")

    out += ["", "## Deploy history", ""]
    out += [f"- **{h['env']}** `{h['tag']}` — {h['at']}" for h in page["history"]] or ["_None yet._"]
    (WIKI / f"{page_name(page['number'])}.md").write_text("\n".join(out) + "\n")


def render_index(state):
    cur = state["current"]
    lines = ["# Prod Releases", "", f"- 🟡 [[{page_name(cur['number'])}]] — open"]
    lines += [f"- ✅ [[{page_name(r['number'])}]] — deployed {r['prod_deployed_at']} (`{r['head']}`)"
              for r in state["releases"]]
    (WIKI / "Prod-Releases.md").write_text("\n".join(lines) + "\n")


def stage_deployed(state, tag):
    cur = state["current"]
    seen = {p["number"]: p["first_on_stage"] for p in cur["prs"]}
    cur["prs"] = prs_between(cur["base"], tag, seen, tag)
    cur["head"] = tag
    cur["history"].append({"env": "stage", "tag": tag, "at": now()})
    render(cur)
    print(f"{page_name(cur['number'])}: {len(cur['prs'])} PRs ({cur['base']}..{tag})")


def prod_deployed(state, tag):
    cur = state["current"]
    seen = {p["number"]: p["first_on_stage"] for p in cur["prs"]}
    last_stage = cur["head"]

    # Close the open page as exactly what went to prod
    cur["prs"] = prs_between(cur["base"], tag, seen, None)
    cur["head"] = tag
    cur["prod_deployed_at"] = now()
    cur["history"].append({"env": "prod", "tag": tag, "at": cur["prod_deployed_at"]})
    render(cur)
    state["releases"].insert(0, {k: cur[k] for k in ("number", "base", "head", "prod_deployed_at")})

    # Open the next page; if stage is already ahead of prod, carry those PRs over
    nxt = new_page(cur["number"] + 1, tag)
    if last_stage and last_stage != tag:
        nxt["prs"] = prs_between(tag, last_stage, seen, last_stage)
        if nxt["prs"]:
            nxt["head"] = last_stage
            nxt["history"].append({"env": "stage", "tag": last_stage, "at": "carried over"})
    state["current"] = nxt
    render(nxt)
    print(f"Closed {page_name(cur['number'])}, opened {page_name(nxt['number'])}")


def main():
    event, tag = sys.argv[1], sys.argv[2]

    if not STATE_FILE.exists():
        if event != "prod-deployed":
            sys.exit("No state yet: run once with prod-deployed <current prod tag> to initialise.")
        state = {"current": new_page(1, tag), "releases": []}
        render(state["current"])
        print(f"Initialised: tracking from {tag}")
    else:
        state = json.loads(STATE_FILE.read_text())
        if event == "stage-deployed":
            stage_deployed(state, tag)
        elif event == "prod-deployed":
            prod_deployed(state, tag)
        else:
            sys.exit(f"Unknown event {event}")

    render_index(state)
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")


if __name__ == "__main__":
    main()
