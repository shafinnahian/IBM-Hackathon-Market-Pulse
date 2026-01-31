"""
Fetch job listings from The Muse public API and store in Cloudant (market_pulse_jobs)
using the same canonical job_post schema as Adzuna.

Usage:
    python -m market_pulse.scripts.collect_muse --batch tech-all
    python -m market_pulse.scripts.collect_muse --batch tech-all --max-pages 2
    python -m market_pulse.scripts.collect_muse --category "Software Engineering" --level "Mid Level"
    python -m market_pulse.cli collect-muse --batch tech-all

Requires CLOUDANT_URL, CLOUDANT_APIKEY in .env.
"""

import argparse
import os
import time
from html.parser import HTMLParser

import httpx
from dotenv import load_dotenv

from market_pulse.companies import ensure_company
from market_pulse.roles import DEFAULT_ROLES, map_title_to_role_id

load_dotenv()

DB_NAME = os.environ.get("CLOUDANT_DB_NAME", "market_pulse_jobs")
MUSE_API_URL = "https://www.themuse.com/api/public/jobs"
MAX_API_PAGE = 99  # The Muse API rejects page >= 100 with 400 Bad Request

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
    "tech-all": {"categories": TECH_CATEGORIES, "levels": ALL_LEVELS, "locations": []},
    "tech-us": {"categories": TECH_CATEGORIES, "levels": ALL_LEVELS, "locations": US_CITIES},
}


class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str):
        self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts).strip()


def _strip_html(html: str) -> str:
    if not html:
        return ""
    stripper = _HTMLStripper()
    stripper.feed(html)
    return stripper.get_text()


def _get_cloudant():
    from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
    from ibmcloudant.cloudant_v1 import CloudantV1

    url = os.environ.get("CLOUDANT_URL")
    apikey = os.environ.get("CLOUDANT_APIKEY")
    if not url or not apikey:
        raise SystemExit("Set CLOUDANT_URL and CLOUDANT_APIKEY in .env")
    authenticator = IAMAuthenticator(apikey=apikey)
    client = CloudantV1(authenticator=authenticator)
    client.set_service_url(url)
    return client


def _ensure_db(client) -> None:
    try:
        client.put_database(db=DB_NAME).get_result()
        print(f"Created database: {DB_NAME}")
    except Exception as e:
        if "file_exists" not in str(e).lower() and "412" not in str(e):
            raise


def _ensure_roles(client) -> None:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for role in DEFAULT_ROLES:
        doc_id = f"role:{role['id']}"
        doc = {"_id": doc_id, "type": "role", "name": role["name"], "created_at": now}
        try:
            client.put_document(db=DB_NAME, doc_id=doc_id, document=doc).get_result()
        except Exception:
            pass


def _build_params(categories: list[str], levels: list[str], locations: list[str], page: int) -> dict:
    params: dict = {"page": page}
    if categories:
        params["category"] = categories
    if levels:
        params["level"] = levels
    if locations:
        params["location"] = locations
    return params


def _fetch_page(client_httpx: httpx.Client, categories: list[str], levels: list[str], locations: list[str], page: int) -> dict | None:
    # Muse API accepts repeated category= & level= & location= query params
    params_list: list[tuple[str, str]] = [("page", str(page))]
    for c in categories:
        params_list.append(("category", c))
    for lv in levels:
        params_list.append(("level", lv))
    for loc in locations:
        params_list.append(("location", loc))
    try:
        resp = client_httpx.get(MUSE_API_URL, params=params_list, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  ERROR: {e}")
        return None


def _muse_job_to_doc(
    job: dict,
    fetched_at: str,
    company_id: str,
    company_name: str,
) -> dict:
    """Transform one Muse API job to canonical job_post document."""
    muse_id = job.get("id")
    if muse_id is None:
        raise ValueError("Muse job missing id")
    doc_id = f"job_post:themuse:{muse_id}"
    title_raw = job.get("name", "")
    return {
        "_id": doc_id,
        "type": "job_post",
        "source": "themuse",
        "external_id": str(muse_id),
        "company_id": company_id,
        "company_name": company_name,
        "role_id": map_title_to_role_id(title_raw),
        "title_raw": title_raw,
        "description_raw": _strip_html(job.get("contents", "")),
        "url": (job.get("refs") or {}).get("landing_page", ""),
        "posted_at": job.get("publication_date", ""),
        "fetched_at": fetched_at,
        "locations": [loc.get("name", "") for loc in job.get("locations", []) if isinstance(loc, dict) and loc.get("name")],
        "categories": [c.get("name", "") for c in job.get("categories", []) if isinstance(c, dict) and c.get("name")],
        "levels": [l.get("name", "") for l in job.get("levels", []) if isinstance(l, dict) and l.get("name")],
    }


def _build_combos(categories: list[str], levels: list[str], locations: list[str]) -> list[dict]:
    combos = []
    cats = categories or [""]
    lvls = levels or [""]
    for cat in cats:
        for lvl in lvls:
            combos.append({
                "categories": [cat] if cat else [],
                "levels": [lvl] if lvl else [],
                "locations": locations or [],
            })
    return combos


def _put_doc(client, doc: dict) -> bool:
    doc_id = doc["_id"]
    rev = None
    try:
        existing = client.get_document(db=DB_NAME, doc_id=doc_id).get_result()
        rev = existing.get("_rev") if isinstance(existing, dict) else getattr(existing, "_rev", None)
    except Exception:
        pass
    kwargs = {"db": DB_NAME, "doc_id": doc_id, "document": doc}
    if rev is not None:
        kwargs["rev"] = rev
    try:
        client.put_document(**kwargs).get_result()
        return True
    except Exception as e:
        print(f"Skip {doc_id}: {e}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect Muse jobs into Cloudant (canonical job_post)")
    parser.add_argument("--batch", choices=list(BATCH_PRESETS.keys()), help="Preset: tech-all or tech-us")
    parser.add_argument("--category", action="append", default=[], help="Category (repeatable)")
    parser.add_argument("--level", action="append", default=[], help="Level (repeatable)")
    parser.add_argument("--location", action="append", default=[], help="Location (repeatable)")
    parser.add_argument("--max-pages", type=int, default=None, help="Cap pages per combo")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no write")
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

    cloudant = _get_cloudant() if not args.dry_run else None
    if not args.dry_run:
        _ensure_db(cloudant)
        _ensure_roles(cloudant)

    from datetime import datetime, timezone
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    combos = _build_combos(categories, levels, locations)
    print(f"Running {len(combos)} query combo(s)")

    total_fetched = 0
    total_stored = 0

    with httpx.Client() as http_client:
        for combo in combos:
            cat, lvl, loc = combo["categories"], combo["levels"], combo["locations"]
            label = f"{cat[0] if cat else 'all'} / {lvl[0] if lvl else 'all'}"
            print(f"\n--- {label} ---")

            first = _fetch_page(http_client, cat, lvl, loc, 0)
            if not first:
                print("  Failed to fetch first page")
                continue

            page_count = first.get("page_count", 1)
            total_jobs = first.get("total", 0)
            pages_to_fetch = min(MAX_API_PAGE + 1, page_count)
            if args.max_pages is not None:
                pages_to_fetch = min(pages_to_fetch, args.max_pages)
            print(f"  Available: {total_jobs} jobs, {page_count} pages (fetching {pages_to_fetch})")

            if args.dry_run:
                for j in first.get("results", [])[:3]:
                    print(f"  - {j.get('name', '?')} @ {(j.get('company') or {}).get('name', '?')}")
                total_fetched += total_jobs
                continue

            for page_num in range(pages_to_fetch):
                data = first if page_num == 0 else _fetch_page(http_client, cat, lvl, loc, page_num)
                if not data:
                    continue
                results = data.get("results", [])
                stored_combo = 0
                for job in results:
                    company_obj = job.get("company") or {}
                    company_name = company_obj.get("name", "") if isinstance(company_obj, dict) else ""
                    if not company_name:
                        company_name = "Unknown"
                    company_id = ensure_company(cloudant, DB_NAME, company_name, source_id=None)
                    try:
                        doc = _muse_job_to_doc(job, fetched_at, company_id=company_id, company_name=company_name)
                    except ValueError:
                        continue
                    if _put_doc(cloudant, doc):
                        stored_combo += 1
                        total_stored += 1
                    total_fetched += 1
                print(f"  [page {page_num + 1}/{pages_to_fetch}] Fetched {len(results)}, stored {stored_combo}")
                if page_num < pages_to_fetch - 1:
                    time.sleep(1)

    print(f"\nDone. Fetched {total_fetched} jobs, stored {total_stored} in '{DB_NAME}'.")


if __name__ == "__main__":
    main()
