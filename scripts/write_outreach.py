"""
Outreach copywriting through the Claude API - the parts of /find-leads that need a model.

The dashboard's Find leads button uses this instead of the Claude Code CLI: Python does
the search, scrape, filing and sending, and calls Claude only to qualify a company and
write its summary, sales edges and emails. The rules here mirror Steps 5b-5e and 7 of
.claude/commands/find-leads.md - keep the two in step when you change either.

Needs the `anthropic` package (pip install anthropic) and ANTHROPIC_API_KEY in .env.
CLAUDE_MODEL in .env picks the model (blank: claude-opus-5-5).
"""
import json
import re
from datetime import timedelta

from config import ROOT, identity, load_env

DEFAULT_MODEL = "claude-opus-5-5"
# Models that accept server-side refusal fallbacks (fallbacks="default").
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5",
                   "claude-fable-5-2", "claude-fable-5-1"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"

BANNED_PHRASES = [
    "i hope this email finds you well", "i came across your business", "as per",
    "leverage", "utilize", "synergy", "exciting opportunity",
]
BAD_GREETINGS = ("dear sir", "dear business owner", "to whom it may concern", "dear ")
MAX_REVISIONS = 2


class OutreachError(RuntimeError):
    """Claude could not be reached or did not return usable copy. `fatal` errors (bad key,
    unknown model, no connection) stop the whole run; the rest skip one lead."""

    def __init__(self, message, fatal=True):
        super().__init__(message)
        self.fatal = fatal


def _read(name):
    path = ROOT / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


class Writer:
    """One per run. Holds the client and the cached system prompt (our offer + targets)."""

    def __init__(self, env=None):
        try:
            import anthropic
        except ImportError as exc:
            raise OutreachError("The anthropic package is not installed - run: "
                                "pip install anthropic") from exc
        self._anthropic = anthropic
        env = load_env() if env is None else env
        key = env.get("ANTHROPIC_API_KEY", "").strip()
        if not key:
            raise OutreachError("ANTHROPIC_API_KEY is not set in .env")
        self.client = anthropic.Anthropic(api_key=key, max_retries=4)
        self.model = env.get("CLAUDE_MODEL", "").strip() or DEFAULT_MODEL
        self.who = identity(env)
        offer, targets = _read("our_offer.md"), _read("target_businesses.md")
        if not offer.strip() or not targets.strip():
            raise OutreachError("our_offer.md and target_businesses.md must both exist "
                                "and be filled in - see CUSTOMIZING.md")
        self.system = self._system_prompt(offer, targets)
        self.usage = {"input": 0, "output": 0, "cache_read": 0}

    # ── prompt ──────────────────────────────────────────────────────────────
    def _system_prompt(self, offer, targets):
        who = self.who
        return f"""You write cold outreach emails for {who['company_name']}. {who['sender_name']} sends them.
Each email goes to one company's general contact inbox. You are given the facts we
collected about that company (its Google Maps listing and text scraped from its website)
and you qualify it, summarise it and write the email.

<our_offer>
{offer}
</our_offer>

<target_businesses>
{targets}
</target_businesses>

How to work:

1. Qualify. If one of the Red Flags in target_businesses applies to this company, set
   qualified to false and give the reason in skip_reason; leave the other fields empty.
   Otherwise qualified is true.

2. Summary: 2-3 sentences on what they do, who their customers are and their approximate
   size or reach, based only on the facts given. If the website could not be read, say
   "Website inaccessible." in the summary.

3. Sales edges: 2-3 concrete, company-specific reasons this business would benefit from
   our offer. Each one MUST pair something you can see in the facts given with one of the
   Signals to Look For in target_businesses - the shape is "[observed fact] -> [why it
   matters]". Never write generic edges like "they could benefit from our service" or
   "they are a growing business". If you can find no specific observed fact at all, set
   qualified to false with skip_reason "no specific sales edge".

4. Subject: 5-8 words, references their business name or a specific detail, no
   clickbait, no ALL CAPS, no question used as a hook.

5. Body (do NOT include a sign-off or your name - it is added afterwards):
   - Greeting to the team, not a person: "Hi [Company Name] team," or "Hi,". Never
     "Dear Sir/Ma", "Dear Business Owner", "To Whom It May Concern". If a contact name is
     known you may mention them in the body ("worth passing to [first name]"), never in the
     greeting.
   - Paragraph 1 (1-2 sentences): prove you looked - one specific detail from their site or
     listing.
   - Paragraph 2 (1-2 sentences): name the exact problem, using the most relevant edge. No
     hedging.
   - Paragraph 3 (1-2 sentences): the single most relevant benefit from our_offer that
     answers it. Never promise anything our_offer does not say we provide.
   - Paragraph 4 (1 sentence): a soft, low-friction call to action, usually a question. Not
     "click here", "book a call" or "sign up now".
   - 100-150 words including the greeting. Separate paragraphs with a blank line.
   - Google listing names are often padded with keywords or places ("Acme Spa Lekki -
     Massage, Sauna"). Use the name the business would call itself ("Acme Spa") and spell
     it the same way in the subject and body.
   - Never use: "I hope this email finds you well", "I came across your business",
     "as per", "leverage", "utilize", "synergy", "exciting opportunity".
   - Tone: the style our_offer describes, otherwise direct, human and informed. It must
     read as if someone researched this one company, not a template.

Only use facts that are in the data you are given. Never invent numbers, customers,
reviews or claims."""

    # ── API call ────────────────────────────────────────────────────────────
    def _call(self, messages, schema, max_tokens=4000):
        kwargs = dict(
            model=self.model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": self.system,
                     "cache_control": {"type": "ephemeral"}}],
            messages=messages,
            output_config={"effort": "medium",
                           "format": {"type": "json_schema", "schema": schema}},
        )
        a = self._anthropic
        try:
            if self.model in FALLBACK_MODELS:
                resp = self.client.beta.messages.create(
                    betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
            else:
                resp = self.client.messages.create(**kwargs)
        except a.AuthenticationError as exc:
            raise OutreachError("ANTHROPIC_API_KEY was rejected - check it in .env") from exc
        except a.PermissionDeniedError as exc:
            raise OutreachError(f"Claude API refused the key: {exc.message}") from exc
        except a.NotFoundError as exc:
            raise OutreachError(f"Unknown model '{self.model}' - check CLAUDE_MODEL in .env") from exc
        except a.BadRequestError as exc:
            raise OutreachError(f"Claude API rejected the request: {exc.message}", fatal=False) from exc
        except a.RateLimitError as exc:
            raise OutreachError("Claude API rate limit reached - wait a minute and retry") from exc
        except a.APIStatusError as exc:
            raise OutreachError(f"Claude API error {exc.status_code}: {exc.message}",
                                fatal=exc.status_code < 500) from exc
        except a.APIConnectionError as exc:
            raise OutreachError("Could not reach the Claude API - check the internet connection") from exc

        u = resp.usage
        self.usage["input"] += (u.input_tokens or 0) + (getattr(u, "cache_creation_input_tokens", 0) or 0)
        self.usage["cache_read"] += getattr(u, "cache_read_input_tokens", 0) or 0
        self.usage["output"] += u.output_tokens or 0

        if resp.stop_reason == "refusal":
            raise OutreachError("Claude declined to write this one", fatal=False)
        if resp.stop_reason == "max_tokens":
            raise OutreachError("Claude's reply was cut off", fatal=False)
        text = "".join(b.text for b in resp.content if b.type == "text")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise OutreachError("Claude returned invalid JSON", fatal=False) from exc

    # ── first email ─────────────────────────────────────────────────────────
    LEAD_SCHEMA = {
        "type": "object",
        "properties": {
            "qualified": {"type": "boolean"},
            "skip_reason": {"type": "string"},
            "summary": {"type": "string"},
            "sales_edges": {"type": "array", "items": {"type": "string"}},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["qualified", "skip_reason", "summary", "sales_edges", "subject", "body"],
        "additionalProperties": False,
    }

    def write_lead(self, facts):
        """Qualify one company and write its copy. `facts` is a dict of what we know.

        Returns {'qualified': False, 'skip_reason': ...} or a dict with summary,
        sales_edges (list), subject, body (sign-off included) and `issues` - the quality
        checks still failing after MAX_REVISIONS rewrites (empty when it passed)."""
        messages = [{"role": "user", "content":
                     "Company facts (JSON):\n" + json.dumps(facts, indent=2, ensure_ascii=False)}]
        out = self._call(messages, self.LEAD_SCHEMA)
        if not out.get("qualified"):
            return {"qualified": False, "skip_reason": out.get("skip_reason") or "red flag"}

        for _ in range(MAX_REVISIONS):
            issues = check_first_email(out)
            if not issues:
                break
            messages += [
                {"role": "assistant", "content": json.dumps(out, ensure_ascii=False)},
                {"role": "user", "content":
                 "This draft fails these checks:\n- " + "\n- ".join(issues)
                 + "\nRewrite whatever fails and return the full JSON again. Keep "
                   "qualified true unless a red flag applies."},
            ]
            revised = self._call(messages, self.LEAD_SCHEMA)
            if not revised.get("qualified"):
                return {"qualified": False, "skip_reason": revised.get("skip_reason") or "red flag"}
            out = revised
        issues = check_first_email(out)

        return {
            "qualified": True,
            "summary": out["summary"].strip(),
            "sales_edges": [e.strip() for e in out["sales_edges"] if e.strip()],
            "subject": " ".join(out["subject"].split()),
            "body": out["body"].strip() + "\n\n" + self.who["signature"],
            "issues": issues,
        }

    # ── follow-ups ──────────────────────────────────────────────────────────
    FOLLOWUP_SCHEMA = {
        "type": "object",
        "properties": {"body": {"type": "string"}},
        "required": ["body"],
        "additionalProperties": False,
    }

    def write_followup(self, row, stage, days_since):
        """Write follow-up `stage` (1 or 2) for a lead row. Returns the body, sign-off included."""
        if stage == 1:
            brief = (f"Write follow-up 1. The first email went {days_since} days ago. 2-3 "
                     "sentences only. Open by referring back to that email naturally (e.g. "
                     f"\"Just checking back on the note I sent {days_since} days ago about...\"), "
                     "add one new angle or detail - do not repeat the original pitch - and end "
                     "with the same kind of soft question.")
        else:
            brief = ("Write follow-up 2, the final touch. Use a different angle from both the "
                     "original email and follow-up 1. 2-3 sentences, respectful. If our_offer or "
                     "target_businesses has a real Proof Point you may use one sentence of it; "
                     "never invent a statistic or a customer.")
        context = {k: row.get(k, "") for k in (
            "Company Name", "Company Summary", "Specific Sales Edges", "Email Subject",
            "First Mail Body", "Followup 1 Body")}
        prompt = (brief + " Greet the team (\"Hi,\" or \"Hi [Company Name] team,\"). No sign-off - "
                  "it is added afterwards. The same banned phrases apply.\n\nLead (JSON):\n"
                  + json.dumps(context, indent=2, ensure_ascii=False))
        messages = [{"role": "user", "content": prompt}]
        out = self._call(messages, self.FOLLOWUP_SCHEMA, max_tokens=2000)
        for _ in range(MAX_REVISIONS):
            issues = check_followup(out.get("body", ""))
            if not issues:
                break
            messages += [
                {"role": "assistant", "content": json.dumps(out, ensure_ascii=False)},
                {"role": "user", "content": "This fails these checks:\n- " + "\n- ".join(issues)
                 + "\nRewrite it and return the JSON again."},
            ]
            out = self._call(messages, self.FOLLOWUP_SCHEMA, max_tokens=2000)
        if check_followup(out.get("body", "")):
            raise OutreachError("follow-up failed the quality checks", fatal=False)
        return out["body"].strip() + "\n\n" + self.who["signature"]

    def cost_line(self):
        u = self.usage
        return (f"Claude usage: {u['input']:,} input tokens, {u['cache_read']:,} cached, "
                f"{u['output']:,} output ({self.model})")


# ── quality checks (Step 5e, the parts code can verify) ─────────────────────

def word_count(text):
    return len(re.findall(r"\b[\w'’-]+\b", text))


def _common_issues(body):
    issues = []
    low = body.lower()
    first_line = low.strip().splitlines()[0] if low.strip() else ""
    if not first_line.startswith("hi"):
        issues.append('The greeting must be "Hi [Company Name] team," or "Hi,".')
    if any(first_line.startswith(g) for g in BAD_GREETINGS):
        issues.append("The greeting must address the team, not 'Dear ...'.")
    for phrase in BANNED_PHRASES:
        if re.search(r"\b" + re.escape(phrase) + r"\b", low):
            issues.append(f'Remove the phrase "{phrase}".')
    return issues


def check_first_email(out):
    body, subject = out.get("body", ""), out.get("subject", "")
    issues = _common_issues(body)
    # The prompt asks for 100-150 words and a 5-8 word subject; the limits here carry a
    # little slack so a near miss isn't sent back for a rewrite.
    words = word_count(body)
    if not 90 <= words <= 165:
        issues.append(f"The body is {words} words; it must be 100-150.")
    sw = len(subject.split())
    if not 4 <= sw <= 10:
        issues.append(f"The subject is {sw} words; it must be 5-8.")
    if subject.isupper() or subject.strip().endswith("?"):
        issues.append("The subject must not be ALL CAPS or a question.")
    edges = [e for e in out.get("sales_edges", []) if e.strip()]
    if not 2 <= len(edges) <= 3:
        issues.append(f"There are {len(edges)} sales edges; write 2-3.")
    paragraphs = [p for p in re.split(r"\n\s*\n", body.strip()) if p.strip()]
    if len(paragraphs) < 4:
        issues.append("The body needs the greeting plus four short paragraphs separated by blank lines.")
    return issues


def check_followup(body):
    issues = _common_issues(body)
    words = word_count(body)
    if words > 90:
        issues.append(f"The follow-up is {words} words; keep it to 2-3 short sentences.")
    return issues


def business_days_from(start, days):
    """`days` business days after `start` (a date), skipping Saturdays and Sundays."""
    d, added = start, 0
    while added < days:
        d += timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d
