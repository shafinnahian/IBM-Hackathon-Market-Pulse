"""
Fetch salary data from Job Salary Data API and store in Cloudant.

Usage:
    # Run a specific batch (each uses a different RapidAPI account's free tier):
    python scripts/ingest_salaries.py --batch locations     # 120 queries — salary by role × city
    python scripts/ingest_salaries.py --batch experience    #  60 queries — salary by role × exp level
    python scripts/ingest_salaries.py --batch companies     #  75 queries — salary by role × company

    # Dry run (print queries without calling API):
    python scripts/ingest_salaries.py --batch locations --dry-run

Requires .env with:
    CLOUDANT_URL, CLOUDANT_APIKEY, RAPIDAPI_KEY
"""

import argparse
import os
import re
import sys
import time
import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from app.database import get_cloudant, ensure_database

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
SALARY_API_URL = "https://api.openwebninja.com/job-salary-data/job-salary"
COMPANY_SALARY_API_URL = "https://api.openwebninja.com/job-salary-data/company-job-salary"
# Single DB for all market data (jobs + salary)
DB_NAME = os.getenv("CLOUDANT_DB_NAME", "market_pulse_jobs")

# ---------------------------------------------------------------------------
# Data dimensions
# ---------------------------------------------------------------------------

ROLES = [
    "Software Engineer",
    "Data Scientist",
    "Machine Learning Engineer",
    "Frontend Developer",
    "Backend Developer",
    "Product Manager",
]

LOCATIONS = [
    "San Francisco",
    "New York",
    "Seattle",
    "Austin",
    "Los Angeles",
    "Chicago",
    "Boston",
    "Remote",
]

EXPERIENCE_LEVELS = [
    "LESS_THAN_ONE",
    "ONE_TO_THREE",
    "FOUR_TO_SIX",
    "SEVEN_TO_NINE",
    "TEN_PLUS",
]

# Roles to cross with experience levels (top 6 for career progression analysis)
EXPERIENCE_ROLES = [
    "Software Engineer",
    "Data Scientist",
    "Machine Learning Engineer",
    "Frontend Developer",
    "Backend Developer",
    "Product Manager",
]

# Cities for experience level queries
EXPERIENCE_CITIES = ["New York", "San Francisco"]

COMPANIES = [
    "Google",
    "Amazon",
    "Microsoft",
    "Apple",
    "Meta",
    "Netflix",
    "Nvidia",
    "Salesforce",
    "Adobe",
    "IBM",
    "Oracle",
    "Uber",
    "Airbnb",
    "Stripe",
    "Coinbase",
]

# Roles to cross with companies
COMPANY_ROLES = [
    "Software Engineer",
    "Data Scientist",
    "Machine Learning Engineer",
    "Product Manager",
    "DevOps Engineer",
]

# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def fetch_salary(job_title: str, location: str, years_of_experience: str = "ONE_TO_THREE") -> dict | None:
    headers = {"x-api-key": RAPIDAPI_KEY, "Accept": "*/*"}
    params = {
        "job_title": job_title,
        "location": location,
        "location_type": "COUNTRY" if location == "Remote" else "CITY",
        "years_of_experience": years_of_experience,
    }
    try:
        resp = requests.get(SALARY_API_URL, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print(f"  ERROR: {e}")
        return None


def fetch_company_salary(job_title: str, company: str) -> dict | None:
    headers = {"x-api-key": RAPIDAPI_KEY, "Accept": "*/*"}
    params = {"job_title": job_title, "company": company}
    try:
        resp = requests.get(COMPANY_SALARY_API_URL, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print(f"  ERROR: {e}")
        return None


def _slug(s: str) -> str:
    """Normalize string for use in _id (lowercase, non-alphanumeric -> hyphen)."""
    if not s:
        return "unknown"
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "unknown"


def _salary_doc_id(q: dict) -> str:
    """Deterministic _id for salary docs so re-runs overwrite."""
    t = q.get("type", "")
    role = _slug(q.get("job_title", ""))
    if t == "salary_by_location":
        loc = _slug(q.get("location", ""))
        exp = (q.get("years_of_experience") or "ONE_TO_THREE").replace("_", "-")
        return f"salary_location:{role}:{loc}:{exp}"
    if t == "salary_by_experience":
        loc = _slug(q.get("location", ""))
        exp = (q.get("years_of_experience") or "").replace("_", "-")
        return f"salary_experience:{role}:{loc}:{exp}"
    if t == "salary_by_company":
        company = _slug(q.get("company", ""))
        return f"salary_company:{role}:{company}"
    return f"salary:{role}:{id(q)}"


def store_in_cloudant(doc: dict) -> bool:
    """Upsert salary doc with deterministic _id (GET rev then PUT). Returns True if stored."""
    client = get_cloudant()
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
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Batch definitions
# ---------------------------------------------------------------------------

def build_locations_batch() -> list[dict]:
    """12 roles × 10 locations = 120 queries."""
    queries = []
    for role in ROLES:
        for loc in LOCATIONS:
            queries.append({
                "type": "salary_by_location",
                "job_title": role,
                "location": loc,
                "years_of_experience": "ONE_TO_THREE",
            })
    return queries


def build_experience_batch() -> list[dict]:
    """6 roles × 5 exp levels × 2 cities = 60 queries."""
    queries = []
    for role in EXPERIENCE_ROLES:
        for city in EXPERIENCE_CITIES:
            for exp in EXPERIENCE_LEVELS:
                queries.append({
                    "type": "salary_by_experience",
                    "job_title": role,
                    "location": city,
                    "years_of_experience": exp,
                })
    return queries


def build_companies_batch() -> list[dict]:
    """5 roles × 15 companies = 75 queries."""
    queries = []
    for role in COMPANY_ROLES:
        for company in COMPANIES:
            queries.append({
                "type": "salary_by_company",
                "job_title": role,
                "company": company,
            })
    return queries


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_batch(queries: list[dict], dry_run: bool = False):
    ensure_database(DB_NAME)

    total = len(queries)
    stored = 0

    print(f"{'DRY RUN — ' if dry_run else ''}Running {total} queries\n")

    for i, q in enumerate(queries, 1):
        label = q.get("company", q.get("location", "?"))
        print(f"[{i}/{total}] {q['job_title']} — {label}", end="")
        if "years_of_experience" in q and q["type"] == "salary_by_experience":
            print(f" ({q['years_of_experience']})", end="")
        print("...", end=" ")

        if dry_run:
            print("SKIP (dry run)")
            continue

        if q["type"] == "salary_by_company":
            data = fetch_company_salary(q["job_title"], q["company"])
        else:
            data = fetch_salary(q["job_title"], q["location"], q.get("years_of_experience", "ONE_TO_THREE"))

        if data and data.get("status") == "OK" and data.get("data"):
            doc = {**q, "api_response": data["data"][0]}
            doc["_id"] = _salary_doc_id(q)
            if store_in_cloudant(doc):
                stored += 1
                print("OK")
            else:
                print("SKIP")
        else:
            print("NO DATA")

        time.sleep(1)

    print(f"\nDone. Stored {stored}/{total} records in Cloudant '{DB_NAME}'.")


def main():
    parser = argparse.ArgumentParser(description="Ingest salary data into Cloudant")
    parser.add_argument("--batch", required=True, choices=["locations", "experience", "companies"],
                        help="Which batch to run")
    parser.add_argument("--dry-run", action="store_true", help="Print queries without calling API")
    args = parser.parse_args()

    if not args.dry_run:
        if not RAPIDAPI_KEY:
            print("ERROR: Set RAPIDAPI_KEY in .env")
            sys.exit(1)
        if not os.getenv("CLOUDANT_URL") or not os.getenv("CLOUDANT_APIKEY"):
            print("ERROR: Set CLOUDANT_URL and CLOUDANT_APIKEY in .env")
            sys.exit(1)

    batches = {
        "locations": build_locations_batch,
        "experience": build_experience_batch,
        "companies": build_companies_batch,
    }

    queries = batches[args.batch]()
    run_batch(queries, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
