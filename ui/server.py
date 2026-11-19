#!/usr/bin/env python3
"""
Lead Desk - a local dashboard for the lead pipeline. Branding, sender identity
and default search settings come from .env (see .env.example).

Stdlib only, to match the rest of the project. Serves a single-page UI plus a
small JSON API over the lead CSVs, and shells out to the existing scripts in
scripts/ for the work they already do (Apify search, website scrape, send).

    python3 ui/server.py [--port 8765] [--no-browser]
"""
import argparse
import importlib.util
import json
import mimetypes
import os
import shlex
import signal
import subprocess
import sys
import tempfile
import threading
import traceback
import uuid
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import store  # noqa: E402
from config import identity, parse_categories  # noqa: E402
from send_email import send_email as mailtrap_send  # noqa: E402
from write_outreach import OutreachError, Writer, business_days_from  # noqa: E402

ROOT = Path(__file__).parent.parent
STATIC = Path(__file__).parent / "static"
SCRIPTS = ROOT / "scripts"

# Background jobs (find details, find leads, website enrichment, batch sends). id -> record.
JOBS = {}
JOBS_LOCK = threading.Lock()
# Live subprocesses for cancellable jobs. job id -> Popen.
PROCS = {}


def new_job(kind, title):
    job_id = uuid.uuid4().hex[:12]
    with JOBS_LOCK:
        JOBS[job_id] = {
            "id": job_id, "kind": kind, "title": title, "state": "running",
            "log": [], "result": None, "error": None,
            "started": date.today().isoformat(),
        }
    return job_id


def job_log(job_id, line):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job:
            job["log"].append(line)


def job_done(job_id, result=None, error=None):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job:
            job["state"] = "error" if error else "done"
            job["result"] = result
            job["error"] = error
        PROCS.pop(job_id, None)


def job_stopped(job_id):
    with JOBS_LOCK:
        return bool(JOBS.get(job_id, {}).get("stopped"))


def job_stop(job_id):
    """Cancel a long job (a find-leads or find-details run). Flags the job so its loop
    exits at the next check, and interrupts whatever subprocess it is running now."""
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job or job["state"] != "running":
            return False
        job["stopped"] = True
    proc = PROCS.get(job_id)
    if proc:
        try:
            # Windows has no SIGINT for child processes; terminate() is its equivalent.
            proc.terminate() if os.name == "nt" else proc.send_signal(signal.SIGINT)
        except Exception:
            pass
    job_log(job_id, "- stopped by user -")
    return True


def run_in_thread(fn, *args):
    threading.Thread(target=fn, args=args, daemon=True).start()


# ── Work performed on behalf of the UI ──────────────────────────────────────
#
# Find details only (no Claude) (no Claude) ───────────────────────────────────────────
#
# Steps 3-5b of /find-leads done in plain Python: Apify search, website scrape,
# contact details and a short factual summary. Nothing from 5c onwards - no sales
# edges, no email copy, no follow-ups - so the rows land as "Draft - Needs Copy".

GENERIC_MAILBOXES = {
    "info", "contact", "contactus", "hello", "hi", "enquiries", "enquiry", "inquiries",
    "inquiry", "sales", "admin", "office", "support", "help", "mail", "team", "welcome",
    "reservations", "reservation", "bookings", "booking", "customercare", "care", "general",
}
FREE_MAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "yahoo.co.uk", "ymail.com", "hotmail.com", "hotmail.co.uk",
    "outlook.com", "live.com", "icloud.com", "aol.com", "protonmail.com", "proton.me",
}
# The scraper's regex also matches things like "image@2x.png" - never an address.
NOT_EMAIL_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js")


def site_domain(url):
    host = urlparse(url if "://" in url else f"https://{url}").netloc.lower()
    return host[4:] if host.startswith("www.") else host


def pick_email(scraped_emails, apify_email, website):
    """The company's general contact address, chosen the way Step 5b of /find-leads
    does: a generic mailbox on their own domain, then anything on their domain, then
    the Google listing's email, then a mailbox on a free-mail provider (small firms
    often publish only a Gmail address). Addresses on some third domain are skipped -
    those are usually the web designer's or a partner's."""
    emails, seen = [], set()
    for raw in scraped_emails or []:
        email = (raw or "").strip().strip(".,;:<>()")
        low = email.lower()
        if "@" not in email or low in seen or low.endswith(NOT_EMAIL_SUFFIXES):
            continue
        seen.add(low)
        emails.append(email)

    domain = site_domain(website) if website else ""
    mailbox = lambda e: e.split("@")[0].lower().split("+")[0]  # noqa: E731
    mail_domain = lambda e: e.split("@")[-1].lower()  # noqa: E731
    own = [e for e in emails if domain and (mail_domain(e) == domain or mail_domain(e).endswith("." + domain))]
    listing = (apify_email or "").strip()

    for pool in (
        [e for e in own if mailbox(e) in GENERIC_MAILBOXES],
        own,
        [listing] if listing and "@" in listing else [],
        [e for e in emails if mail_domain(e) in FREE_MAIL_DOMAINS],
    ):
        if pool:
            return pool[0]
    return "Not found"


def build_summary(item, scraped, location):
    """A short factual summary from the data in hand. No LLM is involved, so it states
    what the Google listing and the site's own description say rather than interpreting."""
    category = (item.get("category") or "").strip() or "Business"
    bits = [f"{category} in {location}, from its Google Maps listing."]

    rating, reviews = item.get("google_rating"), item.get("google_review_count")
    if rating or reviews:
        reviews = reviews or 0
        bits.append(f"Google rating {rating if rating else 'n/a'} from {reviews} review{'' if reviews == 1 else 's'}.")

    if scraped is None:
        bits.append("No website listed.")
    elif scraped.get("error"):
        bits.append("Website inaccessible.")
    else:
        about = " ".join((scraped.get("description") or scraped.get("title") or "").split())
        if len(about) > 300:
            about = about[:297].rsplit(" ", 1)[0] + "..."
        if about:
            bits.append(f"Website says: {about}")
    return " ".join(bits)


def details_row(item, scraped, location):
    """Map one Apify record plus its scrape onto the lead columns Step 5b fills.
    `scraped` is None when the listing has no website."""
    website = (item.get("website") or "").strip()
    scraped = scraped or {}
    address = (item.get("address") or "").strip()
    if address:
        # Broadest to narrowest, as the workflow writes it: "Nigeria; Ibadan; <street>".
        parts = [p.strip() for p in location.split(",") if p.strip()][::-1]
        address = "; ".join(parts + [address])

    email = pick_email(scraped.get("emails"), item.get("email"), website)
    phone = ((scraped.get("phones") or [""])[0] or (item.get("phone") or "")).strip() or "Not found"
    ceo = ((scraped.get("ceo_names") or [""])[0] or "").strip() or "Not identified"
    return {
        "Company Name": (item.get("name") or "").strip(),
        "Company URL": website,
        "Company Address": address,
        "Company Email": email,
        "Company Phone": phone,
        "Company CEO": ceo,
        "Company Summary": build_summary(item, scraped if website else None, location),
        "Status": store.STATUS_DRAFT if store.has_email({"Company Email": email}) else store.STATUS_NO_EMAIL,
    }


def scrape_site(url, timeout=90):
    """Run scripts/scrape_website.py and return its JSON; errors come back as {'error': ...}."""
    try:
        proc = subprocess.run([sys.executable, str(SCRIPTS / "scrape_website.py"), url],
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"error": f"timed out after {timeout}s"}
    if not proc.stdout.strip():
        return {"error": (proc.stderr or "scraper produced no output").strip().splitlines()[-1][:200]}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"error": "scraper returned invalid JSON"}


def scrape_for_details(job_id, url):
    """Homepage first; if no email turned up, the contact pages Step 5a says to try next."""
    data = scrape_site(url)
    if data.get("error") or data.get("emails"):
        return data
    base = url.rstrip("/")
    for path in ("/contact", "/contact-us", "/about-us"):
        if job_stopped(job_id):
            break
        extra = scrape_site(base + path, timeout=60)
        if extra.get("error"):
            continue
        for key in ("emails", "phones", "ceo_names"):
            merged = list(dict.fromkeys((data.get(key) or []) + (extra.get(key) or [])))
            data[key] = merged
        if extra.get("emails"):
            break
    return data


def run_apify(job_id, location, count, categories):
    """Run scripts/apify_search.py, streaming its progress into the job log."""
    fd, tmp = tempfile.mkstemp(prefix="leaddesk_apify_", suffix=".json")
    os.close(fd)
    args = ["--location", location, "--count", str(count)]
    if categories:
        args += ["--categories", categories]
    cmd = [sys.executable, str(SCRIPTS / "apify_search.py")] + args + ["--output", tmp]
    job_log(job_id, "$ " + shlex.join(["apify_search.py"] + args))
    try:
        proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, bufsize=1)
        PROCS[job_id] = proc
        for line in proc.stdout:
            line = line.rstrip()
            # Once cancelled, the script's interrupt traceback is just noise.
            if line and not job_stopped(job_id):
                job_log(job_id, line)
        proc.wait()
        PROCS.pop(job_id, None)
        if job_stopped(job_id):
            return []
        if proc.returncode != 0:
            raise RuntimeError(f"apify_search.py exited {proc.returncode}")
        return json.loads(Path(tmp).read_text(encoding="utf-8") or "[]")
    finally:
        Path(tmp).unlink(missing_ok=True)


# Searching in rounds: the first asks Apify for 4x the lead count. If filtering leaves the
# run short, the next round asks for twice as many places. Apify returns its best matches
# first, so places already seen are dropped and only the new ones are processed. The run
# stops when it has enough valid leads, Apify has nothing new, or the limits below are hit.
SEARCH_FIRST_ROUND = 4      # x lead count
SEARCH_MAX_ROUNDS = 4
SEARCH_MAX_PLACES = 400     # cap on what one round asks Apify for


def iter_candidates(job_id, location, count, categories, target, have, stats):
    """Step 4: yield Apify businesses not already in the leads file, searching again with a
    bigger request whenever the caller still has fewer than `count` valid leads.
    `have()` returns the caller's valid-lead count; stats["duplicates"] is kept up to date."""
    seen = {r["Company Name"].strip().lower() for r in store.read(target)}
    ask = min(SEARCH_MAX_PLACES, count * SEARCH_FIRST_ROUND)
    for rnd in range(1, SEARCH_MAX_ROUNDS + 1):
        if rnd > 1:
            job_log(job_id, f"· round {rnd}: {have()} of {count} valid lead(s) so far - "
                            f"searching again for {ask} places")
        items = run_apify(job_id, location, ask, categories)
        if job_stopped(job_id):
            return
        fresh = []
        for item in items:
            name = (item.get("name") or "").strip()
            if not name or name.lower() in seen:
                if name and rnd == 1:
                    stats["duplicates"] += 1
                continue
            seen.add(name.lower())
            fresh.append(item)
        job_log(job_id, f"· {len(fresh)} new business(es) from Apify"
                        + (f", {stats['duplicates']} already in {target}" if rnd == 1 else ""))
        for item in fresh:
            if job_stopped(job_id) or have() >= count:
                return
            yield item
        if have() >= count:
            return
        if not fresh or ask >= SEARCH_MAX_PLACES:
            job_log(job_id, f"· Apify returned no more new businesses for this search "
                            f"in {location} - try other categories or a district")
            return
        ask = min(SEARCH_MAX_PLACES, ask * 2)
    job_log(job_id, f"· stopped searching after {SEARCH_MAX_ROUNDS} rounds")


def gather_details(job_id, item, location, n):
    """Steps 5a-5b for one Apify record: scrape its site and map it onto the lead columns.
    Returns (row, scraped) - scraped is None when the listing has no website."""
    name, website = item["name"].strip(), (item.get("website") or "").strip()
    scraped = None
    if website:
        job_log(job_id, f"→ {n} {name}: scraping {website}")
        scraped = scrape_for_details(job_id, website)
        if scraped.get("error"):
            job_log(job_id, f"✗ {name}: {scraped['error']} - using the Google listing only")
    else:
        job_log(job_id, f"– {n} {name}: no website listed - using the Google listing only")
    return details_row(item, scraped, location), scraped


def do_find_details(job_id, location, count, categories=""):
    """Find lead details only: search, scrape, file - no outreach copy, nothing sent."""
    if not store.load_env().get("APIFY_API_KEY", "").strip():
        job_done(job_id, error="APIFY_API_KEY is not set in .env - add it to find leads.")
        return

    target = store.lead_file_for(location)
    job_log(job_id, f"· find details only - {count} leads in {location}, no copy, nothing sent")
    job_log(job_id, f"· categories: {categories or 'defaults from .env'}")
    job_log(job_id, f"· leads file: leads/{target}")

    added, no_email = [], 0
    stats = {"duplicates": 0}
    try:
        for item in iter_candidates(job_id, location, count, categories, target,
                                    lambda: len(added), stats):
            name, n = item["name"].strip(), f"[{len(added) + 1}/{count}]"
            row, _ = gather_details(job_id, item, location, n)
            # Only leads with an email are worth filing - skip the rest and keep looking.
            if not store.has_email(row):
                no_email += 1
                job_log(job_id, f"– {name}: no email found - skipped")
                continue
            if not store.append(target, [row]):
                stats["duplicates"] += 1
                continue
            added.append(row["Company Name"])
            job_log(job_id, f"✓ {n} {name} - {row['Company Email']}, {row['Company Phone']}, "
                            f"contact: {row['Company CEO']}")

        stopped = job_stopped(job_id)
        if not stopped and len(added) < count:
            job_log(job_id, f"· only {len(added)} of {count} business(es) had an email - try other "
                            f"categories or a district inside {location} for more")
        job_log(job_id, f"Summary: {len(added)} lead(s) with an email saved to {target}, "
                        f"{no_email} skipped for having no email, {stats['duplicates']} duplicate(s) skipped"
                        + (" - stopped early" if stopped else ""))
        job_done(job_id, result={
            "file": target, "location": location, "added": len(added),
            "skipped_no_email": no_email, "duplicates": stats["duplicates"], "stopped": stopped,
        })
    except Exception as exc:
        job_log(job_id, f"✗ {exc}")
        job_done(job_id, error=str(exc))


# ── Find leads (Claude API) ─────────────────────────────────────────────────
#
# The /find-leads workflow without the Claude Code CLI: the same search and scrape as
# Find details, then one Claude API call per lead (scripts/write_outreach.py) to qualify
# it and write the summary, sales edges and first email. In "full" mode it then sends the
# new emails and any follow-ups that are due (Steps 6-7).

def lead_facts(item, scraped, row, location):
    """What Claude is told about one company - only data we actually collected."""
    scraped = scraped or {}
    facts = {
        "Company Name": row["Company Name"],
        "Search location": location,
        "Google Maps category": item.get("category") or "",
        "Google rating": item.get("google_rating"),
        "Google review count": item.get("google_review_count") or 0,
        "Address": item.get("address") or "",
        "Website": row["Company URL"] or "none listed",
        "Contact name found on site": "" if row["Company CEO"] == "Not identified" else row["Company CEO"],
    }
    if not row["Company URL"]:
        facts["Website status"] = "no website listed"
    elif scraped.get("error"):
        facts["Website status"] = "inaccessible"
    else:
        facts["Website title"] = scraped.get("title") or ""
        facts["Website meta description"] = scraped.get("description") or ""
        facts["Website text (excerpt)"] = scraped.get("page_text_excerpt") or ""
    return facts


def send_priority(row):
    """Step 6 order: most sales edges, then an address on the company's own domain, then A-Z."""
    edges = [e for e in (row.get("Specific Sales Edges") or "").split(";") if e.strip()]
    email, url = row.get("Company Email", ""), row.get("Company URL", "")
    own = bool(url) and site_domain(url) and email.lower().endswith(site_domain(url))
    return (-len(edges), not own, row.get("Company Name", "").lower())


def send_new_leads(job_id, target, names):
    """Step 6: send the first email to the leads this run wrote."""
    rows = [r for r in store.read(target) if r["Company Name"] in names
            and r["Status"] == store.STATUS_READY]
    sent = failed = 0
    log_lines = []
    for row in sorted(rows, key=send_priority):
        if job_stopped(job_id):
            break
        outcome = send_one(target, row["id"], 0, False)
        mark = "✓ SENT  " if outcome["ok"] else "✗ FAILED"
        line = f"{mark} {outcome['name']} <{outcome.get('email', '-')}> - {outcome['detail']}"
        job_log(job_id, line)
        log_lines.append(line)
        sent, failed = sent + outcome["ok"], failed + (not outcome["ok"])
    return sent, failed, log_lines


def send_due_followups(job_id, target, writer):
    """Step 7: write and send every follow-up that is due in this leads file."""
    sent = failed = 0
    log_lines = []
    for due in store.followups_due(store.read(target)):
        if job_stopped(job_id):
            break
        stage, name = due["followup_stage"], due["Company Name"]
        try:
            contacted = date.fromisoformat(due.get("Date Contacted") or "")
            days = (date.today() - contacted).days
        except ValueError:
            days = 5 if stage == 1 else 10
        try:
            body = writer.write_followup(due, stage, days)
        except OutreachError as exc:
            if exc.fatal:
                raise
            job_log(job_id, f"✗ {name}: follow-up {stage} not written - {exc}")
            failed += 1
            continue
        store.update(target, due["id"], {f"Followup {stage} Body": body})
        outcome = send_one(target, due["id"], stage, False)
        mark = "✓ SENT  " if outcome["ok"] else "✗ FAILED"
        line = f"{mark} follow-up {stage}: {name} <{outcome.get('email', '-')}> - {outcome['detail']}"
        job_log(job_id, line)
        log_lines.append(line)
        sent, failed = sent + outcome["ok"], failed + (not outcome["ok"])
    return sent, failed, log_lines


def do_find_leads(job_id, location, count, mode, categories=""):
    """Find leads, research them and write their outreach (and send, in "full" mode)."""
    env = store.load_env()
    if not env.get("APIFY_API_KEY", "").strip():
        job_done(job_id, error="APIFY_API_KEY is not set in .env - add it to find leads.")
        return
    try:
        writer = Writer(env)
    except OutreachError as exc:
        job_done(job_id, error=str(exc))
        return

    target = store.lead_file_for(location)
    job_log(job_id, f"· find leads - {count} leads in {location}, copy written by {writer.model}")
    job_log(job_id, f"· categories: {categories or 'defaults from .env'}")
    job_log(job_id, f"· leads file: leads/{target}")
    job_log(job_id, "· research only - no emails will be sent" if mode == "research"
            else "· full run - this WILL send outreach emails")

    added, review, no_email, skipped = [], [], 0, 0
    sends = {"sent": 0, "failed": 0, "fu_sent": 0, "fu_failed": 0}
    stats = {"duplicates": 0}
    try:
        start = date.today()
        fu1 = business_days_from(start, 5).isoformat()
        fu2 = business_days_from(start, 10).isoformat()

        for item in iter_candidates(job_id, location, count, categories, target,
                                    lambda: len(added), stats):
            name, n = item["name"].strip(), f"[{len(added) + 1}/{count}]"
            row, scraped = gather_details(job_id, item, location, n)
            if not store.has_email(row):
                no_email += 1
                job_log(job_id, f"– {name}: no email found - skipped")
                continue
            if job_stopped(job_id):
                break

            job_log(job_id, f"✎ {name}: writing outreach")
            try:
                copy = writer.write_lead(lead_facts(item, scraped, row, location))
            except OutreachError as exc:
                if exc.fatal:
                    raise
                skipped += 1
                job_log(job_id, f"✗ {name}: {exc} - skipped")
                continue
            if not copy["qualified"]:
                skipped += 1
                job_log(job_id, f"– {name}: not a fit ({copy['skip_reason']}) - skipped")
                continue

            row.update({
                "Company Summary": copy["summary"],
                "Specific Sales Edges": "; ".join(copy["sales_edges"]),
                "Email Subject": copy["subject"],
                "First Mail Body": copy["body"],
                "Followup 1 Date": fu1,
                "Followup 2 Date": fu2,
                # Copy that still fails a check after the rewrites waits for a person.
                "Status": store.STATUS_DRAFT if copy["issues"] else store.STATUS_READY,
            })
            if not store.append(target, [row]):
                stats["duplicates"] += 1
                continue
            added.append(name)
            if copy["issues"]:
                review.append(name)
                job_log(job_id, f"! {n} {name}: saved for review - " + " ".join(copy["issues"]))
            else:
                job_log(job_id, f"✓ {n} {name} - {row['Company Email']}: \"{copy['subject']}\"")

        stopped = job_stopped(job_id)
        if not stopped and len(added) < count:
            job_log(job_id, f"· only {len(added)} of {count} lead(s) written - try other "
                            f"categories or a district inside {location} for more")

        if mode == "full" and not stopped:
            log_lines = []
            job_log(job_id, "· sending first emails")
            s, f, lines = send_new_leads(job_id, target, set(added) - set(review))
            sends["sent"], sends["failed"] = s, f
            log_lines += lines
            if not job_stopped(job_id):
                job_log(job_id, "· checking for follow-ups due")
                s, f, lines = send_due_followups(job_id, target, writer)
                sends["fu_sent"], sends["fu_failed"] = s, f
                log_lines += lines
            if log_lines:
                store.append_log(log_lines)
            stopped = job_stopped(job_id)

        job_log(job_id, f"Summary: {len(added)} lead(s) written to {target}"
                        + (f" ({len(review)} need review)" if review else "")
                        + f", {skipped} not a fit or failed, {no_email} with no email, "
                        f"{stats['duplicates']} duplicate(s)"
                        + (f"; {sends['sent']} email(s) sent, {sends['failed']} failed, "
                           f"{sends['fu_sent']} follow-up(s) sent" if mode == "full" else "")
                        + (" - stopped early" if stopped else ""))
        job_log(job_id, "· " + writer.cost_line())
        job_done(job_id, result={
            "file": target, "location": location, "mode": mode, "added": len(added),
            "needs_review": len(review), "stopped": stopped, **sends,
        })
    except Exception as exc:
        job_log(job_id, f"✗ {exc}")
        job_log(job_id, "· " + writer.cost_line())
        job_done(job_id, error=str(exc))


def do_enrich(job_id, filename, lead_ids):
    """Run scripts/scrape_website.py over leads to fill in email / CEO / phone."""
    rows = store.read(filename)
    updated = []
    for lead_id in lead_ids:
        if lead_id >= len(rows):
            continue
        row = rows[lead_id]
        url = (row.get("Company URL") or "").strip()
        name = row.get("Company Name", "")
        if not url:
            job_log(job_id, f"– {name}: no website on file")
            continue
        job_log(job_id, f"→ {name}: scraping {url}")
        try:
            proc = subprocess.run(
                [sys.executable, str(SCRIPTS / "scrape_website.py"), url],
                capture_output=True, text=True, timeout=90)
            data = json.loads(proc.stdout or "{}")
        except Exception as exc:
            job_log(job_id, f"✗ {name}: {exc}")
            continue

        if data.get("error"):
            job_log(job_id, f"✗ {name}: {data['error']}")
            continue

        patch = {}
        if not store.has_email(row) and data.get("emails"):
            patch["Company Email"] = data["emails"][0]
        if row.get("Company CEO", "") in ("", "Not identified") and data.get("ceo_names"):
            patch["Company CEO"] = data["ceo_names"][0]
        if row.get("Company Phone", "") in ("", "Not found") and data.get("phones"):
            patch["Company Phone"] = data["phones"][0]
        if patch.get("Company Email") and row.get("Status") == store.STATUS_NO_EMAIL:
            patch["Status"] = store.STATUS_DRAFT

        if patch:
            store.update(filename, lead_id, patch)
            updated.append({"id": lead_id, "name": name, "patch": patch})
            job_log(job_id, f"✓ {name}: " + ", ".join(f"{k} → {v}" for k, v in patch.items()))
        else:
            job_log(job_id, f"· {name}: nothing new found")

    job_done(job_id, result={"updated": updated})


def send_one(filename, lead_id, stage, dry_run):
    """Send a lead's first mail (stage 0) or a follow-up (stage 1/2)."""
    env = store.load_env()
    api_key = env.get("MAILTRAP_API_KEY")
    who = identity(env)
    from_email, from_name = who["from_email"], who["from_name"]

    rows = store.read(filename)
    row = rows[lead_id]
    name = row["Company Name"]
    email = (row.get("Company Email") or "").strip()

    if not store.has_email(row):
        return {"ok": False, "name": name, "detail": "no email address on file"}

    if stage == 0:
        subject = row.get("Email Subject", "")
        body = row.get("First Mail Body", "")
        next_status = store.STATUS_SENT
    else:
        subject = row.get("Email Subject", "")
        if subject and not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"
        body = row.get(f"Followup {stage} Body", "")
        next_status = store.STATUS_FU1 if stage == 1 else store.STATUS_FU2

    if not subject.strip() or not body.strip():
        return {"ok": False, "name": name, "detail": "subject or body is empty"}

    if dry_run:
        return {"ok": True, "name": name, "email": email, "dry_run": True,
                "detail": "dry run - nothing sent"}

    if not api_key:
        return {"ok": False, "name": name, "detail": "MAILTRAP_API_KEY not in .env"}
    if not from_email:
        return {"ok": False, "name": name, "detail": "MAIL_FROM_ADDRESS not in .env"}

    ceo = row.get("Company CEO", "")
    to_name = ceo.split()[0] if ceo and ceo != "Not identified" else name
    ok, result = mailtrap_send(email, to_name, subject, body, from_email,
                               from_name, api_key)

    if ok:
        store.update(filename, lead_id, {
            "Status": next_status,
            "Date Contacted": date.today().isoformat(),
        })
        return {"ok": True, "name": name, "email": email, "detail": "sent"}

    store.update(filename, lead_id, {"Status": store.STATUS_FAILED})
    detail = result.get("error") or json.dumps(result)[:200]
    return {"ok": False, "name": name, "email": email, "detail": detail}


def do_batch_send(job_id, filename, lead_ids, stage, dry_run):
    sent, failed, log_lines = [], [], []
    for lead_id in lead_ids:
        try:
            outcome = send_one(filename, lead_id, stage, dry_run)
        except Exception as exc:
            outcome = {"ok": False, "name": f"lead {lead_id}", "detail": str(exc)}
        if not outcome["ok"]:
            mark = "✗ FAILED"
        elif outcome.get("dry_run"):
            mark = "· DRY   "
        else:
            mark = "✓ SENT  "
        line = f"{mark} {outcome['name']} <{outcome.get('email', '-')}> - {outcome['detail']}"
        job_log(job_id, line)
        log_lines.append(line)
        (sent if outcome["ok"] else failed).append(outcome["name"])

    summary = f"Summary: {len(sent)} sent, {len(failed)} failed" + (" (dry run)" if dry_run else "")
    job_log(job_id, summary)
    if log_lines and not dry_run:
        store.append_log(log_lines + [summary])
    job_done(job_id, result={"sent": sent, "failed": failed, "dry_run": dry_run})


# ── HTTP layer ──────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    server_version = "LeadDesk"

    def log_message(self, fmt, *args):
        pass  # keep the console clean; the UI shows what matters

    # -- helpers --
    def _json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length) or b"{}")

    def _static(self, name):
        path = (STATIC / Path(name).name)
        if not path.exists():
            self._json({"error": "not found"}, 404)
            return
        data = path.read_bytes()
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    # -- routes --
    def do_GET(self):
        url = urlparse(self.path)
        path, query = url.path, parse_qs(url.query)
        try:
            if path in ("/", "/index.html"):
                return self._static("index.html")
            if path.startswith("/static/"):
                return self._static(path[len("/static/"):])

            if path == "/api/bootstrap":
                files = store.list_files()
                current = query.get("file", [None])[0] or (files[0]["file"] if files else None)
                rows = store.read(current) if current else []
                env = store.load_env()
                return self._json({
                    "files": files,
                    "file": current,
                    "statuses": store.ALL_STATUSES,
                    "leads": rows,
                    "stats": store.stats(rows),
                    "timeline": store.timeline(rows),
                    "followups": store.followups_due(rows),
                    "today": date.today().isoformat(),
                    "identity": identity(env),
                    "mail_configured": bool(env.get("MAILTRAP_API_KEY")),
                    "apify_configured": bool(env.get("APIFY_API_KEY")),
                    "claude_key_configured": bool(env.get("ANTHROPIC_API_KEY", "").strip()),
                    "claude_sdk": importlib.util.find_spec("anthropic") is not None,
                })

            if path == "/api/log":
                return self._json({"log": store.read_log()})

            if path.startswith("/api/jobs/"):
                job_id = path.rsplit("/", 1)[-1]
                with JOBS_LOCK:
                    job = JOBS.get(job_id)
                if not job:
                    return self._json({"error": "no such job"}, 404)
                return self._json(job)

            return self._json({"error": "not found"}, 404)
        except ValueError as exc:
            return self._json({"error": str(exc)}, 400)
        except Exception as exc:
            traceback.print_exc()
            return self._json({"error": str(exc)}, 500)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            data = self._body()
            filename = data.get("file")

            if path == "/api/lead/update":
                lead = store.update(filename, int(data["id"]), data.get("patch", {}))
                return self._json({"lead": lead})

            if path == "/api/send":
                ids = [int(i) for i in data.get("ids", [])]
                stage = int(data.get("stage", 0))
                dry_run = bool(data.get("dry_run"))
                label = "follow-up" if stage else "first mail"
                job_id = new_job("send", f"Sending {label} to {len(ids)} lead(s)")
                run_in_thread(do_batch_send, job_id, filename, ids, stage, dry_run)
                return self._json({"job": job_id})

            if path == "/api/enrich":
                ids = [int(i) for i in data.get("ids", [])]
                job_id = new_job("enrich", f"Enriching {len(ids)} lead(s) from their websites")
                run_in_thread(do_enrich, job_id, filename, ids)
                return self._json({"job": job_id})

            if path == "/api/find-leads":
                location = (data.get("location") or "").strip()
                count = max(1, min(200, int(data.get("count") or 10)))
                categories = ", ".join(parse_categories(data.get("categories") or ""))
                mode = data.get("mode") if data.get("mode") in ("details", "research", "full") else "research"
                if not location:
                    return self._json({"error": "location is required"}, 400)
                if mode == "details":
                    # Plain Python path: Apify + scraper, no Claude, no copy written.
                    job_id = new_job("finddetails", f"Finding lead details in {location}")
                    run_in_thread(do_find_details, job_id, location, count, categories)
                    return self._json({"job": job_id})
                job_id = new_job("findleads", f"Finding leads in {location}")
                run_in_thread(do_find_leads, job_id, location, count, mode, categories)
                return self._json({"job": job_id})

            if path == "/api/jobs/stop":
                return self._json({"stopped": job_stop(data.get("id", ""))})

            return self._json({"error": "not found"}, 404)
        except (ValueError, IndexError) as exc:
            return self._json({"error": str(exc)}, 400)
        except Exception as exc:
            traceback.print_exc()
            return self._json({"error": str(exc)}, 500)


def main():
    parser = argparse.ArgumentParser(description="Lead Desk dashboard")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}"
    print(f"\n  Lead Desk running at {url}")
    print("  Ctrl-C to stop\n")
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
