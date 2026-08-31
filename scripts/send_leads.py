#!/usr/bin/env python3
"""
Dispatcher: reads lagos_nigeria_leads.csv, sends emails for all
'Ready to Send' rows via Mailtrap, and updates the CSV in place.
"""
import csv
import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
LEADS_FILE = ROOT / "leads" / "lagos_nigeria_leads.csv"
LOG_FILE = ROOT / "leads" / "send_log.txt"
ENV_FILE = ROOT / ".env"


def load_env():
    env = {}
    if ENV_FILE.exists():
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def send_email(to_email, to_name, subject, body_text, from_email, api_key):
    payload = {
        "from": {"email": from_email, "name": "Femi | Krediview"},
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
    from_email = env.get("MAIL_FROM_ADDRESS", "info@krediview.com")

    if not api_key:
        print("ERROR: MAILTRAP_API_KEY not in .env", file=sys.stderr)
        sys.exit(1)

    with open(LEADS_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    fieldnames = list(rows[0].keys()) if rows else []
    today = date.today().isoformat()

    sent, failed, skipped = [], [], []

    log_lines = [f"=== Krediview email send run — {today} ===\n"]

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

        success, detail = send_email(email, to_name, subject, body, from_email, api_key)

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

    with open(LEADS_FILE, "w", newline="", encoding="utf-8") as f:
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
