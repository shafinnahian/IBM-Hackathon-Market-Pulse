"""
Normalize Adzuna docs in market_pulse_jobs to match the Muse schema.

Renames shared fields to unified names (title_raw, company_name, etc.)
and flattens nested objects, while preserving all source-specific fields
(salary_min, salary_max, latitude, longitude, etc.).

Usage:
    python scripts/normalize_adzuna.py
    python scripts/normalize_adzuna.py --dry-run
"""

import argparse
import time

from app.database import get_cloudant

DB_NAME = "market_pulse_jobs"
BATCH_SIZE = 200


def normalize_doc(doc: dict) -> dict:
    """Transform an Adzuna doc to the unified schema, preserving extras."""
    # Start with a copy of all existing fields
    normalized = dict(doc)

    # --- Extract from nested objects before removing them ---
    company_raw = normalized.pop("company", None)
    location_raw = normalized.pop("location", None)
    category_raw = normalized.pop("category", None)

    # company -> company_name (flat string)
    if isinstance(company_raw, dict):
        normalized["company_name"] = company_raw.get("display_name", "")
    elif isinstance(company_raw, str):
        normalized["company_name"] = company_raw
    else:
        normalized["company_name"] = ""

    # location -> locations (list) + location_area (preserve hierarchy)
    if isinstance(location_raw, dict):
        name = location_raw.get("display_name", "")
        normalized["locations"] = [name] if name else []
        area = location_raw.get("area")
        if area:
            normalized["location_area"] = area
    elif isinstance(location_raw, str):
        normalized["locations"] = [location_raw] if location_raw else []
    else:
        normalized["locations"] = []

    # category -> categories (list) + category_tag (preserve tag)
    if isinstance(category_raw, dict):
        label = category_raw.get("label", "")
        normalized["categories"] = [label] if label else []
        tag = category_raw.get("tag")
        if tag:
            normalized["category_tag"] = tag
    elif isinstance(category_raw, str):
        normalized["categories"] = [category_raw] if category_raw else []
    else:
        normalized["categories"] = []

    # --- Rename shared fields ---
    # title -> title_raw
    if "title" in normalized:
        normalized["title_raw"] = normalized.pop("title")

    # description -> description_raw
    if "description" in normalized:
        normalized["description_raw"] = normalized.pop("description")

    # created -> posted_at
    if "created" in normalized:
        normalized["posted_at"] = normalized.pop("created")

    # --- Add missing unified fields ---
    normalized.setdefault("levels", [])

    # --- Clean up Adzuna internal artifacts ---
    normalized.pop("adref", None)
    normalized.pop("salary_is_predicted", None)

    return normalized


def main():
    parser = argparse.ArgumentParser(description="Normalize Adzuna docs to unified schema")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()

    client = get_cloudant()
    bookmark = None
    total_fetched = 0
    total_updated = 0

    while True:
        kwargs = dict(
            db=DB_NAME,
            selector={"type": "job_post", "source": "adzuna"},
            limit=BATCH_SIZE,
        )
        if bookmark:
            kwargs["bookmark"] = bookmark

        result = client.post_find(**kwargs).get_result()
        docs = result.get("docs", [])
        bookmark = result.get("bookmark")

        if not docs:
            break

        total_fetched += len(docs)
        normalized = [normalize_doc(d) for d in docs]

        if args.dry_run:
            for orig, norm in zip(docs, normalized):
                print(f"  {orig['_id']}: {orig.get('title', '?')!r} -> title_raw={norm['title_raw']!r}, "
                      f"company_name={norm['company_name']!r}, locations={norm['locations']}")
        else:
            resp = client.post_bulk_docs(db=DB_NAME, bulk_docs={"docs": normalized}).get_result()
            errors = [r for r in resp if "error" in r]
            ok_count = len(resp) - len(errors)
            total_updated += ok_count
            if errors:
                print(f"  {len(errors)} errors in batch: {errors[:3]}")

        print(f"Processed {total_fetched} docs so far...")
        time.sleep(0.5)

    if args.dry_run:
        print(f"\nDry run complete. {total_fetched} docs would be updated.")
    else:
        print(f"\nDone. {total_updated}/{total_fetched} docs updated successfully.")


if __name__ == "__main__":
    main()
