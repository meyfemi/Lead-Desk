# Lead Desk

Lead Desk is a small dashboard that runs on your own computer. It helps you:

1. **Find businesses** in a city (for example, "restaurants and clinics in Lagos") using Google Maps.
2. **Collect their details**: website, email, phone, address and a short summary.
3. **Write a personal outreach email** for each one with Claude.
4. **Send the emails and follow-ups**, and keep track of who you've contacted.

All your leads are saved as plain CSV files in the `leads/` folder. You can open them
in Excel or Google Sheets at any time.

---

## How it works

```
Pick a city + business types
        │
        ▼
Apify searches Google Maps  ──►  Each website is scanned for contact details
        │
        ▼
Claude researches each business and writes an email
        │
        ▼
You review the emails in Lead Desk  ──►  Send through Mailtrap
```

It uses three outside services. You need an account and API key for each:

| Service | What it does | Needed for |
|---------|--------------|------------|
| [Apify](https://console.apify.com) | Searches Google Maps for businesses | Finding leads |
| [Anthropic Console](https://console.anthropic.com) | Claude writes the emails | Writing emails |
| [Mailtrap](https://mailtrap.io) | Sends the emails | Sending |

---

## Install

You need **Python 3.10 or newer**. Check with `python3 --version` (Mac) or
`python --version` (Windows).

**1. Install the Python packages.** In a terminal, inside the project folder:

```bash
python3 -m pip install -r requirements.txt     # Mac
python -m pip install -r requirements.txt      # Windows
```

**2. Create your settings file.** Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Open `.env` and fill in your details and keys:

```
COMPANY_NAME=Your Company
SENDER_NAME=Your first name
MAIL_FROM_ADDRESS=you@yourcompany.com     # must be verified in Mailtrap
DEFAULT_LOCATION=Lagos, Nigeria
DEFAULT_CATEGORIES=restaurant, clinic, law firm
APIFY_API_KEY=...
MAILTRAP_API_KEY=...
ANTHROPIC_API_KEY=...
```

**3. Start Lead Desk.**

```bash
./start-ui.sh            # Mac / Linux
python ui\server.py      # Windows
```

Your browser opens at **http://127.0.0.1:8765**. Keep the terminal open while you use it,
and press **Ctrl + C** to stop.

> Setting up a new laptop, or using Windows? Follow the step-by-step guide in
> [SETUP.md](../SETUP.md). It covers installing Python, a Windows-only UTF-8 setting you
> shouldn't skip, and fixes for common problems.

**Check it's working:** the three dots at the bottom of the sidebar (Apify, Mailtrap,
Claude) should all be green. A red dot means that key is missing from `.env`.

---

## Using Lead Desk

The sidebar has five pages:

| Page | What it's for |
|------|---------------|
| **Overview** | Totals at a glance: leads, emails sent, follow-ups due |
| **Leads** | Search and filter all your leads. Click a row to view or edit it |
| **Follow-ups** | Leads that are due a follow-up email today |
| **Discover** | Find new leads |
| **Activity** | Live progress of the current run, and a log of sent emails |

### Finding leads

On **Discover**, enter a location, how many leads you want, and the business types.
Then choose one of three options:

| Option | What happens | Keys needed |
|--------|--------------|-------------|
| **Find details only** | Collects contact details. No emails written. | Apify |
| **Research & draft only** *(default)* | Collects details and Claude writes each email. Nothing is sent. | Apify + Claude |
| **Research, draft and send** | Does everything, then sends the emails straight away. | All three |

A run usually takes 5–15 minutes. You can follow it on the **Activity** page and stop it
at any time with **Stop run**.

Good to know:

- Businesses without an email address are skipped.
- "Lead count" means the number of *usable* leads to save. If too many are filtered out,
  Lead Desk searches again (up to 4 times). Extra searches use more Apify credit.
- Claude skips businesses that don't fit, based on the rules in `target_businesses.md`.
- Each email is checked for length and tone. If it still fails after two rewrites, the
  lead is saved as **Draft - Needs Copy** so you can fix it by hand.

### Sending emails

Click a lead to open it. You can edit the subject and email, then:

- **Dry run** shows what would be sent, without sending anything. Use this to test.
- **Send** always asks you to confirm first and lists every recipient.

After sending, the lead's status and date are updated automatically. Follow-up emails
appear on the **Follow-ups** page when they're due.

---

## Make it your own

To use Lead Desk for a different business, edit these three files. No coding needed.

| File | What to put in it |
|------|-------------------|
| `.env` | Your company name, sender, default city and business types, API keys |
| `our_offer.md` | What your company offers. Claude uses this when writing emails |
| `target_businesses.md` | Who you want to reach, and who to avoid |

See [CUSTOMIZING.md](../CUSTOMIZING.md) for more detail.

To choose which Claude model writes the emails, set `CLAUDE_MODEL` in `.env`
(for example `claude-haiku-5-5` is the cheapest). Leave it blank to use `claude-opus-5-5`.

---

## Project files

```
leads/                 Your leads (one CSV per city) and send_log.txt
scripts/               The scripts that search, scrape, write and send
ui/server.py           The Lead Desk web server
ui/store.py            Reads and writes the lead CSV files
ui/static/             The dashboard's web page (HTML, CSS, JavaScript)
start-ui.sh            Starts Lead Desk on Mac / Linux
```

**For developers:** the email-writing rules live in two places:
`scripts/write_outreach.py` (used by Lead Desk) and `.claude/commands/find-leads.md`
(used by the `/find-leads` command in Claude Code). If you change one, change the other.

---

> **Keep `.env` private.** It holds your live API keys. Never share it or upload it to a
> public repository.
