#!/usr/bin/env python3
"""
Website scraper - extracts CEO name, contact email, phone, and key page text
from a business website to enrich lead data before writing outreach emails.
"""
import json
import re
import ssl
import sys
import urllib.request
import urllib.error
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

_SSL_CTX = ssl.create_default_context()
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX.check_hostname = False
    _SSL_CTX.verify_mode = ssl.CERT_NONE


CEO_TITLE_PATTERNS = [
    r"(?:CEO|Chief Executive Officer|Founder|Co-Founder|Managing Director|MD|Director General|Owner|Principal)\s*[:\-,]?\s*([A-Z][a-z]+(?: [A-Z][a-z]+)+)",
    r"([A-Z][a-z]+(?: [A-Z][a-z]+)+)\s*[,\-]?\s*(?:CEO|Chief Executive Officer|Founder|Co-Founder|Managing Director|MD|Owner|Director)",
]

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(
    r"(?:\+?234|0)[\s\-]?[789][\s\-]?[01][\s\-]?(?:\d[\s\-]?){7}\d"
    r"|(?:\+\d{1,3}[\s\-]?)?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4}"
)


class PageParser(HTMLParser):
    """Extracts visible text, mailto/tel links, the <title> and meta description."""

    SKIP_TAGS = {"script", "style", "noscript", "svg"}

    def __init__(self):
        super().__init__()
        self._skip_depth = 0
        self._in_head = False
        self._in_title = False
        self.title = ""
        self.description = ""
        self.text_blocks = []
        self.emails_from_links = []
        self.phones_from_links = []

    def handle_starttag(self, tag, attrs):
        if tag == "head":
            self._in_head = True
            return
        if tag == "title" and self._in_head:
            self._in_title = True
            return
        if tag == "meta":
            attrs_dict = {k.lower(): (v or "") for k, v in attrs}
            key = (attrs_dict.get("name") or attrs_dict.get("property") or "").lower()
            content = " ".join(attrs_dict.get("content", "").split())
            if content and key in ("description", "og:description", "twitter:description"):
                # Plain description wins; the social variants only fill a gap.
                if not self.description or key == "description":
                    self.description = content
            return
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag == "a":
            attrs_dict = dict(attrs)
            href = attrs_dict.get("href", "")
            if href.startswith("mailto:"):
                addr = href[7:].split("?")[0].strip()
                if addr:
                    self.emails_from_links.append(addr)
            elif href.startswith("tel:"):
                self.phones_from_links.append(href[4:].strip())

    def handle_endtag(self, tag):
        if tag == "head":
            self._in_head = False
        elif tag == "title":
            self._in_title = False
        elif tag in self.SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)

    def handle_data(self, data):
        if self._in_title:
            self.title = (self.title + " " + data).strip()
            return
        if self._in_head or self._skip_depth:
            return
        text = data.strip()
        if len(text) > 1:
            self.text_blocks.append(text)

    def get_text(self):
        return " ".join(self.text_blocks)


def fetch_page(url, timeout=15):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,*/*",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
        charset = "utf-8"
        content_type = resp.headers.get("Content-Type", "")
        if "charset=" in content_type:
            charset = content_type.split("charset=")[-1].strip().split(";")[0]
        return resp.read().decode(charset, errors="replace")


def try_contact_page(base_url, html):
    """Try to fetch /contact or /about if we found nothing useful on the homepage."""
    candidates = ["/contact", "/contact-us", "/about", "/about-us", "/team"]
    found_links = re.findall(r'href=["\']([^"\']*(?:contact|about|team)[^"\']*)["\']', html, re.I)
    for link in found_links[:3]:
        candidates.insert(0, link)

    for path in candidates[:4]:
        try:
            url = urljoin(base_url, path)
            if urlparse(url).netloc != urlparse(base_url).netloc:
                continue
            return fetch_page(url)
        except Exception:
            continue
    return ""


def extract_ceo_names(text):
    names = []
    for pattern in CEO_TITLE_PATTERNS:
        names.extend(re.findall(pattern, text))
    # Deduplicate preserving order
    seen = set()
    result = []
    for n in names:
        if n.lower() not in seen:
            seen.add(n.lower())
            result.append(n)
    return result


def scrape(url):
    result = {
        "url": url,
        "title": "",
        "description": "",
        "emails": [],
        "phones": [],
        "ceo_names": [],
        "page_text_excerpt": "",
        "error": None,
    }

    try:
        homepage_html = fetch_page(url)
    except Exception as e:
        result["error"] = f"Could not load page: {e}"
        return result

    parser = PageParser()
    parser.feed(homepage_html)
    text = parser.get_text()
    result["title"] = parser.title
    result["description"] = parser.description

    # Try contact/about page if homepage is sparse
    if len(text) < 500 or not (parser.emails_from_links or EMAIL_RE.search(text)):
        extra_html = try_contact_page(url, homepage_html)
        if extra_html:
            extra_parser = PageParser()
            extra_parser.feed(extra_html)
            text += " " + extra_parser.get_text()
            parser.emails_from_links.extend(extra_parser.emails_from_links)
            parser.phones_from_links.extend(extra_parser.phones_from_links)

    # Collect emails
    emails = list(dict.fromkeys(
        parser.emails_from_links + EMAIL_RE.findall(text)
    ))
    # Filter out common non-contact emails
    skip_domains = {"example.com", "sentry.io", "w3.org", "schema.org"}
    emails = [e for e in emails if e.split("@")[-1] not in skip_domains]
    result["emails"] = emails[:5]

    # Collect phones
    phones = list(dict.fromkeys(
        parser.phones_from_links + [m.group() for m in PHONE_RE.finditer(text)]
    ))
    result["phones"] = phones[:3]

    # CEO names
    result["ceo_names"] = extract_ceo_names(text)

    # Text excerpt for LLM context (first 3000 chars of visible text)
    result["page_text_excerpt"] = text[:3000]

    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: scrape_website.py <url>", file=sys.stderr)
        sys.exit(1)
    url = sys.argv[1]
    if not url.startswith("http"):
        url = "https://" + url
    result = scrape(url)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
