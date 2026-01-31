# Data Ingestion Guide

This document covers how salary and job data is ingested into Cloudant for the Market Pulse project. It is intended for both team members and coding assistants (Claude Code, Copilot, etc.).

## Architecture

```
Job Salary Data API (OpenWeb Ninja)  ──→  Cloudant DB: salary_data
Adzuna API                           ──→  Cloudant DB: market_pulse_jobs
The Muse API                         ──→  Cloudant DB: market_pulse_jobs
```

Two Cloudant databases store data from different APIs. Salary benchmarks live in `salary_data`. All job postings (from both Adzuna and The Muse) live in `market_pulse_jobs`, distinguished by the `source` field (`"adzuna"` or `"themuse"`).

## Cloudant Instance

- **Service:** watsonx-Hackathon Cloudant
- **Region:** us-south
- **Dashboard:** IBM Cloud Console → Resource list → watsonx-Hackathon Cloudant
- **Endpoint:** `https://a5b71c18-ff9c-47bf-9928-3d8e7113b6ca-bluemix.cloudantnosqldb.appdomain.cloud`
- **Plan:** Lite (1 GB storage, 20 reads/sec, 10 writes/sec)

## Databases

### `salary_data`

Salary benchmarks from the Job Salary Data API (Glassdoor source).

**Document schema:**

```json
{
  "_id": "auto-generated",
  "type": "salary_by_location | salary_by_experience | salary_by_company",
  "job_title": "Software Engineer",
  "location": "New York",
  "years_of_experience": "ONE_TO_THREE",
  "api_response": {
    "location": "New York City, NY",
    "job_title": "Software Engineer",
    "min_salary": 107160.88,
    "max_salary": 183293.88,
    "median_salary": 139237.70,
    "min_base_salary": 80865.00,
    "max_base_salary": 134208.24,
    "median_base_salary": 104176.53,
    "min_additional_pay": 26295.88,
    "max_additional_pay": 49085.64,
    "median_additional_pay": 35061.17,
    "salary_period": "YEAR",
    "salary_currency": "USD",
    "salary_count": 68499,
    "salaries_updated_at": "2025-04-10T23:59:59.000Z",
    "publisher_name": "Glassdoor",
    "confidence": "CONFIDENT"
  }
}
```

**Current data:** 42 documents (6 roles × 7 cities). "Remote" queries returned no data.

**Document types:**
- `salary_by_location` — salary for a role in a city (1-3 years experience)
- `salary_by_experience` — salary for a role at different experience levels
- `salary_by_company` — salary for a role at a specific company

### `job_listings` (legacy)

Old Adzuna job postings database. Superseded by `market_pulse_jobs` — all Adzuna data has been migrated there. Kept for reference only.

## Ingestion Script

**Location:** `scripts/ingest_salaries.py`

### Prerequisites

```bash
# Activate venv
source .venv/bin/activate

# Ensure .env has these values
CLOUDANT_URL=https://a5b71c18-ff9c-47bf-9928-3d8e7113b6ca-bluemix.cloudantnosqldb.appdomain.cloud
CLOUDANT_APIKEY=<cloudant-api-key>
RAPIDAPI_KEY=<your-personal-rapidapi-key>
```

Each team member needs their own RapidAPI key (free tier = 50 requests). Sign up at: https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch

### Batches

The script has 3 batches. Each is sized for one free-tier account:

| Batch | Command | Queries | What it fetches |
|-------|---------|---------|-----------------|
| `locations` | `python scripts/ingest_salaries.py --batch locations` | 48 | 6 roles × 8 cities (1-3yr exp) |
| `experience` | `python scripts/ingest_salaries.py --batch experience` | 60 | 6 roles × 5 exp levels × 2 cities |
| `companies` | `python scripts/ingest_salaries.py --batch companies` | 75 | 5 roles × 15 companies |

**Status:**
- [x] `locations` — completed (42/48 stored, "Remote" returned no data)
- [ ] `experience` — needs a teammate's RapidAPI key
- [ ] `companies` — needs a teammate's RapidAPI key

### Dry Run

Preview queries without calling the API or using any requests:

```bash
python scripts/ingest_salaries.py --batch experience --dry-run
```

### Roles Covered

**Locations batch (current):** Software Engineer, Data Scientist, Machine Learning Engineer, Frontend Developer, Backend Developer, Product Manager

**Experience batch:** Same 6 roles, across all 5 experience levels (LESS_THAN_ONE through TEN_PLUS), in New York and San Francisco

**Companies batch:** Software Engineer, Data Scientist, ML Engineer, Product Manager, DevOps Engineer — at Google, Amazon, Microsoft, Apple, Meta, Netflix, Nvidia, Salesforce, Adobe, IBM, Oracle, Uber, Airbnb, Stripe, Coinbase

### `market_pulse_jobs`

Unified job listings database containing postings from both Adzuna and The Muse. All documents have `type: "job_post"` and are distinguished by the `source` field.

**Adzuna document schema (raw):**

```json
{
  "_id": "job_post:adzuna:{id}",
  "type": "job_post",
  "source": "adzuna",
  "title": "Python Architect",
  "description": "Job description text...",
  "company": {"display_name": "STAFFING TECHNOLOGIES"},
  "location": {"display_name": "San Antonio, Bexar County", "area": ["US", "Texas"]},
  "category": {"label": "IT Jobs", "tag": "it-jobs"},
  "salary_min": 119282.40,
  "salary_max": 119282.40,
  "created": "2026-01-05T10:41:12Z",
  "url": "https://www.adzuna.com/..."
}
```

**Muse document schema (normalized):**

```json
{
  "_id": "job_post:themuse:{id}",
  "type": "job_post",
  "source": "themuse",
  "external_id": "18012186",
  "title_raw": "DevOps Engineer",
  "company_name": "Merge",
  "locations": ["San Francisco, CA"],
  "categories": ["Software Engineering"],
  "levels": ["Mid Level"],
  "posted_at": "2026-01-27T23:32:21Z",
  "description_raw": "Plain text job description (HTML stripped)",
  "url": "https://www.themuse.com/jobs/merge/devops-engineer-637902"
}
```

**Current data:** ~1,986 Adzuna docs + ~4,058 Muse docs (growing).

## Muse Jobs Ingestion Script

**Location:** `scripts/ingest_muse_jobs.py`

### Prerequisites

```bash
source .venv/bin/activate

# Ensure .env has these values (no API key needed — The Muse API is public)
CLOUDANT_URL=https://a5b71c18-ff9c-47bf-9928-3d8e7113b6ca-bluemix.cloudantnosqldb.appdomain.cloud
CLOUDANT_APIKEY=<cloudant-api-key>
```

### Batch Presets

| Batch | Command | What it fetches |
|-------|---------|-----------------|
| `tech-all` | `python scripts/ingest_muse_jobs.py --batch tech-all` | Software Engineering + Data Science + Data and Analytics + Computer and IT, all levels, no location filter |
| `tech-us` | `python scripts/ingest_muse_jobs.py --batch tech-us` | Same categories, filtered to 7 US cities |

### Custom Queries

```bash
# Single category and level
python scripts/ingest_muse_jobs.py --category "Software Engineering" --level "Mid Level"

# Multiple categories (repeatable flags)
python scripts/ingest_muse_jobs.py --category "Software Engineering" --category "Data Science"

# Limit pages for testing
python scripts/ingest_muse_jobs.py --batch tech-all --max-pages 2

# Dry run — preview URL and first page without storing
python scripts/ingest_muse_jobs.py --batch tech-all --dry-run
```

### Deduplication

The script queries Cloudant for existing job IDs before inserting, so it is safe to re-run. Duplicate jobs are skipped automatically.

### Status

- [x] `tech-all` — completed (~8,081 documents stored)
- [ ] `tech-us` — not yet run

### API Limitations

The Muse API reports a `page_count` in responses but returns **400 Bad Request** for any page >= 100. The script works around this by splitting queries into individual category × level combinations, giving each combo its own 100-page window. This maximizes coverage but some results in very large combos (e.g. Software Engineering / Senior Level with 321 pages) remain unreachable.

### API Reference: The Muse

- **Base URL:** `https://www.themuse.com/api/public/jobs`
- **Auth:** None required (500 requests/hour without key, 3600/hour with key)
- **Pagination:** `?page=N` (20 results per page, response includes `page_count`). Hard cap at page 99.
- **Filters (query params, repeatable):**
  - `category` — e.g. "Software Engineering", "Data Science", "Computer and IT"
  - `level` — e.g. "Entry Level", "Mid Level", "Senior Level"
  - `location` — e.g. "New York, NY", "San Francisco, CA"
- **Response fields per job:** `id`, `name`, `company.name`, `locations[].name`, `categories[].name`, `levels[].name`, `publication_date`, `contents` (HTML), `refs.landing_page`

## Querying Cloudant from Python

```python
from app.database import get_cloudant

client = get_cloudant()

# Get all salary records for a specific role
result = client.post_find(
    db="salary_data",
    selector={"job_title": {"$eq": "Software Engineer"}},
).get_result()

for doc in result["docs"]:
    resp = doc["api_response"]
    print(f"{doc['location']}: ${resp['median_salary']:,.0f}")

# Get all salary records for a specific city
result = client.post_find(
    db="salary_data",
    selector={"location": {"$eq": "San Francisco"}},
).get_result()

# Get salary by role AND location
result = client.post_find(
    db="salary_data",
    selector={
        "job_title": {"$eq": "Data Scientist"},
        "location": {"$eq": "New York"},
    },
).get_result()
```

## Uploading Data via CLI / curl

You can also interact with Cloudant directly without the Python SDK.

### Get an IAM bearer token

```bash
# Exchange your Cloudant API key for a bearer token
export TOKEN=$(curl -s -X POST "https://iam.cloud.ibm.com/identity/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=urn:ibm:params:oauth:grant-type:apikey&apikey=$CLOUDANT_APIKEY" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

### Create a database

```bash
curl -X PUT "https://a5b71c18-ff9c-47bf-9928-3d8e7113b6ca-bluemix.cloudantnosqldb.appdomain.cloud/my_database" \
  -H "Authorization: Bearer $TOKEN"
```

### Insert a document

```bash
curl -X POST "https://a5b71c18-ff9c-47bf-9928-3d8e7113b6ca-bluemix.cloudantnosqldb.appdomain.cloud/salary_data" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "salary_by_location",
    "job_title": "Data Engineer",
    "location": "Miami",
    "api_response": {
      "median_salary": 120000,
      "min_salary": 95000,
      "max_salary": 150000
    }
  }'
```

### Bulk insert (multiple documents at once)

```bash
curl -X POST "https://a5b71c18-ff9c-47bf-9928-3d8e7113b6ca-bluemix.cloudantnosqldb.appdomain.cloud/salary_data/_bulk_docs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "docs": [
      {"type": "salary_by_location", "job_title": "Data Engineer", "location": "Miami", "api_response": {"median_salary": 120000}},
      {"type": "salary_by_location", "job_title": "Data Engineer", "location": "Dallas", "api_response": {"median_salary": 115000}}
    ]
  }'
```

### Query documents

```bash
# Find all Software Engineer salary records
curl -X POST "https://a5b71c18-ff9c-47bf-9928-3d8e7113b6ca-bluemix.cloudantnosqldb.appdomain.cloud/salary_data/_find" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"selector": {"job_title": {"$eq": "Software Engineer"}}}'
```

### List all databases

```bash
curl "https://a5b71c18-ff9c-47bf-9928-3d8e7113b6ca-bluemix.cloudantnosqldb.appdomain.cloud/_all_dbs" \
  -H "Authorization: Bearer $TOKEN"
```

### Upload a JSON file as a document

```bash
curl -X POST "https://a5b71c18-ff9c-47bf-9928-3d8e7113b6ca-bluemix.cloudantnosqldb.appdomain.cloud/salary_data" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @my_data.json
```

### Using ibmcloud CLI with Cloudant plugin

```bash
# Install the Cloudant plugin (one-time)
ibmcloud plugin install cloudant

# List databases
ibmcloud cloudant database-get-all --instance-crn "crn:v1:bluemix:public:cloudantnosqldb:us-south:a/4ad5443c7e9f401289c3ddae7579ffb6:c878b661-66c0-4bef-adde-9a69a90dd8c4::"

# Get database info
ibmcloud cloudant database-information --db salary_data --instance-crn "..."
```

## API Reference

### Job Salary Data API (OpenWeb Ninja)

- **Base URL:** `https://api.openwebninja.com/job-salary-data`
- **Auth:** `x-api-key` header with RapidAPI key
- **Endpoints:**
  - `GET /job-salary` — salary by job title + location
    - Params: `job_title` (required), `location` (required), `location_type` (CITY/COUNTRY), `years_of_experience`
  - `GET /company-job-salary` — salary by company + job title
    - Params: `job_title` (required), `company` (required)
- **Experience levels:** LESS_THAN_ONE, ONE_TO_THREE, FOUR_TO_SIX, SEVEN_TO_NINE, TEN_PLUS
- **Rate limit:** 50 requests on free tier per account
- **Source:** Glassdoor salary data

### Adzuna API

Managed by another team member. Provides real job listings with descriptions, companies, locations, and salary ranges.
