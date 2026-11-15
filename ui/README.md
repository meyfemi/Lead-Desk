# Lead Desk

A local dashboard over the lead pipeline. Stdlib Python only — nothing to install.

```bash
./start-ui.sh                 # opens http://127.0.0.1:8765
./start-ui.sh --port 9000     # different port
./start-ui.sh --no-browser    # don't auto-open a browser
```

## What it does

The lead CSVs in `leads/` stay the single source of truth. The dashboard reads and
rewrites those same files, so it and the `/find-leads` workflow can be used
interchangeably — run a scrape here, write the copy in Claude Code, send from either.

| View | Purpose |
|------|---------|
| **Overview** | Pipeline counts, status breakdown, outreach volume, follow-ups due |
| **Leads** | Search and filter every lead; select rows for bulk enrich / dry-run / send |
| **Follow-ups** | Leads whose Followup 1 or 2 date has arrived, with overdue flags |
| **Discover** | Run the whole `/find-leads` workflow, or just an Apify search you review before importing |
| **Activity** | Live output of the running job, plus `leads/send_log.txt` |

Click any row to open the lead drawer: full summary and sales edges, editable subject
and body, contact details, status, and follow-up dates. The drawer knows which touch a
lead is on — for a lead already sent and due for follow-up 1, it edits the follow-up
body and sends that instead of the first mail.

## Running /find-leads

The **Run the full workflow** card on Discover launches the same `/find-leads` workflow
you'd get by typing it in Claude Code — search, website scrape, company-specific copy,
written into the CSV. It shells out to the `claude` CLI in print mode and streams the
run into the console, a line per step, with a **Stop run** button. Expect 15–40 minutes.

The location, lead count and business categories you enter are passed in, so the
workflow skips its opening questions rather than stalling on a prompt nobody can answer.
Categories are comma-separated and replace `DEFAULT_CATEGORIES` from `.env` for that run;
the field is pre-filled with the defaults so you can edit rather than retype.

Two scopes:

- **Research & draft only** (default) — stops after Step 5. Nothing is sent; leads land
  at `Ready to Send` for you to read and dispatch from the Leads tab.
- **Research, draft and send** — the full workflow including Steps 6 and 7. Emails go
  out at the end of the run without a further prompt, so the UI confirms up front.

Requires the `claude` CLI on PATH and `ANTHROPIC_API_KEY` in `.env`; the button is
disabled with a note if either is missing. The key is passed to the CLI for that run only,
so each install bills its own account regardless of which claude.ai login the machine has.
The run is granted Bash, Read, Write and Edit — what the workflow needs, nothing else.

## Sending

Sends go through the same Mailtrap path as `scripts/send_leads.py` and append to
`leads/send_log.txt`. Guards, in order:

- **Dry run** — runs the whole path and reports what would go out, sending nothing.
- A real send always asks for confirmation and names every recipient.
- Leads with no email address, or with an empty subject or body, are never sent and
  are reported as skipped.
- On success the row's Status and Date Contacted are updated; on failure the row is
  marked `Send Failed`.

The three dots at the bottom of the sidebar show whether `APIFY_API_KEY`,
`MAILTRAP_API_KEY` and `ANTHROPIC_API_KEY` were found in `.env`. The company name in the
sidebar, the From: name on every send, and the pre-filled location and categories on
Discover all come from `.env` too — see [CUSTOMIZING.md](../CUSTOMIZING.md).

## Layout

```
ui/server.py    HTTP server + JSON API; shells out to scripts/ for the real work
ui/store.py     CSV read/write, status vocabulary, stats, follow-up scheduling
ui/static/      index.html, app.js, styles.css — no build step, no dependencies
```
