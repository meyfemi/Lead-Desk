# Find Leads & Send Outreach Emails

You are running the lead generation and email outreach workflow for the company described in
`our_offer.md`. Work through every step below in order. Do not skip steps.

Nothing in this file is specific to one business. Who we are comes from `.env` and
`our_offer.md`; who we target and what to look for comes from `target_businesses.md`.

---

## STEP 1 - Load context

Read these files from the project root:

1. `.env` - identity, defaults and credentials. Parse:
   - `COMPANY_NAME`, `COMPANY_TAGLINE` (may be blank), `SENDER_NAME`, `MAIL_FROM_ADDRESS`
   - `DEFAULT_LOCATION`, `DEFAULT_CATEGORIES` (comma-separated; may be blank)
   - `APIFY_API_KEY`, `MAILTRAP_API_KEY`
2. `our_offer.md` - who we are, what we offer, and our value propositions
3. `target_businesses.md` - who we target, what qualifies them, and the signals to look for

**If `.env` is missing or `COMPANY_NAME` / `SENDER_NAME` / `MAIL_FROM_ADDRESS` are blank:**
Stop and tell the user to copy `.env.example` to `.env` and fill in the identity section.

**If `our_offer.md` is missing:**
Ask the user: "Please describe your company name, what services you offer, and the main
reasons a customer chooses you." Then create `our_offer.md` with their answer before continuing.

**If `target_businesses.md` is missing:**
Ask the user: "Please describe the types of businesses you are targeting, what makes one a
qualified lead, and what you'd look for on their website or Google listing that shows they
need your offer." Then create `target_businesses.md` with these headings - Primary Niche,
Qualifying Criteria, Decision Maker, Signals to Look For, Sales Edges, Red Flags - filled
from their answer, before continuing.

Derive and remember these values for the rest of the workflow:

- `SENDER_LINE` = `SENDER_NAME | COMPANY_NAME` (for example "Femi | Krediview")
- `SIGN_OFF` =
  ```
  SENDER_NAME
  COMPANY_NAME - COMPANY_TAGLINE
  MAIL_FROM_ADDRESS
  ```
  If `COMPANY_TAGLINE` is blank, the middle line is just `COMPANY_NAME`.

---

## STEP 2 - Ask the three required questions

Use the `AskUserQuestion` tool with all THREE questions in a single call:

- **Question 1 - "Location":** "In which city and country do you want to find leads?"
  Offer `DEFAULT_LOCATION` from `.env` as the first option if it is set.
- **Question 2 - "Lead Count":** "How many leads do you want to find and contact?"
  Offer 10, 20 and 50 as options.
- **Question 3 - "Categories":** "Which business categories should we search for in that
  location? (comma-separated, e.g. dentist, gym, car wash)"
  Offer "Use the defaults from .env" as the first option, showing the `DEFAULT_CATEGORIES`
  list in its description.

Wait for the answers before continuing. Then set:

- `LOCATION` = the city + country given
- `LEAD_COUNT` = the number requested
- `CATEGORIES` = the categories given, or `DEFAULT_CATEGORIES` when they chose the defaults
  or left it blank. If both are blank, use: restaurant, hotel, clinic, pharmacy, law firm,
  accounting firm, consulting firm, training academy, spa, retail boutique.

If the values were supplied in the prompt that launched you (the dashboard does this), use
them and do not ask.

---

## STEP 3 - Prepare the leads file

Sanitize LOCATION to a safe filename: lowercase, spaces → underscores, commas removed.
Example: "Accra, Ghana" → `accra_ghana`

**Leads file path:** `leads/accra_ghana_leads.csv` (adjust for actual location)

**CSV columns (in this exact order):**
```
Company Name,Company URL,Company Address,Company Email,Company Phone,Company CEO,Company Summary,Specific Sales Edges,Email Subject,First Mail Body,Followup 1 Date,Followup 1 Body,Followup 2 Date,Followup 2 Body,Status,Date Contacted
```

- If the file does not exist, create it with the header row only.
- If the file exists, read it now and build a set of company names already in it - you will use this to avoid duplicates.

---

## STEP 4 - Search for leads via Apify

Inform the user: "Starting Apify Google Maps search for [CATEGORIES] in [LOCATION]. This typically takes 5–15 minutes..."

Run:
```bash
python3 scripts/apify_search.py --location "[LOCATION]" --count [LEAD_COUNT] --categories "[CATEGORIES joined with commas]" --output /tmp/apify_results.json
```

After the script finishes, read `/tmp/apify_results.json`.

**Filter the results:**
- Remove any company whose name already exists in the leads CSV (duplicate check)
- Remove entries with no website AND no address
- Stop collecting once you have enough candidates to fill LEAD_COUNT (gather up to 2× LEAD_COUNT as buffer for later filtering)

If the script returns fewer results than needed, run it again with district-level locations
inside the same city (for example "[District], [City]") and merge the results.

---

## STEP 5 - Process each lead (repeat for every qualifying company)

Work through each company one at a time. Complete **all sub-steps** before moving to the next company.

### 5a. Scrape the company website

```bash
python3 scripts/scrape_website.py "[company_website_url]"
```

Parse the JSON output. Combine it with the Apify data to fill in the lead record.

If the scraper's `emails` list comes back empty, re-run it directly against the contact page before giving up:

```bash
python3 scripts/scrape_website.py "[company_website_url]/contact"
```

(Also try `/contact-us` and `/about-us` if needed.) The contact page is where the company's general enquiry address is usually published.

### 5b. Populate the lead record

| Column | Source |
|--------|--------|
| Company Name | Apify `title` |
| Company URL | Apify `website` |
| Company Address | Apify `address`, prefixed with LOCATION's parts from broadest to narrowest. For LOCATION "Accra, Ghana" write "Ghana; Accra; [street]" |
| Company Email | Use the company's general contact email - the one published on their website's contact/about page (e.g. `info@`, `contact@`, `hello@`, `enquiries@`, `sales@`, `admin@`). Take it from the scraper's `emails` list, preferring a mailbox on the company's own domain. Fall back to Apify `email`. Do NOT use a CEO/personal email even if you find one. Write "Not found" if none |
| Company Phone | Prefer a direct number from scraper; fall back to Apify `phone`; write "Not found" if none |
| Company CEO | From scraper `ceo_names[0]` if found; otherwise "Not identified". This is context only - it is never used as the send address |
| Company Summary | Write 2–3 sentences: what they do, who their customers are, and their approximate size/reach. Base this on their website text and Apify data. |
| Specific Sales Edges | See Step 5c |
| Email Subject | See Step 5d |
| First Mail Body | See Step 5d |
| Followup 1 Date | 5 business days from today |
| Followup 2 Date | 10 business days from today |
| Status | "Ready to Send" |
| Date Contacted | (leave blank - filled on send) |

Before writing the record, check the company against the **Red Flags** in `target_businesses.md`.
If one applies, skip the company and move on; do not add it to the CSV.

### 5c. Write Specific Sales Edges

Identify 2–3 concrete, company-specific reasons this business would benefit from our offer.
Each one MUST pair something you actually observed (on their website, their Google listing
or the Apify data) with one of the **Signals to Look For** in `target_businesses.md`.
Generic statements are not acceptable.

An acceptable edge has the shape: *[specific observed fact] → [why it matters, in terms of
one of our signals]*. For example: "Their site lists three branches, yet their Google listing
has four reviews in total" or "Their homepage claims '500+ clients' with nothing a visitor
could verify". Use the examples in `target_businesses.md` as the standard, not these.

Do NOT write edges like "They could benefit from our service" or "They are a growing
business" - if you cannot point to a specific observed fact, you do not have an edge.

### 5d. Write the outreach email

**Subject line rules:**
- 5–8 words maximum
- Reference their business name or a specific detail you found
- No clickbait, no ALL CAPS, no question marks as a hook
- Examples: "[Business Name] - one thing worth 5 minutes" / "Noticed something on your [page/listing]"

**Email body rules:**
- These emails land in a shared company inbox, so write to the team, not to an individual: open with "Hi [Company Name] team" or just "Hi" (NEVER "Dear Sir/Ma", "Dear Business Owner", "To Whom It May Concern"). If a CEO name is known you may mention them in the body ("...worth passing to [First name]"), but do not use their name as the greeting.
- Total length: 100–150 words, no more
- **Paragraph 1 (1–2 sentences):** Prove you looked at their business. Reference one specific thing you found on their website or Google listing.
- **Paragraph 2 (1–2 sentences):** Name the exact problem clearly, using the Sales Edge most relevant to them. No hedging.
- **Paragraph 3 (1–2 sentences):** State the specific benefit from `our_offer.md` that answers that problem. Pick the single most relevant value proposition; do not list several.
- **Paragraph 4 (1 sentence):** Soft call to action - ask a question or offer something low-friction. Do NOT say "click here", "book a call", or "sign up now".
- **Sign-off:** exactly `SIGN_OFF` from Step 1.

**Tone:** Match the style described in `our_offer.md` if it gives one; otherwise direct,
human, informed. Write as if you researched this one company personally. It should not feel
like it could have been sent to 100 businesses.

### 5e. Quality check (MANDATORY - do not skip)

Before this lead is marked "Ready to Send", verify every item on this checklist. If any item fails, rewrite the relevant part and recheck.

- [ ] The greeting is addressed to the company/team, not to an individual, and the recipient email is a company contact address (not a personal/CEO mailbox)
- [ ] Paragraph 1 contains a specific, verifiable detail from THIS company's website/data (not a generic statement)
- [ ] The problem statement is true for this specific company (not assumed) and maps to a signal in `target_businesses.md`
- [ ] The benefit mentioned is the most relevant one from `our_offer.md` for this company's situation, and nothing in the email promises something `our_offer.md` does not say we provide
- [ ] The email is 100–150 words (count them)
- [ ] There are no phrases like "I hope this email finds you well", "I came across your business", "as per", "leverage", "utilize", "synergy", "exciting opportunity"
- [ ] Reading it aloud, it sounds like a real person who researched this business, not a template
- [ ] The company name is spelled the same way throughout subject and body
- [ ] The sign-off is exactly `SIGN_OFF`

**If any check fails:** rewrite the failing part, then run through the full checklist again before proceeding.

### 5f. Append to leads CSV

Append the completed lead record as a new row in the CSV. Quote all fields that contain commas or newlines. Write the email body with `\n` for line breaks inside the CSV cell.

Announce progress: "✓ Lead [N/LEAD_COUNT]: [Company Name] - processed and queued"

---

## STEP 6 - Send outreach emails

After all LEAD_COUNT leads are processed, send the emails in this priority order:

1. Leads with the most company-specific Sales Edges (ranked by specificity)
2. Leads whose contact email is on the company's own domain (rather than a free/generic provider)
3. Remaining leads alphabetically

For each lead with Status = "Ready to Send":

```bash
python3 scripts/send_email.py \
  --to-email "[Company Email]" \
  --to-name "[Company Name]" \
  --subject "[Email Subject]" \
  --body "[First Mail Body]"
```

(The sender name and address come from `.env`; you do not pass them.)

**On success:**
- Update that row's Status → "Sent"
- Update Date Contacted → today's date (YYYY-MM-DD)
- Announce: "✓ Email sent to [Company Name] ([Company Email])"

**On failure:**
- Update Status → "Send Failed"
- Note the error
- Continue to next lead; report all failures in the final summary

---

## STEP 7 - Handle follow-ups for previously contacted leads

After sending new emails, scan the entire leads CSV for follow-up duties:

**First follow-up check:**
Find rows where:
- Status = "Sent"
- Followup 1 Date ≤ today's date

For each matching row, write a follow-up email:
- 2–3 sentences only
- Open by referencing the original email naturally ("Just checking back on the note I sent [N] days ago about...")
- One new, fresh angle or detail - do not repeat the original pitch word-for-word
- Same soft CTA
- Same sign-off (`SIGN_OFF`)

Quality-check this follow-up the same way as the original (Step 5e checklist applies).

Save the composed follow-up body to the row's **Followup 1 Body** column in the CSV, then send it and update Status → "Followed Up 1".

**Second follow-up check:**
Find rows where:
- Status = "Followed Up 1"
- Followup 2 Date ≤ today's date

Write a final follow-up - a different angle from the first two. If `target_businesses.md`
or `our_offer.md` contains a **Proof Point** (a real result or number), you may include one
sentence of it; never invent a statistic or a customer. Keep it 2–3 sentences. This is the
last touch - make it count but keep it respectful.

Save the composed follow-up body to the row's **Followup 2 Body** column in the CSV, then send it and update Status → "Followed Up 2 (Final)".

---

## STEP 8 - Final summary

Output a clean summary at the end:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LEAD GENERATION & OUTREACH COMPLETE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Location:          [LOCATION]
Categories:        [CATEGORIES]
New leads found:   [N]
Emails sent:       [N]
Follow-ups sent:   [N]
Send failures:     [N] (list company names if any)

Next follow-up batch due: [earliest Followup 1 Date in file]
Leads database:    leads/[filename]_leads.csv
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Error handling

| Situation | Action |
|-----------|--------|
| Apify returns < LEAD_COUNT results | Re-run with district-level locations inside the city; merge results |
| Website cannot be scraped | Use only Apify data; note "Website inaccessible" in Company Summary |
| No email found for a company | Still add to CSV with "Not found"; Status = "No Email - Skip Send" |
| Email send fails | Mark "Send Failed"; include in final summary; do not retry automatically |
| Company already in CSV | Skip silently; do not add duplicate |
| Apify run fails | Report the error and the run ID; ask user whether to retry |
| `.env` identity values missing | Stop; tell the user which keys to fill in `.env` |
