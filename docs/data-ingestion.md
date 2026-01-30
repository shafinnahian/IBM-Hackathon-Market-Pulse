# Data Ingestion Guide

This document covers how salary and job data is ingested into Cloudant for the Market Pulse project. It is intended for both team members and coding assistants (Claude Code, Copilot, etc.).

## Architecture

```
Job Salary Data API (OpenWeb Ninja)  ──→  Cloudant DB: salary_data
Adzuna API                           ──→  Cloudant DB: job_listings
```

Two separate Cloudant databases store data from two different APIs. They share common fields (`job_title`, `location`, `company`) that can be used to cross-reference.

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

### `job_listings`

Job postings from the Adzuna API (managed by another team member).

**Document schema (from Adzuna):**

```json
{
  "_id": "auto-generated",
  "type": "job_listing",
  "adzuna_id": "5568088167",
  "title": "Python Architect",
  "description": "Job description text...",
  "company": "STAFFING TECHNOLOGIES",
  "location": "San Antonio, Bexar County",
  "location_area": ["US", "Texas", "Bexar County", "San Antonio"],
  "category": "IT Jobs",
  "salary_min": 119282.40,
  "salary_max": 119282.40,
  "created": "2026-01-05T10:41:12Z",
  "redirect_url": "https://www.adzuna.com/..."
}
```

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
