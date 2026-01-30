"""
Fetch jobs from the Adzuna API and store them in Cloudant (market_pulse_jobs).

Creates the database if missing, ensures role documents exist, then for each job
puts a document with _id = job_post:adzuna:{id} and role_id from title mapping.

Usage:
    python -m market_pulse.scripts.collect_adzuna --page 1 --what python
    python -m market_pulse.cli collect --page 1 --what python

Requires CLOUDANT_URL, CLOUDANT_APIKEY, ADZUNA_APP_ID, ADZUNA_APP_KEY in .env.
"""

import argparse
import os
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

from market_pulse.roles import DEFAULT_ROLES, map_title_to_role_id

load_dotenv()

DB_NAME = os.environ.get("CLOUDANT_DB_NAME", "market_pulse_jobs")
ADZUNA_BASE = "https://api.adzuna.com/v1/api/jobs/us/search"


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
    """Upsert role documents so job_post.role_id references exist."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for role in DEFAULT_ROLES:
        doc_id = f"role:{role['id']}"
        doc = {"_id": doc_id, "type": "role", "name": role["name"], "created_at": now}
        try:
            client.put_document(db=DB_NAME, doc_id=doc_id, document=doc).get_result()
        except Exception:
            pass  # ignore; doc may already exist


def _job_to_doc(job: dict, fetched_at: str) -> dict:
    """Map one Adzuna result item to a Cloudant document (raw collect + role_id)."""
    external_id = job.get("id", "")
    title_raw = job.get("title") or ""
    doc_id = f"job_post:adzuna:{external_id}"
    return {
        "_id": doc_id,
        "type": "job_post",
        "source": "adzuna",
        "external_id": external_id,
        "role_id": map_title_to_role_id(title_raw),
        "title": title_raw,
        "description": job.get("description"),
        "url": job.get("redirect_url"),
        "created": job.get("created"),
        "company": job.get("company"),
        "location": job.get("location"),
        "category": job.get("category"),
        "salary_min": job.get("salary_min"),
        "salary_max": job.get("salary_max"),
        "salary_is_predicted": job.get("salary_is_predicted"),
        "latitude": job.get("latitude"),
        "longitude": job.get("longitude"),
        "adref": job.get("adref"),
        "fetched_at": fetched_at,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect Adzuna jobs into Cloudant")
    parser.add_argument("--page", type=int, default=1, help="Adzuna API page number")
    parser.add_argument("--what", type=str, default="python", help="Adzuna search query")
    parser.add_argument("--results-per-page", type=int, default=20)
    args = parser.parse_args()

    app_id = os.environ.get("ADZUNA_APP_ID")
    app_key = os.environ.get("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        raise SystemExit("Set ADZUNA_APP_ID and ADZUNA_APP_KEY in .env")

    url = (
        f"{ADZUNA_BASE}/{args.page}"
        f"?app_id={app_id}&app_key={app_key}"
        f"&results_per_page={args.results_per_page}&what={args.what}"
        "&content-type=application/json"
    )
    resp = httpx.get(url)
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results") or []
    count_total = data.get("count", 0)

    client = _get_cloudant()
    _ensure_db(client)
    _ensure_roles(client)

    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stored = 0
    for job in results:
        doc = _job_to_doc(job, fetched_at)
        doc_id = doc["_id"]
        rev = None
        try:
            existing = client.get_document(db=DB_NAME, doc_id=doc_id).get_result()
            rev = existing.get("_rev") if isinstance(existing, dict) else getattr(existing, "_rev", None)
        except Exception:
            pass  # document does not exist; create new
        try:
            kwargs = {"db": DB_NAME, "doc_id": doc_id, "document": doc}
            if rev is not None:
                kwargs["rev"] = rev
            client.put_document(**kwargs).get_result()
            stored += 1
        except Exception as e:
            print(f"Skip {doc_id}: {e}")

    print(f"Stored {stored}/{len(results)} jobs (API total: {count_total})")


if __name__ == "__main__":
    main()
