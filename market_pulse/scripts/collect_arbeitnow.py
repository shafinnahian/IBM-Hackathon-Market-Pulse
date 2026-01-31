"""
Fetch job listings from the Arbeitnow job-board API and store in Cloudant (market_pulse_jobs)
using the same canonical job_post schema as Adzuna and The Muse.

API: https://www.arbeitnow.com/api/job-board-api (public, no auth)
Pagination: ?limit=100&page=1

Usage:
    python -m market_pulse.scripts.collect_arbeitnow
    python -m market_pulse.scripts.collect_arbeitnow --max-pages 3
    python -m market_pulse.scripts.collect_arbeitnow --dry-run
    python -m market_pulse.cli collect-arbeitnow --max-pages 2

Requires CLOUDANT_URL, CLOUDANT_APIKEY in .env.
"""

import argparse
import os
import time
from datetime import datetime, timezone
from html.parser import HTMLParser

import httpx
from dotenv import load_dotenv

from market_pulse.companies import ensure_company
from market_pulse.roles import map_title_to_role_id

load_dotenv()

DB_NAME = os.environ.get("CLOUDANT_DB_NAME", "market_pulse_jobs")
ARBEITNOW_API_URL = "https://www.arbeitnow.com/api/job-board-api"
DEFAULT_LIMIT = 100


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


# Timeout for Cloudant requests (seconds); avoids indefinite hang if service is slow/unreachable
CLOUDANT_TIMEOUT = 45


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
    client.set_http_config({"timeout": CLOUDANT_TIMEOUT})
    return client


def _ensure_db(client) -> None:
    try:
        client.put_database(db=DB_NAME).get_result()
        print(f"Created database: {DB_NAME}")
    except Exception as e:
        if "file_exists" not in str(e).lower() and "412" not in str(e):
            raise


def _ensure_roles(client) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    from market_pulse.roles import DEFAULT_ROLES

    for role in DEFAULT_ROLES:
        doc_id = f"role:{role['id']}"
        doc = {"_id": doc_id, "type": "role", "name": role["name"], "created_at": now}
        try:
            client.put_document(db=DB_NAME, doc_id=doc_id, document=doc).get_result()
        except Exception:
            pass


def _unix_to_iso(ts: int | float | None) -> str:
    """Convert Unix timestamp to ISO 8601 string."""
    if ts is None:
        return ""
    try:
        dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, OSError):
        return ""


def _fetch_page(client_httpx: httpx.Client, page: int) -> dict | None:
    params = {"limit": DEFAULT_LIMIT, "page": page}
    try:
        resp = client_httpx.get(ARBEITNOW_API_URL, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  ERROR: {e}")
        return None


def _arbeitnow_job_to_doc(
    job: dict,
    fetched_at: str,
    company_id: str,
    company_name: str,
) -> dict:
    """Transform one Arbeitnow API job to canonical job_post document."""
    slug = job.get("slug")
    if not slug:
        raise ValueError("Arbeitnow job missing slug")
    doc_id = f"job_post:arbeitnow:{slug}"
    title_raw = job.get("title") or ""
    location = job.get("location")
    locations = [location] if location else []
    tags = job.get("tags")
    categories = list(tags) if isinstance(tags, list) else []
    job_types_raw = job.get("job_types")
    job_types = list(job_types_raw) if isinstance(job_types_raw, list) else []
    posted_at = _unix_to_iso(job.get("created_at"))

    return {
        "_id": doc_id,
        "type": "job_post",
        "source": "arbeitnow",
        "external_id": slug,
        "company_id": company_id,
        "company_name": company_name,
        "role_id": map_title_to_role_id(title_raw),
        "title_raw": title_raw,
        "description_raw": _strip_html(job.get("description") or ""),
        "url": job.get("url") or "",
        "posted_at": posted_at,
        "fetched_at": fetched_at,
        "locations": locations,
        "categories": categories,
        "levels": [],  # Arbeitnow has no seniority; use job_types for employment type
        "job_types": job_types,
        "remote": bool(job.get("remote")),
    }


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
    parser = argparse.ArgumentParser(
        description="Collect Arbeitnow jobs into Cloudant (canonical job_post)",
    )
    parser.add_argument("--max-pages", type=int, default=None, help="Cap number of pages to fetch")
    parser.add_argument("--page", type=int, default=1, help="Starting page (default 1)")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no write")
    args = parser.parse_args()

    cloudant = _get_cloudant() if not args.dry_run else None
    if not args.dry_run:
        _ensure_db(cloudant)
        _ensure_roles(cloudant)

    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    total_fetched = 0
    total_stored = 0
    page = args.page
    max_pages = args.max_pages

    with httpx.Client() as http_client:
        while True:
            if max_pages is not None and (page - args.page) >= max_pages:
                break
            data = _fetch_page(http_client, page)
            if not data:
                break
            jobs = data.get("data") or []
            if not jobs:
                break

            if args.dry_run:
                for j in jobs[:5]:
                    print(f"  - {j.get('title', '?')} @ {j.get('company_name', '?')}")
                total_fetched += len(jobs)
                meta = data.get("meta") or {}
                if not data.get("links", {}).get("next"):
                    break
                page += 1
                time.sleep(1)
                continue

            stored_page = 0
            company_cache: dict[str, str] = {}  # company_name -> company_id (fewer Cloudant calls)
            print(f"  [page {page}] Ensuring companies and storing {len(jobs)} jobs...", end="", flush=True)
            for i, job in enumerate(jobs):
                company_name = (job.get("company_name") or "").strip() or "Unknown"
                if company_name not in company_cache:
                    company_cache[company_name] = ensure_company(
                        cloudant, DB_NAME, company_name, source_id=None
                    )
                company_id = company_cache[company_name]
                try:
                    doc = _arbeitnow_job_to_doc(
                        job,
                        fetched_at,
                        company_id=company_id,
                        company_name=company_name,
                    )
                except ValueError:
                    continue
                if _put_doc(cloudant, doc):
                    stored_page += 1
                    total_stored += 1
                total_fetched += 1
                if (i + 1) % 25 == 0:
                    print(f" {i + 1}", end="", flush=True)
            print(f" done. Stored {stored_page}.")
            if not data.get("links", {}).get("next"):
                break
            page += 1
            time.sleep(1)

    print(f"\nDone. Fetched {total_fetched} jobs, stored {total_stored} in '{DB_NAME}'.")


if __name__ == "__main__":
    main()
