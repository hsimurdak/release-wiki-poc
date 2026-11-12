# release-wiki-poc

Proof of concept: generate a GitHub wiki page per production release from deploy events.

This repo contains no application code. The PRs, authors and tags are placeholders used to
exercise the workflow.

## How it works

`.github/workflows/release-wiki.yml` listens for two events:

| Event | Effect on the wiki |
|---|---|
| `stage-deployed` `<tag>` | The open page lists every merged PR between the last prod tag and `<tag>`. |
| `prod-deployed` `<tag>` | The open page is stamped with the prod deploy date and a new page is opened. PRs already on stage but newer than `<tag>` carry over. |

State is kept in `release-state.json` in the wiki, and each page is re-rendered from it.

## Triggering

From a deploy system, after the deploy succeeds:

```bash
gh api repos/OWNER/REPO/dispatches \
  -f event_type=stage-deployed \
  -f "client_payload[tag]=v1.1.0"
```

Or run **Release wiki** manually from the Actions tab.

## First run

1. Create any page in the Wiki tab so the wiki repo exists.
2. Run the workflow with `prod-deployed` and the tag currently in prod to set the starting point.
