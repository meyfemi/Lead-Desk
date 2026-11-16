"""
CSV-backed data layer for the lead dashboard.

The lead CSVs in leads/ are the single source of truth - the same files the
/find-leads workflow and scripts/send_leads.py read and write. Everything here
reads and rewrites them in place so the UI and the CLI stay in sync.
"""
import csv
import re
import sys
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from config import load_env, identity  # noqa: E402,F401 - shared .env loader, re-exported

LEADS_DIR = ROOT / "leads"
LOG_FILE = LEADS_DIR / "send_log.txt"

COLUMNS = [
    "Company Name", "Company URL", "Company Address", "Company Email", "Company Phone",
    "Company CEO", "Company Summary", "Specific Sales Edges", "Email Subject",
    "First Mail Body", "Followup 1 Date", "Followup 1 Body", "Followup 2 Date",
    "Followup 2 Body", "Status", "Date Contacted",
]

# Status vocabulary shared with the /find-leads workflow, plus "Draft" for rows
# that have no outreach copy written yet.
STATUS_DRAFT = "Draft - Needs Copy"
STATUS_READY = "Ready to Send"
STATUS_SENT = "Sent"
STATUS_FAILED = "Send Failed"
STATUS_NO_EMAIL = "No Email - Skip Send"
STATUS_FU1 = "Followed Up 1"
STATUS_FU2 = "Followed Up 2 (Final)"

ALL_STATUSES = [
    STATUS_DRAFT, STATUS_READY, STATUS_SENT, STATUS_FU1,
    STATUS_FU2, STATUS_FAILED, STATUS_NO_EMAIL,
]

_write_lock = threading.Lock()


def slugify_location(location):
    slug = location.lower().replace(",", "").strip()
    slug = re.sub(r"\s+", "_", slug)
    return re.sub(r"[^a-z0-9_]", "", slug)


def lead_file_for(location):
    """The CSV /find-leads uses for a location: 'Accra, Ghana' -> accra_ghana_leads.csv."""
    return f"{slugify_location(location)}_leads.csv"


def list_files():
    """Every lead CSV in leads/, newest activity first."""
    LEADS_DIR.mkdir(exist_ok=True)
    out = []
    for path in sorted(LEADS_DIR.glob("*_leads.csv")):
        rows = read(path.name)
        out.append({
            "file": path.name,
            "label": path.stem.replace("_leads", "").replace("_", " ").title(),
            "count": len(rows),
        })
    return out


def resolve(filename):
    """Resolve a client-supplied filename to a path inside leads/ only."""
    if not filename:
        files = list_files()
        if not files:
            return None
        filename = files[0]["file"]
    name = Path(filename).name
    if not name.endswith(".csv"):
        raise ValueError("Not a CSV file")
    return LEADS_DIR / name


def read(filename):
    path = resolve(filename)
    if path is None or not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for i, row in enumerate(rows):
        for col in COLUMNS:
            row.setdefault(col, "")
        row["id"] = i
    return rows


def write(filename, rows):
    path = resolve(filename)
    with _write_lock:
        LEADS_DIR.mkdir(exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS, quoting=csv.QUOTE_ALL,
                                    extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)


def update(filename, lead_id, patch):
    rows = read(filename)
    if lead_id < 0 or lead_id >= len(rows):
        raise IndexError("No such lead")
    for key, value in patch.items():
        if key in COLUMNS:
            rows[lead_id][key] = value
    write(filename, rows)
    return rows[lead_id]


def append(filename, new_rows):
    """Append rows to a lead CSV, creating it if needed. Names already in the file are
    skipped (case-insensitive), the same duplicate rule /find-leads applies. Missing
    columns are written blank. Returns the rows actually added."""
    path = resolve(filename)
    existing = read(filename) if path.exists() else []
    known = {r["Company Name"].strip().lower() for r in existing}
    added = []
    for row in new_rows:
        name = (row.get("Company Name") or "").strip()
        if not name or name.lower() in known:
            continue
        known.add(name.lower())
        full = {col: row.get(col, "") for col in COLUMNS}
        existing.append(full)
        added.append(full)
    if added:
        write(filename, existing)
    return added


def has_email(row):
    email = (row.get("Company Email") or "").strip()
    return bool(email) and email.lower() != "not found"


def followups_due(rows, today=None):
    """Leads whose next follow-up touch is due on or before today."""
    today = today or date.today().isoformat()
    due = []
    for row in rows:
        status = row.get("Status", "")
        if status == STATUS_SENT:
            stage, when = 1, row.get("Followup 1 Date", "")
        elif status == STATUS_FU1:
            stage, when = 2, row.get("Followup 2 Date", "")
        else:
            continue
        if when and when <= today:
            due.append({**row, "followup_stage": stage, "due_date": when})
    return sorted(due, key=lambda r: r["due_date"])


def stats(rows):
    counts = {s: 0 for s in ALL_STATUSES}
    for row in rows:
        status = row.get("Status", "") or "Unknown"
        counts[status] = counts.get(status, 0) + 1
    contacted = counts[STATUS_SENT] + counts[STATUS_FU1] + counts[STATUS_FU2]
    reachable = sum(1 for r in rows if has_email(r))
    return {
        "total": len(rows),
        "reachable": reachable,
        "contacted": contacted,
        "by_status": counts,
        "followups_due": len(followups_due(rows)),
        "coverage": round(100 * contacted / reachable) if reachable else 0,
    }


def timeline(rows, days=30):
    """Contacted-per-day series for the activity chart.

    Anchored on today, but if the last send predates that window the series
    slides back to end on the most recent send - an outreach run from two
    months ago should still be visible rather than showing an empty chart.
    """
    counts = {}
    for row in rows:
        when = (row.get("Date Contacted") or "").strip()
        if when:
            counts[when] = counts.get(when, 0) + 1
    if not counts:
        return []
    end = date.today()
    window_start = end - timedelta(days=days - 1)
    if not any(k >= window_start.isoformat() for k in counts):
        try:
            end = date.fromisoformat(max(counts))
        except ValueError:
            pass
    start = end - timedelta(days=days - 1)
    series = []
    day = start
    while day <= end:
        key = day.isoformat()
        series.append({"date": key, "count": counts.get(key, 0)})
        day += timedelta(days=1)
    return series


def append_log(lines):
    LEADS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    company = identity()["company_name"]
    text = f"\n=== {company} dashboard send - {stamp} ===\n" + "\n".join(lines) + "\n"
    with _write_lock:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(text)


def read_log(limit=400):
    if not LOG_FILE.exists():
        return ""
    lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[-limit:])
