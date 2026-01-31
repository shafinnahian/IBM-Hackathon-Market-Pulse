import re

from fastapi import APIRouter, HTTPException, Query

from app.database import get_cloudant
from app.models import JobDetail, JobMatchResponse, JobMatchSummary, JobSearchResponse, JobSummary

router = APIRouter(prefix="/jobs", tags=["Jobs"])

DB_NAME = "market_pulse_jobs"


# ---------------------------------------------------------------------------
# Unified doc → model converters
# ---------------------------------------------------------------------------

def _doc_to_summary(doc: dict) -> JobSummary:
    return JobSummary(
        id=doc.get("_id", ""),
        title=doc.get("title_raw", ""),
        company=doc.get("company_name", ""),
        locations=doc.get("locations", []),
        categories=doc.get("categories", []),
        levels=doc.get("levels", []),
        publication_date=doc.get("posted_at", ""),
        landing_page_url=doc.get("url", ""),
        source=doc.get("source", ""),
    )


def _doc_to_detail(doc: dict) -> JobDetail:
    return JobDetail(
        id=doc.get("_id", ""),
        title=doc.get("title_raw", ""),
        company=doc.get("company_name", ""),
        locations=doc.get("locations", []),
        categories=doc.get("categories", []),
        levels=doc.get("levels", []),
        publication_date=doc.get("posted_at", ""),
        landing_page_url=doc.get("url", ""),
        description=doc.get("description_raw", ""),
        source=doc.get("source", ""),
        external_id=str(doc.get("external_id")) if doc.get("external_id") is not None else None,
        salary_min=doc.get("salary_min"),
        salary_max=doc.get("salary_max"),
    )


# ---------------------------------------------------------------------------
# Selector builder
# ---------------------------------------------------------------------------

def _build_selector(
    title: str | None,
    company: str | None,
    location: str | None,
    category: str | None,
    level: str | None,
    source: str | None,
) -> dict:
    selector: dict = {"type": "job_post"}

    if source:
        selector["source"] = source
    if title:
        selector["title_raw"] = {"$regex": f"(?i){title}"}
    if company:
        selector["company_name"] = {"$regex": f"(?i){company}"}
    if location:
        selector["locations"] = {"$elemMatch": {"$regex": f"(?i){location}"}}
    if category:
        selector["categories"] = {"$elemMatch": {"$regex": f"(?i){category}"}}
    if level:
        selector["levels"] = {"$elemMatch": {"$regex": f"(?i){level}"}}

    return selector


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/search",
    response_model=JobSearchResponse,
    operation_id="search_jobs",
    summary="Search job listings by title, company, location, category, or level",
    description=(
        "Search tech job listings from The Muse and Adzuna. All text filters are "
        "case-insensitive partial matches. Combine multiple filters to narrow results. "
        "Use the 'source' parameter to filter by data source ('themuse' or 'adzuna'). "
        "Adzuna jobs include salary data visible in the detail endpoint. "
        "The 'level' filter only applies to Muse jobs."
    ),
)
def search_jobs(
    title: str | None = Query(None, description="Job title keyword, e.g. 'Data Scientist'"),
    company: str | None = Query(None, description="Company name, e.g. 'Google'"),
    location: str | None = Query(None, description="City or region, e.g. 'New York'"),
    category: str | None = Query(
        None,
        description="Job category, e.g. 'Software Engineering', 'Data Science', 'IT Jobs'",
    ),
    level: str | None = Query(
        None,
        description="Seniority level: 'Entry Level', 'Mid Level', or 'Senior Level' (Muse jobs only)",
    ),
    source: str | None = Query(
        None,
        description="Filter by data source: 'themuse', 'adzuna', or omit for both",
    ),
    limit: int = Query(25, ge=1, le=100, description="Max results to return"),
    skip: int = Query(0, ge=0, description="Number of results to skip for pagination"),
) -> JobSearchResponse:
    client = get_cloudant()

    if source:
        selector = _build_selector(title, company, location, category, level, source)
        result = client.post_find(
            db=DB_NAME, selector=selector, limit=limit, skip=skip,
        ).get_result()
        jobs = [_doc_to_summary(d) for d in result.get("docs", [])]
    else:
        # Interleaved query: half from each source, merged by date
        half_a = limit // 2 + limit % 2
        half_b = limit // 2
        skip_a = skip // 2 + skip % 2
        skip_b = skip // 2

        muse_sel = _build_selector(title, company, location, category, level, "themuse")
        adzuna_sel = _build_selector(title, company, location, category, level, "adzuna")

        muse_docs = client.post_find(
            db=DB_NAME, selector=muse_sel, limit=half_a, skip=skip_a,
        ).get_result().get("docs", [])

        adzuna_docs = client.post_find(
            db=DB_NAME, selector=adzuna_sel, limit=half_b, skip=skip_b,
        ).get_result().get("docs", [])

        all_docs = muse_docs + adzuna_docs
        all_docs.sort(key=lambda d: d.get("posted_at", ""), reverse=True)
        jobs = [_doc_to_summary(d) for d in all_docs]

    return JobSearchResponse(
        total_results=len(jobs),
        jobs=jobs,
        limit=limit,
        skip=skip,
    )


# ---------------------------------------------------------------------------
# Skills matching
# ---------------------------------------------------------------------------

def _score_skills(doc: dict, skills: list[str]) -> tuple[list[str], int]:
    """Return (matched_skills, count) for a doc against a list of skills."""
    text = doc.get("description_raw", "").lower()
    matched = [s for s in skills if re.search(rf"\b{re.escape(s.lower())}\b", text)]
    return matched, len(matched)


@router.get(
    "/match-skills",
    response_model=JobMatchResponse,
    operation_id="match_skills",
    summary="Find jobs matching a set of skills",
    description=(
        "Takes a comma-separated list of skills and returns jobs whose descriptions "
        "mention those skills, ranked by how many skills match. Useful for matching "
        "a candidate's resume skills to relevant job listings."
    ),
)
def match_skills(
    skills: str = Query(
        ...,
        description="Comma-separated skills, e.g. 'Python,SQL,React,AWS'",
    ),
    source: str | None = Query(
        None,
        description="Filter by data source: 'themuse', 'adzuna', or omit for both",
    ),
    limit: int = Query(25, ge=1, le=100, description="Max results to return"),
) -> JobMatchResponse:
    client = get_cloudant()
    skill_list = [s.strip() for s in skills.split(",") if s.strip()]

    if not skill_list:
        return JobMatchResponse(total_results=0, jobs=[], limit=limit)

    pattern = "|".join(re.escape(s) for s in skill_list)
    regex = {"$regex": f"(?i)({pattern})"}
    fetch_limit = limit * 4

    if source:
        selector: dict = {"type": "job_post", "source": source, "description_raw": regex}
        docs = client.post_find(
            db=DB_NAME, selector=selector, limit=fetch_limit,
        ).get_result().get("docs", [])
    else:
        half = fetch_limit // 2
        muse_docs = client.post_find(
            db=DB_NAME,
            selector={"type": "job_post", "source": "themuse", "description_raw": regex},
            limit=half,
        ).get_result().get("docs", [])
        adzuna_docs = client.post_find(
            db=DB_NAME,
            selector={"type": "job_post", "source": "adzuna", "description_raw": regex},
            limit=half,
        ).get_result().get("docs", [])
        docs = muse_docs + adzuna_docs

    scored = []
    for doc in docs:
        matched, count = _score_skills(doc, skill_list)
        if count > 0:
            summary = _doc_to_summary(doc)
            scored.append(JobMatchSummary(
                **summary.model_dump(),
                matched_skills=matched,
                match_count=count,
            ))

    scored.sort(key=lambda j: j.match_count, reverse=True)
    scored = scored[:limit]

    return JobMatchResponse(total_results=len(scored), jobs=scored, limit=limit)


@router.get(
    "/{doc_id}",
    response_model=JobDetail,
    operation_id="get_job_by_id",
    summary="Get full details of a specific job listing",
    description=(
        "Retrieve complete job information including the full description text. "
        "Use the document ID from search results. Works for both Muse and Adzuna jobs. "
        "Adzuna jobs may include salary_min and salary_max fields."
    ),
)
def get_job_by_id(doc_id: str) -> JobDetail:
    client = get_cloudant()

    try:
        result = client.get_document(db=DB_NAME, doc_id=doc_id).get_result()
    except Exception:
        raise HTTPException(status_code=404, detail="Job not found")

    return _doc_to_detail(result)
