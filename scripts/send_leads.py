#!/usr/bin/env python3
"""
Dispatcher: reads a leads CSV, sends emails for all 'Ready to Send' rows via
Mailtrap, and updates the CSV in place.

    python3 scripts/send_leads.py                       # leads/<DEFAULT_LOCATION>_leads.csv
    python3 scripts/send_leads.py leads/accra_ghana_leads.csv
"""
import csv
import json
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

from config import ROOT, load_env, identity

LOG_FILE = ROOT / "leads" / "send_log.txt"


def default_leads_file(env):
    location = env.get("DEFAULT_LOCATION", "")
    slug = re.sub(r"\s+", "_", location.lower().replace(",", "").strip())
    slug = re.sub(r"[^a-z0-9_]", "", slug)
    return ROOT / "leads" / f"{slug}_leads.csv" if slug else None


def send_email(to_email, to_name, subject, body_text, from_email, from_name, api_key):
    payload = {
        "from": {"email": from_email, "name": from_name},
        "to": [{"email": to_email, "name": to_name or to_email}],
        "subject": subject,
        "text": body_text,
    }
    cmd = [
        "curl", "--silent", "--show-error",
        "-X", "POST", "https://send.api.mailtrap.io/api/send",
        "-H", f"Authorization: Bearer {api_key}",
        "-H", "Content-Type: application/json",
        "-d", json.dumps(payload),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            return False, proc.stderr.strip()
        result = json.loads(proc.stdout)
        return result.get("success", False), proc.stdout.strip()
    except subprocess.TimeoutExpired:
        return False, "Timed out after 30s"
    except Exception as e:
        return False, str(e)


def main():
    if not shutil.which("curl"):
        print("ERROR: curl not found", file=sys.stderr)
        sys.exit(1)

    env = load_env()
    api_key = env.get("MAILTRAP_API_KEY")
    who = identity(env)
    from_email, from_name = who["from_email"], who["from_name"]

    if not api_key:
        print("ERROR: MAILTRAP_API_KEY not in .env", file=sys.stderr)
        sys.exit(1)
    if not from_email:
        print("ERROR: MAIL_FROM_ADDRESS not in .env", file=sys.stderr)
        sys.exit(1)

    leads_file = Path(sys.argv[1]) if len(sys.argv) > 1 else default_leads_file(env)
    if not leads_file:
        print("ERROR: pass a leads CSV path, or set DEFAULT_LOCATION in .env", file=sys.stderr)
        sys.exit(1)
    if not leads_file.exists():
        print(f"ERROR: {leads_file} does not exist", file=sys.stderr)
        sys.exit(1)

    with open(leads_file, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    fieldnames = list(rows[0].keys()) if rows else []
    today = date.today().isoformat()

    sent, failed, skipped = [], [], []

    log_lines = [f"=== {who['company_name']} email send run — {today} ===\n"]

    for row in rows:
        name = row["Company Name"]
        status = row["Status"]

        if status != "Ready to Send":
            skipped.append(name)
            continue

        email = row["Company Email"]
        if not email or email == "Not found":
            row["Status"] = "No Email — Skip Send"
            skipped.append(name)
            continue

        subject = row["Email Subject"]
        body = row["First Mail Body"]
        ceo = row["Company CEO"]
        to_name = ceo.split()[0] if ceo and ceo != "Not identified" else name

        success, detail = send_email(email, to_name, subject, body, from_email, from_name, api_key)

        if success:
            row["Status"] = "Sent"
            row["Date Contacted"] = today
            sent.append(name)
            log_lines.append(f"✓ SENT     {name} <{email}>")
            print(f"✓ Email sent to {name} ({email})")
        else:
            row["Status"] = "Send Failed"
            failed.append(name)
            log_lines.append(f"✗ FAILED   {name} <{email}> — {detail}")
            print(f"✗ Failed:  {name} ({email}) — {detail}")

    with open(leads_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)

    log_lines.append(f"\nSummary: {len(sent)} sent, {len(failed)} failed, {len(skipped)} skipped")
    if failed:
        log_lines.append("Failed: " + ", ".join(failed))

    log_text = "\n".join(log_lines) + "\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_text)

    print(f"\nDone — {len(sent)} sent, {len(failed)} failed, {len(skipped)} skipped")
    print(f"Log: {LOG_FILE}")


if __name__ == "__main__":
    main()
