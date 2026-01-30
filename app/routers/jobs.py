from fastapi import APIRouter, HTTPException, Query

from app.database import get_cloudant
from app.models import JobDetail, JobSearchResponse, JobSummary

router = APIRouter(prefix="/jobs", tags=["Jobs"])

DB_NAME = "muse_jobs"

SUMMARY_FIELDS = [
    "_id", "title", "company", "locations", "categories",
    "levels", "publication_date", "landing_page_url",
]


def _doc_to_summary(doc: dict) -> JobSummary:
    return JobSummary(
        id=doc.get("_id", ""),
        title=doc.get("title", ""),
        company=doc.get("company", ""),
        locations=doc.get("locations", []),
        categories=doc.get("categories", []),
        levels=doc.get("levels", []),
        publication_date=doc.get("publication_date", ""),
        landing_page_url=doc.get("landing_page_url", ""),
    )


def _doc_to_detail(doc: dict) -> JobDetail:
    return JobDetail(
        id=doc.get("_id", ""),
        title=doc.get("title", ""),
        company=doc.get("company", ""),
        locations=doc.get("locations", []),
        categories=doc.get("categories", []),
        levels=doc.get("levels", []),
        publication_date=doc.get("publication_date", ""),
        landing_page_url=doc.get("landing_page_url", ""),
        description=doc.get("description", ""),
        source=doc.get("source", ""),
        muse_id=doc.get("muse_id"),
    )


@router.get(
    "/search",
    response_model=JobSearchResponse,
    operation_id="search_jobs",
    summary="Search job listings by title, company, location, category, or level",
    description=(
        "Search tech job listings from The Muse. All text filters are "
        "case-insensitive partial matches. Combine multiple filters to narrow results."
    ),
)
def search_jobs(
    title: str | None = Query(None, description="Job title keyword, e.g. 'Data Scientist'"),
    company: str | None = Query(None, description="Company name, e.g. 'Google'"),
    location: str | None = Query(None, description="City or region, e.g. 'New York'"),
    category: str | None = Query(
        None,
        description="Job category: 'Software Engineering', 'Data Science', 'Data and Analytics', or 'Computer and IT'",
    ),
    level: str | None = Query(
        None,
        description="Seniority level: 'Entry Level', 'Mid Level', or 'Senior Level'",
    ),
    limit: int = Query(25, ge=1, le=100, description="Max results to return"),
    skip: int = Query(0, ge=0, description="Number of results to skip for pagination"),
) -> JobSearchResponse:
    selector: dict = {"type": "muse_job"}

    if title:
        selector["title"] = {"$regex": f"(?i){title}"}
    if company:
        selector["company"] = {"$regex": f"(?i){company}"}
    if location:
        selector["locations"] = {"$elemMatch": {"$regex": f"(?i){location}"}}
    if category:
        selector["categories"] = {"$elemMatch": {"$regex": f"(?i){category}"}}
    if level:
        selector["levels"] = {"$elemMatch": {"$regex": f"(?i){level}"}}

    client = get_cloudant()
    result = client.post_find(
        db=DB_NAME,
        selector=selector,
        fields=SUMMARY_FIELDS,
        limit=limit,
        skip=skip,
    ).get_result()

    docs = result.get("docs", [])
    jobs = [_doc_to_summary(doc) for doc in docs]

    return JobSearchResponse(
        total_results=len(jobs),
        jobs=jobs,
        limit=limit,
        skip=skip,
    )


@router.get(
    "/{doc_id}",
    response_model=JobDetail,
    operation_id="get_job_by_id",
    summary="Get full details of a specific job listing",
    description=(
        "Retrieve complete job information including the full description text. "
        "Use the document ID from search results."
    ),
)
def get_job_by_id(doc_id: str) -> JobDetail:
    client = get_cloudant()
    try:
        result = client.get_document(db=DB_NAME, doc_id=doc_id).get_result()
    except Exception:
        raise HTTPException(status_code=404, detail="Job not found")

    return _doc_to_detail(result)
