import re
import statistics

from fastapi import APIRouter, Query

from app.config import settings
from app.database import get_cloudant
from app.models import SalaryAggregation, SalaryRecord, SalaryResponse

router = APIRouter(prefix="/salaries", tags=["Salaries"])

DB_NAME = settings.cloudant_db_name


# ---------------------------------------------------------------------------
# State abbreviation helpers (duplicated from jobs router to avoid imports)
# ---------------------------------------------------------------------------

_STATE_ABBREVIATIONS: dict[str, str] = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}

_ABBREV_TO_STATE: dict[str, str] = {v.lower(): k for k, v in _STATE_ABBREVIATIONS.items()}


def _expand_location(location: str) -> str:
    """Build a regex that matches both the full state name and its abbreviation."""
    loc_lower = location.lower().strip()

    if loc_lower in _STATE_ABBREVIATIONS:
        abbrev = _STATE_ABBREVIATIONS[loc_lower]
        return f"(?i)({re.escape(location)}|,\\s*{re.escape(abbrev)}\\b)"

    if loc_lower in _ABBREV_TO_STATE:
        full_name = _ABBREV_TO_STATE[loc_lower]
        return f"(?i)({re.escape(location)}|{re.escape(full_name)})"

    return f"(?i){re.escape(location)}"


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get(
    "/search",
    response_model=SalaryResponse,
    operation_id="search_salaries",
    summary="Search salary data from Adzuna job postings",
    description=(
        "Aggregates salary information from Adzuna job postings that include salary data. "
        "Returns individual salary records plus aggregate stats (min, max, median, average). "
        "Requires a job title; location and company are optional filters. "
        "All text filters are case-insensitive partial matches."
    ),
)
def search_salaries(
    job_title: str = Query(..., description="Job title keyword, e.g. 'frontend developer', 'data scientist'"),
    location: str | None = Query(None, description="City, state, or region, e.g. 'California', 'New York'"),
    company: str | None = Query(None, description="Company name, e.g. 'TikTok', 'Amazon'"),
    limit: int = Query(25, ge=1, le=100, description="Max individual salary records to return"),
) -> SalaryResponse:
    selector: dict = {
        "type": "job_post",
        "source": "adzuna",
        "salary_min": {"$gt": 0},
        "title_raw": {"$regex": f"(?i){job_title}"},
    }

    if location:
        selector["locations"] = {"$elemMatch": {"$regex": _expand_location(location)}}
    if company:
        selector["company_name"] = {"$regex": f"(?i){company}"}

    client = get_cloudant()
    result = client.post_find(
        db=DB_NAME, selector=selector, limit=limit,
    ).get_result()

    docs = result.get("docs", [])

    records = [
        SalaryRecord(
            job_title=doc.get("title_raw", ""),
            company=doc.get("company_name", ""),
            location=", ".join(doc.get("locations", [])),
            salary_min=doc["salary_min"],
            salary_max=doc.get("salary_max", doc["salary_min"]),
        )
        for doc in docs
    ]

    aggregation = None
    if records:
        mins = [r.salary_min for r in records]
        maxes = [r.salary_max for r in records]
        midpoints = [(r.salary_min + r.salary_max) / 2 for r in records]

        aggregation = SalaryAggregation(
            avg_salary_min=round(statistics.mean(mins), 2),
            avg_salary_max=round(statistics.mean(maxes), 2),
            overall_min=min(mins),
            overall_max=max(maxes),
            median_salary=round(statistics.median(midpoints), 2),
        )

    message = None
    if not records:
        message = (
            "No salary data found for the given filters. Try broadening your search "
            "by removing the location or company filter, or using a more general job title."
        )

    return SalaryResponse(
        count=len(records),
        aggregation=aggregation,
        records=records,
        message=message,
    )
