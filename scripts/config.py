"""
Shared configuration for the lead pipeline.

Everything business-specific lives in .env at the project root, so one install
can be customised for any company without touching code. Secrets and identity
share that file — see .env.example for every key.

Identity keys:   COMPANY_NAME, COMPANY_TAGLINE, SENDER_NAME, MAIL_FROM_ADDRESS
Sourcing keys:   DEFAULT_LOCATION, DEFAULT_CATEGORIES
Service keys:    APIFY_API_KEY, MAILTRAP_API_KEY, ANTHROPIC_API_KEY
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"

# Used only when DEFAULT_CATEGORIES is not set in .env.
FALLBACK_CATEGORIES = [
    "restaurant", "hotel", "clinic", "pharmacy", "law firm",
    "accounting firm", "consulting firm", "training academy", "spa", "retail boutique",
]


def load_env(path=ENV_FILE):
    """Parse KEY=value lines from .env. Quotes are stripped; # lines and blanks ignored."""
    env = {}
    if path.exists():
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def parse_categories(text):
    """'dentist, gym;car wash' -> ['dentist', 'gym', 'car wash']. Dedupes, keeps order."""
    if not text:
        return []
    seen, out = set(), []
    for part in re.split(r"[,;\n]", text):
        part = " ".join(part.split())
        if part and part.lower() not in seen:
            seen.add(part.lower())
            out.append(part)
    return out


def default_categories(env=None):
    env = load_env() if env is None else env
    return parse_categories(env.get("DEFAULT_CATEGORIES")) or list(FALLBACK_CATEGORIES)


def identity(env=None):
    """Who the outreach is from, derived from .env with safe fallbacks."""
    env = load_env() if env is None else env
    company = env.get("COMPANY_NAME", "").strip() or "Our Company"
    sender = env.get("SENDER_NAME", "").strip() or company
    tagline = env.get("COMPANY_TAGLINE", "").strip()
    from_email = env.get("MAIL_FROM_ADDRESS", "").strip()

    from_name = company if sender == company else f"{sender} | {company}"
    signature = [sender, f"{company} — {tagline}" if tagline else company]
    if from_email:
        signature.append(from_email)

    return {
        "company_name": company,
        "sender_name": sender,
        "tagline": tagline,
        "from_email": from_email,
        "from_name": from_name,
        "signature": "\n".join(signature),
        "default_location": env.get("DEFAULT_LOCATION", "").strip(),
        "default_categories": default_categories(env),
    }
