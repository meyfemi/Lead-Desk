#!/usr/bin/env python3
"""
Apify Google Maps business scraper for lead generation.
Searches a location for every business category given (or the defaults from .env).

    python3 scripts/apify_search.py --location "Lagos, Nigeria" --count 20
    python3 scripts/apify_search.py --location "Accra, Ghana" --categories "dentist, gym, car wash"
"""
import argparse
import json
import ssl
import sys
import time
import urllib.request
import urllib.error

from config import load_env, default_categories, parse_categories

_SSL_CTX = ssl.create_default_context()
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX.check_hostname = False
    _SSL_CTX.verify_mode = ssl.CERT_NONE


def apify_request(url, method="GET", data=None, api_key=None):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        print(f"HTTP {e.code}: {error_body}", file=sys.stderr)
        raise


def run_actor(search_queries, count_per_query, api_key):
    actor_id = "compass~crawler-google-places"
    run_input = {
        "searchStringsArray": search_queries,
        "maxCrawledPlacesPerSearch": count_per_query,
        "language": "en",
        "exportPlaceUrls": True,
        "additionalInfo": True,
        "includeHistogram": False,
        "includeOpeningHours": False,
        "includePeopleAlsoSearch": False,
    }

    url = f"https://api.apify.com/v2/acts/{actor_id}/runs"
    print(f"[Apify] Starting run with {len(search_queries)} queries...", file=sys.stderr)
    run = apify_request(url, method="POST", data=run_input, api_key=api_key)
    run_id = run["data"]["id"]
    dataset_id = run["data"]["defaultDatasetId"]
    print(f"[Apify] Run ID: {run_id}", file=sys.stderr)

    # Poll until finished
    status_url = f"https://api.apify.com/v2/actor-runs/{run_id}"
    terminal_statuses = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}
    elapsed = 0
    while True:
        time.sleep(15)
        elapsed += 15
        status_data = apify_request(status_url, api_key=api_key)
        status = status_data["data"]["status"]
        item_count = status_data["data"].get("stats", {}).get("itemsWrittenCount", "?")
        print(f"[Apify] {elapsed}s — status: {status}, items: {item_count}", file=sys.stderr)
        if status in terminal_statuses:
            break

    if status_data["data"]["status"] != "SUCCEEDED":
        raise RuntimeError(f"Apify run ended with status: {status_data['data']['status']}")

    # Fetch dataset items (paginated)
    all_items = []
    offset = 0
    limit = 200
    while True:
        items_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?limit={limit}&offset={offset}"
        batch = apify_request(items_url, api_key=api_key)
        if not batch:
            break
        all_items.extend(batch)
        if len(batch) < limit:
            break
        offset += limit

    return all_items


def filter_and_normalize(items):
    """Normalize Apify output to a clean lead dict and filter obvious non-qualifying entries."""
    leads = []
    seen_names = set()

    for item in items:
        name = (item.get("title") or "").strip()
        if not name or name.lower() in seen_names:
            continue

        website = (item.get("website") or "").strip()
        address = (item.get("address") or "").strip()
        phone = (item.get("phone") or "").strip()
        email = (item.get("email") or "").strip()
        category = (item.get("categoryName") or "").strip()
        rating = item.get("totalScore")
        review_count = item.get("reviewsCount", 0)

        # Skip clearly informal/unqualified entries (no website, no address)
        if not website and not address:
            continue

        lead = {
            "name": name,
            "website": website,
            "address": address,
            "phone": phone,
            "email": email,
            "category": category,
            "google_rating": rating,
            "google_review_count": review_count,
            "place_id": item.get("placeId", ""),
            "maps_url": item.get("url", ""),
        }
        leads.append(lead)
        seen_names.add(name.lower())

    return leads


def build_search_queries(location, categories):
    return [f"{category} in {location}" for category in categories]


def main():
    parser = argparse.ArgumentParser(description="Search for business leads via Apify")
    parser.add_argument("--location", required=True, help='e.g. "Lagos, Nigeria"')
    parser.add_argument("--count", type=int, default=10, help="Target number of leads")
    parser.add_argument("--categories", default="",
                        help='Comma-separated business types, e.g. "dentist, gym, car wash". '
                             "Replaces DEFAULT_CATEGORIES from .env for this run.")
    parser.add_argument("--output", default="-", help="Output JSON file path (- for stdout)")
    args = parser.parse_args()

    env = load_env()
    api_key = env.get("APIFY_API_KEY")
    if not api_key:
        print("Error: APIFY_API_KEY not found in .env", file=sys.stderr)
        sys.exit(1)

    categories = parse_categories(args.categories) or default_categories(env)
    print(f"[Apify] Categories: {', '.join(categories)}", file=sys.stderr)

    # Request enough per query to exceed the target; we'll trim after filtering
    count_per_query = max(5, (args.count // len(categories)) + 3)
    queries = build_search_queries(args.location, categories)

    raw_items = run_actor(queries, count_per_query, api_key)
    leads = filter_and_normalize(raw_items)

    print(f"[Apify] Raw items: {len(raw_items)}, qualified leads: {len(leads)}", file=sys.stderr)

    output = json.dumps(leads, indent=2, ensure_ascii=False)
    if args.output == "-":
        print(output)
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"[Apify] Results written to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
