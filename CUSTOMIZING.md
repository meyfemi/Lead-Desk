# Customizing for a new business

Nothing in the code is tied to one company. To set this up for a different business you
edit three files, all at the project root. No code changes.

| File | What it holds | Who reads it |
|------|---------------|--------------|
| `.env` | Company name, sender name, from-address, default location and categories, API keys | Every script, the dashboard, and `/find-leads` |
| `our_offer.md` | What the company does, its value propositions, tone | The dashboard's **Find leads** and `/find-leads`, when they write the benefit paragraph of each email |
| `target_businesses.md` | Who to target, what qualifies them, the signals to look for, red flags | The dashboard's **Find leads** and `/find-leads`, when they qualify companies and write their Sales Edges |

## 1. `.env`

```
cp .env.example .env
```

Fill in the identity block - this is what appears on every email:

```
COMPANY_NAME=Acme Web Studio
COMPANY_TAGLINE=Websites that bring in customers      # optional
SENDER_NAME=Ada
MAIL_FROM_ADDRESS=hello@acmeweb.example               # must be verified in Mailtrap
```

The From: name becomes `Ada | Acme Web Studio` and the sign-off becomes:

```
Ada
Acme Web Studio - Websites that bring in customers
hello@acmeweb.example
```

Then the defaults the dashboard and `/find-leads` pre-fill (both can be changed per run):

```
DEFAULT_LOCATION=Accra, Ghana
DEFAULT_CATEGORIES=dentist, law firm, real estate agency, private school
```

And the three keys:

| Key | Needed for |
|-----|-----------|
| `APIFY_API_KEY` | Finding businesses on Google Maps |
| `MAILTRAP_API_KEY` | Sending email |
| `ANTHROPIC_API_KEY` | Writing the outreach emails when you click **Find leads** in the dashboard. Each install bills its own Claude Console account. |

## 2. `our_offer.md`

Rewrite it for the company. Keep it factual - the workflow is told never to promise anything
this file does not say you provide. Useful sections: what you do, who it's for, 3–5 value
propositions (each one a reason a customer picks you), the tone you write in, and any real
proof points.

## 3. `target_businesses.md`

Rewrite every section but keep the headings. The one that matters most for email quality is
**Signals to Look For**: concrete things visible on a prospect's website or Google listing
that show they need you. The workflow is only allowed to write a sales edge when it can pair
a signal from this list with something it actually observed. For a web agency that might be
"no HTTPS", "no mobile layout", "copyright year two years old"; for an accountant, "no
pricing or services page", "a 'we're hiring' notice but no company registration shown".

## 4. Check

- Start the dashboard: `./start-ui.sh` (or `python ui\server.py` on Windows). The sidebar
  shows the company name, and all three key dots are green.
- The Discover tab pre-fills your default location and categories.
- Open any lead and click **Dry run** - the output shows the new From: name.
- On Discover, run **Research & draft only** for a small count (2–3) and read the drafts
  before sending anything.

The `leads/` folder is per-install and ignored by git, so a fresh copy starts empty.
