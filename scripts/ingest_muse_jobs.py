"""
Fetch job listings from The Muse public API and store in Cloudant.

Usage:
    # Run a batch preset:
    python scripts/ingest_muse_jobs.py --batch tech-all
    python scripts/ingest_muse_jobs.py --batch tech-us

    # Custom query:
    python scripts/ingest_muse_jobs.py --category "Software Engineering" --level "Mid Level"

    # Limit pages (useful for testing):
    python scripts/ingest_muse_jobs.py --batch tech-all --max-pages 2

    # Dry run (preview URL and page count without storing):
    python scripts/ingest_muse_jobs.py --batch tech-all --dry-run

Requires .env with:
    CLOUDANT_URL, CLOUDANT_APIKEY
"""

import argparse
import os
import sys
import time
from html.parser import HTMLParser

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from app.database import get_cloudant, ensure_database

MUSE_API_URL = "https://www.themuse.com/api/public/jobs"
DB_NAME = "muse_jobs"
MAX_API_PAGE = 99  # The Muse API rejects page >= 100 with 400 Bad Request

# ---------------------------------------------------------------------------
# Batch presets
# ---------------------------------------------------------------------------

TECH_CATEGORIES = ["Software Engineering", "Data Science", "Data and Analytics", "Computer and IT"]
ALL_LEVELS = ["Entry Level", "Mid Level", "Senior Level"]
US_CITIES = [
    "New York, NY",
    "San Francisco, CA",
    "Chicago, IL",
    "Seattle, WA",
    "Los Angeles, CA",
    "Austin, TX",
    "Boston, MA",
]

BATCH_PRESETS = {
    "tech-all": {
        "categories": TECH_CATEGORIES,
        "levels": ALL_LEVELS,
        "locations": [],
    },
    "tech-us": {
        "categories": TECH_CATEGORIES,
        "levels": ALL_LEVELS,
        "locations": US_CITIES,
    },
}

# ---------------------------------------------------------------------------
# HTML stripping helper
# ---------------------------------------------------------------------------

class _HTMLStripper(HTMLParser):
    """Simple HTML-to-plain-text converter using only the stdlib."""

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str):
        self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts).strip()


def strip_html(html: str) -> str:
    stripper = _HTMLStripper()
    stripper.feed(html)
    return stripper.get_text()

# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def build_api_params(
    categories: list[str],
    levels: list[str],
    locations: list[str],
    page: int = 0,
) -> list[tuple[str, str]]:
    """Build query params as a list of tuples (supports repeated keys)."""
    params: list[tuple[str, str]] = [("page", str(page))]
    for c in categories:
        params.append(("category", c))
    for l in levels:
        params.append(("level", l))
    for loc in locations:
        params.append(("location", loc))
    return params


def fetch_page(params: list[tuple[str, str]]) -> dict | None:
    try:
        resp = requests.get(MUSE_API_URL, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print(f"  ERROR: {e}")
        return None


def transform_job(job: dict) -> dict:
    """Transform a Muse API job object into our Cloudant document schema."""
    return {
        "type": "muse_job",
        "source": "themuse",
        "muse_id": job.get("id"),
        "title": job.get("name", ""),
        "company": (job.get("company") or {}).get("name", ""),
        "locations": [loc["name"] for loc in job.get("locations", [])],
        "categories": [cat["name"] for cat in job.get("categories", [])],
        "levels": [lvl["name"] for lvl in job.get("levels", [])],
        "publication_date": job.get("publication_date", ""),
        "description": strip_html(job.get("contents", "")),
        "landing_page_url": (job.get("refs") or {}).get("landing_page", ""),
    }

# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def find_existing_muse_ids(client, muse_ids: list[int]) -> set[int]:
    """Query Cloudant for already-stored muse_ids."""
    if not muse_ids:
        return set()
    try:
        result = client.post_find(
            db=DB_NAME,
            selector={"muse_id": {"$in": muse_ids}},
            fields=["muse_id"],
            limit=len(muse_ids),
        ).get_result()
        return {doc["muse_id"] for doc in result.get("docs", [])}
    except Exception:
        return set()

# ---------------------------------------------------------------------------
# Main ingestion
# ---------------------------------------------------------------------------

def _build_query_combos(
    categories: list[str],
    levels: list[str],
    locations: list[str],
) -> list[dict]:
    """Split categories × levels into individual combos to work around the
    Muse API's 100-page pagination cap. Each combo gets its own 100-page
    window, maximizing the total jobs we can reach."""
    combos = []
    cats = categories or [""]
    lvls = levels or [""]
    for cat in cats:
        for lvl in lvls:
            combo = {"categories": [cat] if cat else [], "levels": [lvl] if lvl else [], "locations": locations}
            combos.append(combo)
    return combos


def _fetch_combo(
    categories: list[str],
    levels: list[str],
    locations: list[str],
    max_pages: int | None,
    dry_run: bool,
    client,
) -> tuple[int, int, int]:
    """Fetch and store pages for a single category+level combo.
    Returns (fetched, stored, skipped) counts."""
    params = build_api_params(categories, levels, locations, page=0)
    url = requests.Request("GET", MUSE_API_URL, params=params).prepare().url

    label = f"{categories[0] if categories else 'all'} / {levels[0] if levels else 'all'}"
    print(f"\n--- {label} ---")
    print(f"URL: {url}")

    first_page = fetch_page(params)
    if first_page is None:
        print("ERROR: Failed to fetch first page.")
        return 0, 0, 0

    page_count = first_page.get("page_count", 1)
    # Cap at API hard limit and optional user limit
    api_cap = min(page_count, MAX_API_PAGE + 1)
    total_pages = min(api_cap, max_pages) if max_pages else api_cap
    total_jobs = first_page.get("total", 0)

    print(f"Available: {total_jobs} jobs across {page_count} pages (fetching {total_pages})")

    if page_count > MAX_API_PAGE + 1:
        print(f"Note: API caps at page {MAX_API_PAGE}, {page_count - MAX_API_PAGE - 1} pages unreachable")

    if dry_run:
        results = first_page.get("results", [])
        for job in results[:3]:
            company = (job.get("company") or {}).get("name", "?")
            print(f"  - {job.get('name', '?')} @ {company}")
        return total_jobs, 0, 0

    combo_fetched = 0
    combo_stored = 0
    combo_skipped = 0

    for page_num in range(total_pages):
        if page_num == 0:
            data = first_page
        else:
            page_params = build_api_params(categories, levels, locations, page=page_num)
            data = fetch_page(page_params)
            if data is None:
                print(f"  [page {page_num + 1}/{total_pages}] ERROR, skipping.")
                continue

        results = data.get("results", [])
        docs = [transform_job(job) for job in results]
        combo_fetched += len(docs)

        # Deduplicate
        muse_ids = [d["muse_id"] for d in docs if d["muse_id"] is not None]
        existing = find_existing_muse_ids(client, muse_ids)
        new_docs = [d for d in docs if d["muse_id"] not in existing]
        skipped = len(docs) - len(new_docs)

        if new_docs:
            client.post_bulk_docs(db=DB_NAME, bulk_docs={"docs": new_docs}).get_result()

        combo_stored += len(new_docs)
        combo_skipped += skipped

        print(
            f"  [page {page_num + 1}/{total_pages}] "
            f"Fetched {len(docs)}, stored {len(new_docs)} "
            f"({skipped} dupes)"
        )

        if page_num < total_pages - 1:
            time.sleep(1)

    print(f"  Subtotal: {combo_fetched} fetched, {combo_stored} stored, {combo_skipped} skipped")
    return combo_fetched, combo_stored, combo_skipped


def run_ingestion(
    categories: list[str],
    levels: list[str],
    locations: list[str],
    max_pages: int | None = None,
    dry_run: bool = False,
):
    if not dry_run:
        if not os.getenv("CLOUDANT_URL") or not os.getenv("CLOUDANT_APIKEY"):
            print("ERROR: Set CLOUDANT_URL and CLOUDANT_APIKEY in .env")
            sys.exit(1)

    client = None
    if not dry_run:
        client = get_cloudant()
        ensure_database(DB_NAME)

    combos = _build_query_combos(categories, levels, locations)
    print(f"Running {len(combos)} query combo(s) to maximize coverage past API page limit")

    grand_fetched = 0
    grand_stored = 0
    grand_skipped = 0

    for combo in combos:
        fetched, stored, skipped = _fetch_combo(
            categories=combo["categories"],
            levels=combo["levels"],
            locations=combo["locations"],
            max_pages=max_pages,
            dry_run=dry_run,
            client=client,
        )
        grand_fetched += fetched
        grand_stored += stored
        grand_skipped += skipped

    print(f"\n{'=' * 50}")
    if dry_run:
        print(f"DRY RUN — {grand_fetched} total jobs available across {len(combos)} queries. No data stored.")
    else:
        print(f"Done. Fetched {grand_fetched} jobs across {len(combos)} queries.")
        print(f"Stored {grand_stored} new records, skipped {grand_skipped} duplicates in Cloudant '{DB_NAME}'.")


def main():
    parser = argparse.ArgumentParser(description="Ingest job listings from The Muse API into Cloudant")
    parser.add_argument("--batch", choices=list(BATCH_PRESETS.keys()),
                        help="Run a predefined batch preset")
    parser.add_argument("--category", action="append", default=[],
                        help="Filter by category (repeatable)")
    parser.add_argument("--level", action="append", default=[],
                        help="Filter by level (repeatable)")
    parser.add_argument("--location", action="append", default=[],
                        help="Filter by location (repeatable)")
    parser.add_argument("--max-pages", type=int, default=None,
                        help="Max number of pages to fetch (default: all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview API URL and first page without storing data")
    args = parser.parse_args()

    if args.batch:
        preset = BATCH_PRESETS[args.batch]
        categories = preset["categories"]
        levels = preset["levels"]
        locations = preset["locations"]
    elif args.category or args.level or args.location:
        categories = args.category
        levels = args.level
        locations = args.location
    else:
        parser.error("Provide --batch or at least one of --category, --level, --location")

    run_ingestion(
        categories=categories,
        levels=levels,
        locations=locations,
        max_pages=args.max_pages,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
